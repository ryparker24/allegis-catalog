/**
 * CAT-WO-02 item 2 · one column model for Find, shared by the server (SQL whitelist) and the browser (grid).
 * type decides the header filter: pick = multi-select of codes, year/date = from/to, text = contains, flag = yes/no/any.
 * source "live" columns come only from the Drive call on the visible page, so they can't be sorted or filtered in SQL.
 */
import type { VocabList } from "./vocab";

export type ColType = "pick" | "year" | "date" | "text" | "flag";
export interface ColDef {
  key: string;
  label: string;
  type: ColType;
  source: "db" | "live";
  /** SQL expression in app.v_find (db columns only) */
  sql?: string;
  array?: boolean;
  vocab?: VocabList;
  /** facet key served by /api/facets (pick columns) */
  facet?: string;
  /** default width in px */
  width: number;
}

export const COLUMN_DEFS: ColDef[] = [
  { key: "name", label: "Name", type: "text", source: "live", width: 340 },
  { key: "kind", label: "Kind", type: "pick", source: "db", sql: "kind", vocab: "kind", facet: "kind", width: 170 },
  { key: "entities", label: "Entity", type: "pick", source: "db", sql: "entities", array: true, facet: "entity", width: 130 },
  { key: "portcos", label: "Portco", type: "pick", source: "db", sql: "portcos", array: true, facet: "portco", width: 120 },
  { key: "fiscal_year", label: "Fiscal year", type: "year", source: "db", sql: "fiscal_year", width: 100 },
  { key: "period", label: "Period", type: "pick", source: "db", sql: "period", vocab: "period", facet: "period", width: 90 },
  { key: "stage", label: "Signing stage", type: "pick", source: "db", sql: "stage", vocab: "stage", facet: "stage", width: 150 },
  { key: "executed_date", label: "Executed", type: "date", source: "live", width: 110 },
  { key: "signed_date", label: "Signed date", type: "date", source: "db", sql: "signed_date", width: 110 },
  { key: "effective_date", label: "Effective date", type: "date", source: "db", sql: "effective_date", width: 120 },
  { key: "workstream", label: "Workstream", type: "pick", source: "db", sql: "workstream", vocab: "workstream", facet: "workstream", width: 140 },
  { key: "issuer", label: "Issuer type", type: "pick", source: "db", sql: "issuer", vocab: "issuer", facet: "issuer", width: 120 },
  { key: "tier", label: "Handling", type: "pick", source: "db", sql: "tier", vocab: "tier", facet: "tier", width: 110 },
  { key: "is_primary", label: "Primary copy", type: "flag", source: "db", sql: "is_primary", width: 110 },
  { key: "modified_time", label: "Modified", type: "date", source: "db", sql: "modified_time", width: 110 },
  { key: "file_type_family", label: "File type", type: "pick", source: "db", sql: "file_type_family", facet: "file_type_family", width: 110 },
  { key: "review_status", label: "Review status", type: "pick", source: "live", vocab: "review", width: 130 },
  { key: "file_id", label: "File ID", type: "text", source: "db", sql: "file_id", width: 180 },
  { key: "document_id", label: "Catalog ID", type: "text", source: "db", sql: "document_id::text", width: 110 },
];

export const COLUMN_BY_KEY = new Map(COLUMN_DEFS.map((c) => [c.key, c]));
export const DEFAULT_COLUMNS = ["name", "kind", "entities", "portcos", "fiscal_year", "period", "stage", "tier", "review_status"];
export const PAGE_SIZES = [10, 25, 100] as const;
export const DEFAULT_PAGE_SIZE = 25;

export function isSortable(key: string): boolean {
  const c = COLUMN_BY_KEY.get(key);
  return !!c && c.source === "db";
}
export function isFilterable(key: string): boolean {
  return isSortable(key);
}

/** Filter keys the spec uses for pick columns (kept from v1 so saved views still load). */
export const PICK_FILTER_KEY: Record<string, string> = {
  kind: "kind", entities: "entity", portcos: "portco", period: "period", stage: "stage", workstream: "workstream",
  issuer: "issuer", tier: "tier", file_type_family: "file_type_family",
};
