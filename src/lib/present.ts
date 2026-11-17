import type { LiveRow, DbRow } from "./live";

/** What the browser gets for one row: LIVE label values displayed; DB values kept only where they differ. */
export function present<T extends DbRow>(r: LiveRow<T>) {
  const d = r.db as Record<string, unknown>;
  const L = r.live;
  const dbDiff: Record<string, unknown> = {};
  for (const k of r.changed) dbDiff[k] = d[k] ?? null;
  return {
    file_id: r.db.file_id,
    document_id: d.document_id ?? null,
    name: r.name,
    web_view_link: r.web_view_link,
    kind: L.kind,
    entities: L.entities,
    portcos: L.portcos,
    fiscal_year: L.fiscal_year,
    period: L.period,
    stage: L.stage ?? (d.stage === "unknown" ? "unknown" : null),
    executed_date: L.executed_date,
    workstream: L.workstream,
    issuer: L.issuer,
    tier: L.tier ?? (d.tier as string | null) ?? null,
    review_status: L.review_status,
    signed_date: d.signed_date ?? null,
    effective_date: d.effective_date ?? null,
    is_primary: d.is_primary ?? null,
    modified_time: d.modified_time ?? null,
    file_type_family: d.file_type_family ?? null,
    queue_reason: d.queue_reason ?? null,
    signals: d.signals ?? null,
    confidence: d.confidence ?? null,
    stage_suggested: d.stage_suggested ?? null,
    changed: r.changed,
    catalog: dbDiff,
  };
}
export type PresentedRow = ReturnType<typeof present>;
