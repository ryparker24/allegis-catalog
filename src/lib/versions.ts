/**
 * CAT-WO-04 · version families in the app: the side-panel Versions timeline, its actions, Find's merge and the Review
 * lane "Link versions".
 *
 * Reads: app.v_family_member (catalog_app). A member is shown only after a live access check of its file as the user
 * (R-020); members the user can't open are a count only. Names never reach the DB, the log or a label.
 * Writes: one app.review_event (source version_link, edits.version = {action, ...}); the trigger
 * app.tg_review_event_version applies it at once as PERSON-SET family rows the nightly run never changes.
 * The L6 Version label follows in the nightly re-sync (it writes the catalog's person-set values; codes / IDs only).
 */
import type { Db } from "./db";
import type { Session } from "./session";
import { accessFor } from "./checklists";
import { FILE_ID_RE, type FetchLike } from "./google";
import { logEvent } from "./log";

export const ROLE_LABEL: Record<string, string> = {
  current: "Current", superseded: "Superseded", amends: "Amends", redline: "Redline / compare", draft_of: "Draft of",
};
export const ACTIONS = ["mark_current", "remove", "move", "amends", "merge", "accept", "split"] as const;
export type VersionAction = (typeof ACTIONS)[number];
export const MERGE_CAP = 50;

const ID = /^[0-9]{1,12}$/;
const id = (v: unknown) => (v != null && ID.test(String(v)) ? String(v) : null);

export type ActionInput = { action: VersionAction; document?: string; family?: string; base?: string; target?: string; documents?: string[] };

/** Validates the browser's request: codes and catalog numbers only. */
export function validateAction(x: unknown): { ok: true; value: ActionInput } | { ok: false; reason: string } {
  const o = (x ?? {}) as Record<string, unknown>;
  const action = String(o.action ?? "") as VersionAction;
  if (!(ACTIONS as readonly string[]).includes(action)) return { ok: false, reason: "bad_action" };
  const v: ActionInput = { action };
  if (["mark_current", "remove", "move", "amends"].includes(action)) {
    const d = id(o.document); if (!d) return { ok: false, reason: "bad_document" }; v.document = d;
  }
  if (action === "move") {   // "move to the family of catalog ID ...": a member of the other family
    const t = id(o.target); if (!t || t === v.document) return { ok: false, reason: "bad_target" }; v.target = t;
  }
  if (action === "accept" || action === "split") {
    const f = id(o.family); if (!f) return { ok: false, reason: "bad_family" }; v.family = f;
  }
  if (action === "amends") {
    const b = id(o.base); if (!b || b === v.document) return { ok: false, reason: "bad_base" }; v.base = b;
  }
  if (action === "merge" || action === "split") {
    if (!Array.isArray(o.documents)) return { ok: false, reason: "bad_documents" };
    const ds = [...new Set((o.documents as unknown[]).map(id))];
    if (ds.some((d) => !d) || ds.length > MERGE_CAP) return { ok: false, reason: "bad_documents" };
    if (action === "merge" && ds.length < 2) return { ok: false, reason: "merge_needs_two" };
    if (action === "split" && ds.length < 1) return { ok: false, reason: "bad_documents" };
    v.documents = ds as string[];
  }
  return { ok: true, value: v };
}

export type Member = {
  family_id: string; family_confidence: string; family_reason: string[]; current_document_id: string | null;
  document_id: string; role: string | null; supersedes: string | null; amends: string | null; person_set: boolean; person_current: boolean;
  kind: string | null; stage: string | null; status: string | null; effective_date: string | null; fiscal_year: number | null;
  file_id: string | null; web_view_link: string | null; modified_time: string | null;
};
const MEMBER_COLS = `family_id::text, family_confidence, family_reason, current_document_id::text, document_id::text, role,
  supersedes::text, amends::text, person_set, person_current, kind, stage, status, effective_date::text, fiscal_year, file_id,
  web_view_link, modified_time::text`;

