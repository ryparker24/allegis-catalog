/**
 * CAT-WO-03 item 3 (R-026) · set a document's Subject as the signed-in user: roster CODES (Subject code(s)) and/or a
 * current staff account (Subject (person)) on the Parties label. Never a typed name: codes are pattern-checked AND must
 * be on the roster of the document's entities (app.v_party); the person must be an @allegiscapital.com account.
 * Used by the Review lane "Match subject" (source match_subject) and Find's side panel (source find_single).
 * Until the Subject fields are published, the decision is recorded in app.review_event only (the nightly subject step
 * carries it to the catalog and the re-sync writes it to the label once published).
 */
import type { Db } from "./db";
import type { Session } from "./session";
import { hasField, SCHEMA, STAFF_EMAIL_RE, SUBJECT_CODE_RE } from "./labels";
import { modifyLabels, FILE_ID_RE, type FetchLike } from "./google";
import { liveWritable } from "./editflow";
import { logEvent } from "./log";

type Out = { status: number; body: Record<string, unknown> };
export const MAX_CODES = 20;

export interface SubjectInput { codes: string[] | null; person: string | null | undefined; none: boolean }

/** codes: null = leave unchanged, [] with none = "this document has no roster subject". person: undefined = unchanged. */
export function validateSubject(o: Record<string, unknown>): { ok: true; value: SubjectInput } | { ok: false; reason: string } {
  const none = o.none === true;
  let codes: string[] | null = null;
  if (o.codes !== undefined && o.codes !== null) {
    if (!Array.isArray(o.codes) || o.codes.length > MAX_CODES) return { ok: false, reason: "codes" };
    const c = o.codes.map((x) => String(x).trim().toUpperCase());
    if (!c.every((x) => SUBJECT_CODE_RE.test(x))) return { ok: false, reason: "codes_must_be_roster_codes" };   // never a typed name
    codes = [...new Set(c)].sort();
  }
  if (none) {
    if (codes && codes.length) return { ok: false, reason: "none_with_codes" };
    codes = [];
  }
  let person: string | null | undefined = undefined;
  if (o.person !== undefined) {
    person = o.person === null || o.person === "" ? null : String(o.person).trim().toLowerCase();
    if (person !== null && !STAFF_EMAIL_RE.test(person)) return { ok: false, reason: "person_must_be_staff_account" };
  }
  if (codes === null && person === undefined) return { ok: false, reason: "nothing_to_change" };
  return { ok: true, value: { codes, person, none } };
}

export function subjectMods(v: SubjectInput): { labelModifications: unknown[]; labels: string[] } {
  const P = SCHEMA.parties;
  if (!P) return { labelModifications: [], labels: [] };
  const fm: unknown[] = [];
  if (v.codes !== null && hasField("parties", "subject_codes")) {
    const f = P.fields.subject_codes.field_id;
    fm.push(v.codes.length ? { fieldId: f, setTextValues: [v.codes.join(", ")] } : { fieldId: f, unsetValues: true });
  }
  if (v.person !== undefined && hasField("parties", "subject_person")) {
    const f = P.fields.subject_person.field_id;
    fm.push(v.person ? { fieldId: f, setUserValues: [v.person] } : { fieldId: f, unsetValues: true });
  }
  return fm.length ? { labelModifications: [{ labelId: P.label_id, fieldModifications: fm }], labels: ["parties"] } : { labelModifications: [], labels: [] };
}

