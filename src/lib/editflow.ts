import type { Db } from "./db";
import type { Session } from "./session";
import { BULK_CAP, buildEditMods, bulkWrite, editRecord, validateEdit, type EditSet } from "./edit";
import { driveBatchGet, FILE_ID_RE, isTransient, modifyLabels, type FetchLike } from "./google";
import { decodeLabels, INCLUDE_LABELS } from "./labels";
import { logEvent } from "./log";

type Out = { status: number; body: Record<string, unknown> };
const ACCESS_FIELDS = "id,capabilities/canModifyLabels,labelInfo";

/**
 * The user's live access check (R-020 condition 1) before any write: the file must open for them, they must be
 * allowed to change its labels, and its live Handling tier must not be secret. Returns the ids that pass.
 */
export async function liveWritable(token: string, ids: string[], f?: FetchLike): Promise<{ ok: string[]; noAccess: string[]; checkFailed: string[]; expired: boolean }> {
  const out = { ok: [] as string[], noAccess: [] as string[], checkFailed: [] as string[], expired: false };
  for (let i = 0; i < ids.length; i += 100) {
    const chunk = ids.slice(i, i + 100);
    const m = await driveBatchGet(token, chunk, { fields: ACCESS_FIELDS, includeLabels: INCLUDE_LABELS }, f);
    for (const id of chunk) {
      const it = m.get(id);
      if (!it) { out.checkFailed.push(id); continue; }
      if (it.status === 401) { out.expired = true; out.checkFailed.push(id); continue; }
      if (it.status === 200 && it.body) {
        const caps = it.body.capabilities as { canModifyLabels?: boolean } | undefined;
        const live = decodeLabels(it.body.labelInfo as never);
        if (caps?.canModifyLabels === false || live.tier === "secret") out.noAccess.push(id);
        else out.ok.push(id);
        continue;
      }
      if (isTransient(it)) out.checkFailed.push(id); else out.noAccess.push(id);
    }
  }
  return out;
}

async function recordEvents(D: Db, rows: { file_id: string; document_id: string | null }[], email: string, e: EditSet, labels: string[], source: string) {
  if (!rows.length) return;
  // one multi-row insert (codes only in edits)
  const params: unknown[] = [];
  const vals = rows.map((r) => {
    params.push(r.file_id, r.document_id, email.toLowerCase(), e.stage ?? null, e.executed_date ?? null, labels, source, JSON.stringify(editRecord(e)));
    const b = params.length - 8;
    return `($${b + 1}, $${b + 2}, $${b + 3}, 'confirmed', $${b + 4}, $${b + 5}::date, NULL, NULL, $${b + 6}::text[], $${b + 7}, $${b + 8}::jsonb)`;
  });
  await D.exec(
    `INSERT INTO app.review_event (file_id, document_id, reviewer_email, status, stage, executed_date, note, queue_reason, labels_written, source, edits)
     VALUES ${vals.join(", ")}`, params);
}

/** Single edit (Find side panel / Review form). */
export async function editOne(body: unknown, ctx: { session: Session; db: Db; fetch?: FetchLike; source?: "find_single" | "review_edit" }): Promise<Out> {
  const o = (body ?? {}) as Record<string, unknown>;
  const fileId = String(o.file_id ?? "");
  if (!FILE_ID_RE.test(fileId)) return { status: 400, body: { error: "bad_file_id" } };
  const v = validateEdit(o.set);
  if (!v.ok) return { status: 400, body: { error: "bad_input", reason: v.reason } };
  const q = await ctx.db.rows<{ document_id: string | null }>("SELECT document_id::text AS document_id FROM app.v_find_x WHERE file_id = $1", [fileId]);
  if (!q.length) return { status: 404, body: { error: "not_in_catalog_scope" } };
  const acc = await liveWritable(ctx.session.at, [fileId], ctx.fetch);
  if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
  if (!acc.ok.length) return { status: 403, body: { error: acc.noAccess.length ? "no_access" : "access_check_failed" } };
  const { labelModifications, labels } = buildEditMods(v.value, ctx.session.email);
  const d = await modifyLabels(ctx.session.at, fileId, labelModifications, ctx.fetch);
  if (d.status !== 200) {
    logEvent("edit_write", { outcome: "drive_refused", file_id: fileId, drive_status: d.status });
    return { status: d.status === 401 ? 401 : d.status === 403 || d.status === 404 ? 403 : 502, body: { error: "drive_write_failed", drive_status: d.status } };
  }
  try {
    await recordEvents(ctx.db, [{ file_id: fileId, document_id: q[0].document_id }], ctx.session.email, v.value, labels, ctx.source ?? "find_single");
  } catch {
    logEvent("edit_write", { outcome: "event_insert_failed", file_id: fileId });
    return { status: 500, body: { error: "event_insert_failed", drive_written: true } };
  }
  logEvent("edit_write", { outcome: "ok", file_id: fileId, document_id: q[0].document_id, labels });
  return { status: 200, body: { ok: true, labels } };
}

/**
 * Bulk edit. Without confirm: a preview (count in scope, the change) and NO writes. With confirm: capped at 500,
 * each file live-checked as the user (failures skipped), written in batches, then logged. Report: done / skipped / failed.
 */
export async function editBulk(body: unknown, ctx: { session: Session; db: Db; fetch?: FetchLike; sleep?: (ms: number) => Promise<void> }): Promise<Out> {
  const o = (body ?? {}) as Record<string, unknown>;
  if (!Array.isArray(o.file_ids)) return { status: 400, body: { error: "bad_input", reason: "file_ids" } };
  const ids = [...new Set((o.file_ids as unknown[]).map(String))];
  if (ids.length > BULK_CAP) return { status: 400, body: { error: "too_many_files", cap: BULK_CAP, got: ids.length } };
  if (!ids.length || !ids.every((id) => FILE_ID_RE.test(id))) return { status: 400, body: { error: "bad_input", reason: "file_ids" } };
  const v = validateEdit(o.set, { bulk: true });
  if (!v.ok) return { status: 400, body: { error: "bad_input", reason: v.reason } };
  const inScope = await ctx.db.rows<{ file_id: string; document_id: string | null }>(
    "SELECT file_id, document_id::text AS document_id FROM app.v_find_x WHERE file_id = ANY($1::text[])", [ids]);
  const notInScope = ids.length - inScope.length;
  if (o.confirm !== true) {
    return { status: 200, body: { preview: true, files: ids.length, in_scope: inScope.length, not_in_scope: notInScope, change: v.value, cap: BULK_CAP } };
  }
  const acc = await liveWritable(ctx.session.at, inScope.map((r) => r.file_id), ctx.fetch);
  if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
  const { labelModifications, labels } = buildEditMods(v.value, ctx.session.email);
  const res = await bulkWrite(ctx.session.at, acc.ok, labelModifications, { fetch: ctx.fetch, sleep: ctx.sleep });
  const doneSet = new Set(res.done);
  let eventsFailed = false;
  try {
    await recordEvents(ctx.db, inScope.filter((r) => doneSet.has(r.file_id)), ctx.session.email, v.value, labels, "find_bulk");
  } catch { eventsFailed = true; }
  const report = {
    done: res.done.length,
    skipped_no_access: acc.noAccess.length + res.skippedNoAccess.length,
    skipped_check_failed: acc.checkFailed.length,
    skipped_not_in_scope: notInScope,
    failed: res.failed.length,
    events_failed: eventsFailed,
  };
  logEvent("edit_bulk", { outcome: "done", count: report.done, total: ids.length, labels });
  return { status: 200, body: { ok: true, report, failed: res.failed } };
}
