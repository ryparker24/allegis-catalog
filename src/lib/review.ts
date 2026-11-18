import type { Db } from "./db";
import type { Session } from "./session";
import { buildReviewMods, validateReview } from "./labels";
import { FILE_ID_RE, modifyLabels, type FetchLike } from "./google";
import { logEvent } from "./log";

/**
 * "Confirm and next": (1) the file must be in the queue view (labelled, non-secret, not yet reviewed);
 * (2) files.modifyLabels AS THE USER, Execution + Catalog Review labels only; (3) one app.review_event row.
 * Skip never calls this.
 */
export async function reviewWrite(body: unknown, ctx: { session: Session; db: Db; fetch?: FetchLike }): Promise<{ status: number; body: Record<string, unknown> }> {
  const o = (body ?? {}) as Record<string, unknown>;
  const fileId = String(o.file_id ?? "");
  if (!FILE_ID_RE.test(fileId)) return { status: 400, body: { error: "bad_file_id" } };
  const v = validateReview(o);
  if (!v.ok) return { status: 400, body: { error: "bad_input", reason: v.reason } };

  const q = await ctx.db.rows<{ document_id: string | null; queue_reason: string; requires_execution: boolean | null }>(
    "SELECT document_id, queue_reason, requires_execution FROM app.v_review_queue WHERE file_id = $1", [fileId]);
  if (!q.length) return { status: 404, body: { error: "not_in_queue" } };
  // R-022 on the server too (CISO review): Status is for non-executable documents only - the Status-unknown lane, or
  // a file the catalog does not mark as requiring execution. An executable document gets a Stage.
  if (v.value.docStatus && q[0].queue_reason !== "status_unknown" && q[0].requires_execution === true)
    return { status: 400, body: { error: "bad_input", reason: "status_not_for_executable" } };

  const { labelModifications, labels } = buildReviewMods({ ...v.value, reviewerEmail: ctx.session.email });
  const d = await modifyLabels(ctx.session.at, fileId, labelModifications, ctx.fetch);
  if (d.status !== 200) {
    logEvent("review_write", { outcome: "drive_refused", file_id: fileId, drive_status: d.status });
    return { status: d.status === 401 ? 401 : d.status === 403 || d.status === 404 ? 403 : 502, body: { error: "drive_write_failed", drive_status: d.status } };
  }
  try {
    await ctx.db.exec(
      `INSERT INTO app.review_event (file_id, document_id, reviewer_email, status, stage, executed_date, note, queue_reason, labels_written, edits)
       VALUES ($1, $2, $3, $4, $5, $6::date, $7, $8, $9::text[], $10::jsonb)`,
      [fileId, q[0].document_id, ctx.session.email.toLowerCase(), v.value.status, v.value.stage, v.value.executedDate, v.value.note, q[0].queue_reason, labels,
       v.value.docStatus ? JSON.stringify({ status: v.value.docStatus }) : null],
    );
  } catch {
    // Drive already holds the review; the queue will show the file again until the event lands. Say so plainly.
    logEvent("review_write", { outcome: "event_insert_failed", file_id: fileId, document_id: q[0].document_id, status: v.value.status });
    return { status: 500, body: { error: "event_insert_failed", drive_written: true } };
  }
  logEvent("review_write", { outcome: "ok", file_id: fileId, document_id: q[0].document_id, status: v.value.status, stage: v.value.stage, doc_status: v.value.docStatus ?? null, queue_reason: q[0].queue_reason, labels });
  return { status: 200, body: { ok: true, labels } };
}