export async function subjectWrite(body: unknown, ctx: { session: Session; db: Db; fetch?: FetchLike; source: "match_subject" | "find_single" }): Promise<Out> {
  const o = (body ?? {}) as Record<string, unknown>;
  const fileId = String(o.file_id ?? "");
  if (!FILE_ID_RE.test(fileId)) return { status: 400, body: { error: "bad_file_id" } };
  const v = validateSubject(o);
  if (!v.ok) return { status: 400, body: { error: "bad_input", reason: v.reason } };
  const q = await ctx.db.rows<{ document_id: string | null; entities: string[]; issuing_entity: string | null }>(
    "SELECT document_id::text AS document_id, entities, issuing_entity FROM app.v_find_x WHERE file_id = $1", [fileId]);
  if (!q.length || !q[0].document_id) return { status: 403, body: { error: "no_access" } };
  if (v.value.codes && v.value.codes.length) {
    // every code must be on the roster of one of the document's entities (or its issuer): no free codes
    const ents = [...new Set([...(q[0].entities ?? []), ...(q[0].issuing_entity ? [q[0].issuing_entity] : [])])];
    const ok = await ctx.db.rows<{ partner_code: string }>(
      "SELECT DISTINCT partner_code FROM app.v_party WHERE partner_code = ANY($1::text[]) AND entity_code = ANY($2::text[])", [v.value.codes, ents]);
    if (ok.length !== v.value.codes.length) return { status: 400, body: { error: "bad_input", reason: "code_not_on_the_documents_roster" } };
  }
  const acc = await liveWritable(ctx.session.at, [fileId], ctx.fetch);
  if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
  if (!acc.ok.length) return { status: 403, body: { error: acc.noAccess.length ? "no_access" : "access_check_failed" } };
  const { labelModifications, labels } = subjectMods(v.value);
  if (labelModifications.length) {
    const d = await modifyLabels(ctx.session.at, fileId, labelModifications, ctx.fetch);
    if (d.status !== 200) {
      logEvent("subject_write", { outcome: "drive_refused", file_id: fileId, drive_status: d.status });
      return { status: d.status === 401 ? 401 : d.status === 403 || d.status === 404 ? 403 : 502, body: { error: "drive_write_failed", drive_status: d.status } };
    }
  }
  const edits: Record<string, unknown> = {};
  if (v.value.codes !== null) edits.subject_codes = v.value.codes;
  if (v.value.person !== undefined) edits.subject_person = v.value.person;
  try {
    await ctx.db.exec(
      `INSERT INTO app.review_event (file_id, document_id, reviewer_email, status, queue_reason, labels_written, source, edits)
       VALUES ($1, $2, $3, 'edited', $4, $5::text[], $6, $7::jsonb)`,
      [fileId, q[0].document_id, ctx.session.email.toLowerCase(), ctx.source === "match_subject" ? "match_subject" : null, labels, ctx.source, JSON.stringify(edits)]);
  } catch {
    logEvent("subject_write", { outcome: "event_insert_failed", file_id: fileId, drive_status: labels.length ? 200 : 0 });
    return { status: 500, body: { error: "event_insert_failed", drive_written: labels.length > 0 } };
  }
  logEvent("subject_write", { outcome: "ok", file_id: fileId, document_id: q[0].document_id, labels, lane: ctx.source, count: v.value.codes?.length ?? 0 });
  return { status: 200, body: { ok: true, labels, label_published: labels.length > 0, recorded: true } };
}

// ------------------------------------------------------------------ the Workspace directory (R-026 Subject (person))
export interface StaffHit { email: string; name: string }
/**
 * People API searchDirectoryPeople AS THE USER (directory.readonly; requested only on a person-field edit).
 * Names go to the browser for the picker only; they are never logged or stored. Staff accounts only.
 */
export async function directorySearch(accessToken: string, q: string, f: FetchLike = (i, init) => fetch(i, init)): Promise<{ status: number; hits: StaffHit[] }> {
  const u = new URL("https://people.googleapis.com/v1/people:searchDirectoryPeople");
  u.searchParams.set("query", q);
  u.searchParams.set("readMask", "names,emailAddresses");
  u.searchParams.append("sources", "DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE");
  u.searchParams.set("pageSize", "20");
  const r = await f(u.toString(), { headers: { authorization: `Bearer ${accessToken}` } }).catch(() => null);
  if (!r) return { status: 0, hits: [] };
  if (!r.ok) return { status: r.status, hits: [] };
  const j = (await r.json().catch(() => ({}))) as { people?: { names?: { displayName?: string }[]; emailAddresses?: { value?: string }[] }[] };
  const hits: StaffHit[] = [];
  for (const p of j.people ?? []) {
    const email = (p.emailAddresses ?? []).map((e) => (e.value ?? "").toLowerCase()).find((e) => STAFF_EMAIL_RE.test(e));
    const name = p.names?.[0]?.displayName ?? "";
    if (email) hits.push({ email, name });
  }
  return { status: 200, hits };
}