export type ShownMember = Omit<Member, "web_view_link"> & { name: string; link: string };

/** The family of one file's document, every member live-checked as the user; the rest are counted only. */
export async function timeline(D: Db, token: string, fileId: string, f?: FetchLike): Promise<{ status: number; body: Record<string, unknown> }> {
  if (!FILE_ID_RE.test(fileId)) return { status: 400, body: { error: "bad_file_id" } };
  const q = await D.rows<{ document_id: string | null }>("SELECT document_id::text AS document_id FROM app.v_find_x WHERE file_id = $1", [fileId]);
  if (!q.length) return { status: 403, body: { error: "no_access" } };
  if (!q[0].document_id) return { status: 200, body: { family: null, members: [], not_shown: 0 } };
  const ms = await D.rows<Member>(
    `SELECT ${MEMBER_COLS} FROM app.v_family_member WHERE family_id = (SELECT family_id FROM app.v_family_member WHERE document_id = $1::bigint)
     ORDER BY (role = 'current') DESC, (role = 'amends') DESC, effective_date DESC NULLS LAST, modified_time DESC NULLS LAST LIMIT 200`,
    [q[0].document_id]);
  return shown(ms, token, f, { document_id: q[0].document_id, file_id: fileId });
}

async function shown(ms: Member[], token: string, f: FetchLike | undefined, ctx: Record<string, unknown>) {
  if (!ms.length) return { status: 200, body: { family: null, members: [], not_shown: 0 } };
  const acc = await accessFor(token, ms.map((m) => m.file_id ?? "").filter(Boolean), f);
  if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
  const out: ShownMember[] = [];
  let hidden = 0;
  for (const m of ms) {
    const a = m.file_id ? acc.map.get(m.file_id) : undefined;
    if (a?.state !== "ok") { hidden++; continue; }
    const { web_view_link: _drop, ...rest } = m;
    void _drop;
    out.push({ ...rest, name: a.name, link: a.link });
  }
  const f0 = ms[0];
  logEvent("versions_read", { ...ctx, count: out.length, dropped_no_access: hidden });
  return {
    status: 200,
    body: {
      family: { family_id: f0.family_id, confidence: f0.family_confidence, reason: f0.family_reason, current_document_id: f0.current_document_id, size: ms.length },
      members: out, not_shown: hidden,
    },
  };
}

/** The Review lane "Link versions": proposed families, one page; members live-checked like the timeline. */
export async function lane(D: Db, token: string, page = 0, f?: FetchLike): Promise<{ status: number; body: Record<string, unknown> }> {
  const size = 10;
  const p = Math.max(0, Math.min(10_000, Math.floor(page) || 0));
  const [fams, n] = await Promise.all([
    D.rows<{ family_id: string; reason: string[]; n_members: number }>(
      `SELECT family_id::text, reason, n_members FROM app.v_link_versions ORDER BY n_members DESC, family_id LIMIT ${size} OFFSET ${p * size}`),
    D.rows<{ n: number }>("SELECT count(*)::int AS n FROM app.v_link_versions"),
  ]);
  if (!fams.length) return { status: 200, body: { families: [], total: n[0]?.n ?? 0, page: p, page_size: size } };
  const ms = await D.rows<Member>(`SELECT ${MEMBER_COLS} FROM app.v_family_member WHERE family_id = ANY($1::bigint[])
    ORDER BY family_id, (role = 'current') DESC, effective_date DESC NULLS LAST, modified_time DESC NULLS LAST`, [fams.map((x) => x.family_id)]);
  const acc = await accessFor(token, ms.map((m) => m.file_id ?? "").filter(Boolean), f);
  if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
  let hidden = 0;
  const families = fams.map((fa) => {
    const mine = ms.filter((m) => m.family_id === fa.family_id);
    const members: ShownMember[] = [];
    let not_shown = 0;
    for (const m of mine) {
      const a = m.file_id ? acc.map.get(m.file_id) : undefined;
      if (a?.state !== "ok") { not_shown++; continue; }
      const { web_view_link: _d, ...rest } = m;
      void _d;
      members.push({ ...rest, name: a.name, link: a.link });
    }
    hidden += not_shown;
    return { family_id: fa.family_id, reason: fa.reason, size: fa.n_members, members, not_shown };
  });
  logEvent("versions_lane", { page: p, count: families.length, dropped_no_access: hidden });
  return { status: 200, body: { families, total: n[0]?.n ?? 0, page: p, page_size: size } };
}

