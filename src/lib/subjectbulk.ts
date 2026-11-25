/**
 * CAT-WO-15 · bulk Confirm on the Review "Match subject" lane (R-023: at most 500 per action). Writes ONLY through the existing
 * Parties path of a single save (subject.ts subjectMods + a match_subject review event), and only when the person clicks.
 */
import type { Db } from "./db";
import type { Session } from "./session";
import { BULK_CAP, bulkWrite } from "./edit";
import { liveWritable } from "./editflow";
import { buildWhere, SpecError } from "./find";
import { FILE_ID_RE, type FetchLike } from "./google";
import { SUBJECT_CODE_RE } from "./labels";
import { logEvent } from "./log";
import { parseReviewSpec } from "./reviewq";
import { subjectMods } from "./subject";

type Out = { status: number; body: Record<string, unknown> };

/** reasons that mean "a person must look": never confirmed in bulk */
export const BULK_SUBJECT_BLOCKERS = ["MULTIPLE", "NOT_IN_FUND", "CONFLICT_PERSON", "CONFLICT_PORTAL", "NO_ROSTER_MATCH"] as const;

/**
 * The lane rows a bulk Confirm may take: Match subject, exactly ONE roster candidate, no blocking reason, and that code on the
 * roster of the document's entities (or its issuer): the same roster check as a single save. Filters = the Review list's.
 */
export function subjectBulkQuery(rawSpec: string | null): { sql: string; countSql: string; params: unknown[] } {
  const rs = parseReviewSpec(rawSpec, "match_subject");
  const { where, params } = buildWhere(rs.spec);
  const p = (v: unknown) => { params.push(v); return `$${params.length}`; };
  const parts = where ? [where.replace(/^WHERE /, "")] : [];
  parts.push(`queue_reason = 'match_subject'`, `cardinality(subject_candidates) = 1`,
    `NOT (coalesce(subject_reasons, '{}'::text[]) && ${p([...BULK_SUBJECT_BLOCKERS])}::text[])`,
    `EXISTS (SELECT 1 FROM app.v_find_x x JOIN app.v_party vp ON vp.partner_code = q.subject_candidates[1]
             AND (vp.entity_code = ANY(x.entities) OR vp.entity_code = x.issuing_entity) WHERE x.file_id = q.file_id)`);
  const w = parts.join(" AND ");
  return {
    params,
    countSql: `SELECT count(*)::int AS n FROM app.v_review_queue q WHERE ${w}`,
    sql: `SELECT q.file_id, q.document_id::text AS document_id, q.subject_candidates[1] AS code FROM app.v_review_queue q WHERE ${w}
          ORDER BY q.queue_rank, q.confidence_rank, q.file_id LIMIT ${BULK_CAP}`,
  };
}

/**
 * Without confirm: a preview (how many qualify, how many this action takes) and NO writes. With confirm: at most 500, each file
 * live-checked as the user (no access / secret skipped), the single candidate written to Subject code(s), then recorded.
 */
export async function subjectBulk(body: unknown, ctx: { session: Session; db: Db; fetch?: FetchLike; sleep?: (ms: number) => Promise<void> }): Promise<Out> {
  const o = (body ?? {}) as Record<string, unknown>;
  let q;
  try { q = subjectBulkQuery(typeof o.spec === "string" ? o.spec : null); }
  catch (e) { return { status: 400, body: { error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid" } }; }
  const total = (await ctx.db.rows<{ n: number }>(q.countSql, q.params))[0]?.n ?? 0;
  if (o.confirm !== true) {
    return { status: 200, body: { preview: true, eligible: total, this_action: Math.min(total, BULK_CAP), cap: BULK_CAP } };
  }
  const rows = (await ctx.db.rows<{ file_id: string; document_id: string; code: string }>(q.sql, q.params))
    .filter((r) => FILE_ID_RE.test(r.file_id) && SUBJECT_CODE_RE.test(String(r.code)))
    .slice(0, BULK_CAP);
  if (!rows.length) return { status: 200, body: { ok: true, report: { done: 0, skipped_no_access: 0, skipped_check_failed: 0, failed: 0, events_failed: false, eligible_before: total, label_published: false }, failed: [] } };
  const acc = await liveWritable(ctx.session.at, rows.map((r) => r.file_id), ctx.fetch);
  if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
  const by = new Map(rows.map((r) => [r.file_id, r]));
  const modsFor = (id: string) => subjectMods({ codes: [by.get(id)!.code], person: undefined, none: false });
  const labels = modsFor(rows[0].file_id).labels;
  let eventsFailed = false;
  const record = async (ids: string[]) => {
    if (!ids.length) return;
    const params: unknown[] = [];
    const vals = ids.map((id) => {
      const r = by.get(id)!;
      params.push(id, r.document_id, ctx.session.email.toLowerCase(), labels, JSON.stringify({ subject_codes: [r.code], bulk: true }));
      const b = params.length - 5;
      return `($${b + 1}, $${b + 2}, $${b + 3}, 'edited', 'match_subject', $${b + 4}::text[], 'match_subject', $${b + 5}::jsonb)`;
    });
    try {
      await ctx.db.exec(`INSERT INTO app.review_event (file_id, document_id, reviewer_email, status, queue_reason, labels_written, source, edits)
                         VALUES ${vals.join(", ")}`, params);
    } catch { eventsFailed = true; logEvent("subject_bulk", { outcome: "event_insert_failed", count: ids.length }); }
  };
  let done: string[] = [];
  let skippedNoAccess: string[] = [];
  let failed: { file_id: string; drive_status: number }[] = [];
  if (labels.length) {
    const res = await bulkWrite(ctx.session.at, acc.ok, (id) => modsFor(id).labelModifications, { fetch: ctx.fetch, sleep: ctx.sleep, onBatch: record });
    done = res.done; skippedNoAccess = res.skippedNoAccess; failed = res.failed;
  } else {
    done = acc.ok;                                  // Subject fields unpublished: recorded only (as a single save)
    await record(done);
  }
  const report = {
    done: done.length, skipped_no_access: acc.noAccess.length + skippedNoAccess.length, skipped_check_failed: acc.checkFailed.length,
    failed: failed.length, events_failed: eventsFailed, eligible_before: total, label_published: labels.length > 0,
  };
  logEvent("subject_bulk", { outcome: "done", count: report.done, total: rows.length, labels, lane: "match_subject" });
  return { status: 200, body: { ok: true, report, failed } };
}
