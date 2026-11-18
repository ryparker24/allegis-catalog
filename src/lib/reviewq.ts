/**
 * CAT-WO-02 item 2 on the Review queue: server-side filters, sort and paging over app.v_review_queue.
 * Filters reuse Find's whitelisted, bound buildWhere(); the lane (queue reason) and sort are whitelisted here.
 * The default order is unchanged from CAT-WO-01 (stage unknown first, then lowest confidence).
 */
import { buildWhere, pageSizeOf, parseSpec, SpecError, type FindSpec } from "./find";

export const LANES = ["stage_unknown", "low_confidence_executed", "no_kind"] as const;
const SORT: Record<string, string> = {
  queue: "queue_rank, confidence_rank",
  queue_reason: "queue_rank",
  confidence: "confidence_rank",
  kind: "kind", stage: "stage", fiscal_year: "fiscal_year", modified_time: "modified_time", entities: "entities", file_id: "file_id",
};
export const REVIEW_SORTABLE = Object.keys(SORT);
/** Review list columns (widths saved per user, item 2). */
export const REVIEW_COLUMNS = ["name", "why", "stage", "kind", "entities", "fiscal_year", "confidence"];

export interface ReviewSpec { spec: FindSpec; lanes: string[] }

/** spec (JSON, from the query string) + lane list -> validated ReviewSpec. Throws SpecError. */
export function parseReviewSpec(rawSpec: string | null, rawLanes: string | null): ReviewSpec {
  let o: Record<string, unknown> = {};
  if (rawSpec) {
    if (rawSpec.length > 4000) throw new SpecError("spec: too long");
    try { o = JSON.parse(rawSpec); } catch { throw new SpecError("spec: invalid json"); }
  }
  const sort = o.sort as { col?: string; dir?: string } | undefined;
  if (sort && !REVIEW_SORTABLE.includes(String(sort.col))) throw new SpecError("sort: column not sortable");
  // validate filters / search / pageSize with Find's parser (sort checked above, Find's sort list differs)
  const spec = parseSpec({ ...o, sort: undefined });
  spec.sort = sort ? { col: String(sort.col), dir: sort.dir === "asc" ? "asc" : "desc" } : undefined;
  const lanes = (rawLanes ?? "").split(",").filter(Boolean);
  if (lanes.length > LANES.length || !lanes.every((l) => (LANES as readonly string[]).includes(l))) throw new SpecError("lane: bad value");
  return { spec, lanes };
}

export function reviewQuery(r: ReviewSpec, skip: string[], page: number): { sql: string; countSql: string; params: unknown[]; pageSize: number } {
  const { where, params } = buildWhere(r.spec);
  const p = (v: unknown) => { params.push(v); return `$${params.length}`; };
  const parts = where ? [where.replace(/^WHERE /, "")] : [];
  parts.push(`NOT (file_id = ANY(${p(skip)}::text[]))`);
  if (r.lanes.length) parts.push(`queue_reason = ANY(${p(r.lanes)}::text[])`);
  const col = r.spec.sort?.col ?? "queue";
  const desc = r.spec.sort?.dir === "desc";
  // "queue" = the review order (most uncertain first); descending reverses it (coder review: the arrow must do something)
  const order = col === "queue"
    ? (desc ? "queue_rank DESC, confidence_rank DESC" : SORT.queue)
    : `${SORT[col]}${desc ? " DESC NULLS LAST" : " ASC NULLS LAST"}, queue_rank, confidence_rank`;
  const pageSize = r.spec.pageSize ? pageSizeOf(r.spec) : 50; // CAT-WO-01 default stays 50 when no size is chosen
  return {
    params, pageSize,
    countSql: `SELECT count(*)::int AS n FROM app.v_review_queue WHERE ${parts.join(" AND ")}`,
    sql: `SELECT file_id, document_id, kind, entities, portcos, fiscal_year, period, stage, signed_date, effective_date, workstream, issuer,
                 tier, is_primary, modified_time, file_type_family, queue_reason, signals, confidence, stage_suggested
          FROM app.v_review_queue WHERE ${parts.join(" AND ")}
          ORDER BY ${order}, file_id LIMIT ${pageSize} OFFSET ${page * pageSize}`,
  };
}