/**
 * Applies one action as the person. Every document the action touches must open for the user now (live check of its
 * primary copy); for accept / split, every member of the family. One answer for "not in scope" and "can't open".
 */
export async function act(body: unknown, ctx: { session: Session; db: Db; fetch?: FetchLike }): Promise<{ status: number; body: Record<string, unknown> }> {
  const v = validateAction(body);
  if (!v.ok) return { status: 400, body: { error: "bad_input", reason: v.reason } };
  const a = v.value;
  const D = ctx.db;
  // the documents the action touches, and the copy to check for each
  let docs: string[] = [...(a.documents ?? []), ...(a.document ? [a.document] : []), ...(a.base ? [a.base] : []), ...(a.target ? [a.target] : [])];
  if (a.action === "move") {
    const t = await D.rows<{ family_id: string }>("SELECT family_id::text FROM app.v_family_member WHERE document_id = $1::bigint", [a.target]);
    if (!t.length) return { status: 400, body: { error: "bad_input", reason: "target_not_in_a_family" } };
    a.family = t[0].family_id;
  }
  if (a.family) {
    const fm = await D.rows<{ document_id: string }>("SELECT document_id::text FROM app.v_family_member WHERE family_id = $1::bigint", [a.family]);
    if (!fm.length) return { status: 404, body: { error: "no_such_family" } };
    if (a.action === "split" && !a.documents!.every((d) => fm.some((m) => m.document_id === d))) return { status: 400, body: { error: "bad_input", reason: "not_in_family" } };
    if (a.action === "accept" || a.action === "split") docs = [...docs, ...fm.map((m) => m.document_id)];
  }
  docs = [...new Set(docs)];
  const files = await D.rows<{ document_id: string; file_id: string }>(
    `SELECT DISTINCT ON (document_id) document_id::text, file_id FROM app.v_find_x WHERE document_id = ANY($1::bigint[])
     ORDER BY document_id, is_primary DESC NULLS LAST, file_id`, [docs]);
  if (files.length !== docs.length) return { status: 403, body: { error: "no_access" } };
  const acc = await accessFor(ctx.session.at, files.map((x) => x.file_id), ctx.fetch);
  if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
  if (files.some((x) => acc.map.get(x.file_id)?.state !== "ok")) return { status: 403, body: { error: "no_access" } };
  const anchor = files.find((x) => x.document_id === (a.document ?? a.documents?.[0])) ?? files[0];
  const rec: Record<string, unknown> = { action: a.action };
  if (a.document) rec.document = a.document;
  if (a.family) rec.family = a.family;
  if (a.base) rec.base = a.base;
  if (a.documents) rec.documents = a.documents;
  try {
    await D.exec(
      `INSERT INTO app.review_event (file_id, document_id, reviewer_email, status, labels_written, source, edits)
       VALUES ($1, $2::bigint, $3, 'edited', '{}'::text[], 'version_link', $4::jsonb)`,
      [anchor.file_id, anchor.document_id, ctx.session.email.toLowerCase(), JSON.stringify({ version: rec })]);
  } catch {
    logEvent("versions_action", { outcome: "event_insert_failed", action: a.action, document_id: anchor.document_id });
    return { status: 500, body: { error: "event_insert_failed" } };
  }
  logEvent("versions_action", { outcome: "ok", action: a.action, document_id: anchor.document_id, count: docs.length });
  return { status: 200, body: { ok: true } };
}
