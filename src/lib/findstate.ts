/**
 * CAT-WO-12 · Find list state as plain functions (no React), so the rules can be unit-tested:
 *  - the text term `search` (URL `?q=`) is one filter among the others: a TEXT chip, counted, removed by Clear all;
 *  - the in-window field sets `search` and keeps every other filter;
 *  - the header (global) search starts fresh: other filters, column filters and the open saved view go;
 *  - a saved view stores its text term; any change to filters, text, columns or sort marks it edited; Revert restores it.
 */
import { COLUMN_BY_KEY, DEFAULT_COLUMNS, DEFAULT_PAGE_SIZE, PAGE_SIZES } from "./columns";
import { display, type VocabList } from "./vocab";

export type Range = { from?: string; to?: string };
export type Filters = Record<string, unknown> & {
  kind?: string[]; entity?: string[]; portco?: string[]; fiscal_year?: string[]; stage?: string[]; tier?: string[];
  period?: string[]; workstream?: string[]; issuer?: string[]; file_type_family?: string[];
  primary_only?: boolean; is_primary?: "yes" | "no"; fy_range?: Range; modified_time?: Range; signed_date?: Range; effective_date?: Range;
  file_id?: string; document_id?: string;
  /** CAT-WO-04 R-029: off by default */
  current_only?: boolean;
};
export type Spec = { filters: Filters; search?: string; sort: { col: string; dir: "asc" | "desc" }; groupBy: string | null; page: number; pageSize: number };
export type Layout = { columns: string[]; widths: Record<string, number> };
/** The saved view open in Find: its id, name, the stored spec (for Revert) and its fingerprint (for "edited"). */
export type Current = { id: number; name: string; spec: Record<string, unknown>; stored: string };

export const EMPTY: Spec = { filters: {}, sort: { col: "modified_time", dir: "desc" }, groupBy: null, page: 0, pageSize: DEFAULT_PAGE_SIZE };
export const DEFAULT_LAYOUT: Layout = { columns: DEFAULT_COLUMNS, widths: {} };
/** Chip key of the text filter (no real filter key can start with "_"). */
export const TEXT_KEY = "_text";

export const FILTER_LABEL: Record<string, string> = {
  [TEXT_KEY]: "Text",
  kind: "Kind", entity: "Entity", portco: "Portco", fiscal_year: "Fiscal year", stage: "Signing stage", tier: "Handling", period: "Period", workstream: "Workstream",
  issuer: "Issuer type", file_type_family: "File type", primary_only: "Primary copy", is_primary: "Primary copy", fy_range: "Fiscal year", modified_time: "Modified",
  signed_date: "Signed date", effective_date: "Effective date", file_id: "File ID", document_id: "Catalog ID",
  current_only: "Current versions only", version_role: "Version", versions: "Versions",
  published_channel: "Published to", published_date: "Posted date", portal_kind_conflict: "Portal kind conflict",
};
export const VOCAB_OF: Record<string, VocabList | undefined> = { kind: "kind", stage: "stage", tier: "tier", period: "period", workstream: "workstream", issuer: "issuer", version_role: "version_role", published_channel: "published_channel" };

export const isActive = (v: unknown) => Array.isArray(v) ? v.length > 0 : v && typeof v === "object" ? Object.values(v).some((x) => x != null && x !== "") : v != null && v !== "" && v !== false;
export const rangeText = (r: Range) => r.from && r.to ? `${r.from} – ${r.to}` : r.from ? `from ${r.from}` : `to ${r.to}`;
const term = (q: string | null | undefined) => (q ?? "").trim() || undefined;

/** spec -> what the server stores / runs. Empty filters dropped; an empty text term dropped. */
export function wire(spec: Spec): Spec {
  const filters: Filters = {};
  for (const [k, v] of Object.entries(spec.filters)) if (isActive(v)) filters[k] = v;
  return { ...spec, filters, search: term(spec.search) };
}

export function fromStored(x: Record<string, unknown>): { spec: Spec; layout: Layout | null } {
  const spec: Spec = {
    filters: (x.filters as Filters) ?? {}, search: term(typeof x.search === "string" ? x.search : undefined),
    sort: (x.sort as Spec["sort"]) ?? EMPTY.sort, groupBy: (x.groupBy as string | null) ?? null, page: 0,
    pageSize: PAGE_SIZES.includes(Number(x.pageSize) as never) ? Number(x.pageSize) : DEFAULT_PAGE_SIZE,
  };
  const cols = Array.isArray(x.columns) ? (x.columns as string[]).filter((c) => COLUMN_BY_KEY.has(c)) : null;
  return { spec, layout: cols?.length ? { columns: cols.includes("name") ? cols : ["name", ...cols], widths: (x.widths as Record<string, number>) ?? {} } : null };
}

/** What a saved view stores for the list as shown: filters, text, sort, grouping, page size and layout. */
export function storedNow(spec: Spec, layout: Layout): Record<string, unknown> {
  return { ...wire(spec), ...layout } as unknown as Record<string, unknown>;
}

/** Normalized form of a stored view, for "edited" detection: active filters, text, default layout filled in. */
export function fingerprint(x: Record<string, unknown>): string {
  const s = fromStored(x);
  const l = s.layout ?? DEFAULT_LAYOUT;
  const w = wire(s.spec);
  const widths = Object.fromEntries(Object.entries(l.widths).filter(([k, v]) => v !== COLUMN_BY_KEY.get(k)?.width).sort());
  return JSON.stringify({ f: Object.fromEntries(Object.entries(w.filters).sort()), q: w.search ?? null, s: w.sort, g: w.groupBy ?? null, p: w.pageSize, c: l.columns, w: widths });
}
export const openView = (id: number, name: string, spec: Record<string, unknown>): Current => ({ id, name, spec, stored: fingerprint(spec) });
export const isEdited = (current: Current | null, spec: Spec, layout: Layout) => !!current && fingerprint(storedNow(spec, layout)) !== current.stored;

// ------------------------------------------------------------------ transitions
/** Header (global) search: start fresh. Only the term remains (page size and columns kept; they are not filters). */
export function headerSearch(s: Spec, q: string): Spec {
  return { ...EMPTY, pageSize: s.pageSize, search: term(q) };
}
/** In-window field: set or clear the term; every other filter stays. Page 1 when the term changes. */
export function setText(s: Spec, q: string): Spec {
  const t = term(q);
  return t === s.search ? s : { ...s, page: 0, search: t };
}
export function setFilter(s: Spec, k: string, v: unknown): Spec {
  if (k === TEXT_KEY) return setText(s, typeof v === "string" ? v : "");
  const f: Filters = { ...s.filters, [k]: v };
  if (k === "is_primary") delete f.primary_only; // one "primary copy" filter at a time
  if (!isActive(v)) delete f[k];
  return { ...s, page: 0, filters: f };
}
/** Clear all: every filter including the text term. */
export function clearAll(s: Spec): Spec {
  return { ...s, page: 0, filters: {}, search: undefined };
}
/** Revert an edited view to what it stores. */
export function revert(c: Current): { spec: Spec; layout: Layout } {
  const s = fromStored(c.spec);
  return { spec: s.spec, layout: s.layout ?? DEFAULT_LAYOUT };
}
/** Start-up text term when Find restores the last state: this tab's own term if it has one, else the open view's. */
export function restoredText(sessionQ: string | null, view: Record<string, unknown> | null): string | undefined {
  if (sessionQ !== null) return term(sessionQ);
  return view && typeof view.search === "string" ? term(view.search) : undefined;
}

// ------------------------------------------------------------------ chips
export type Chip = { key: string; label: string; text: string };
export function chipsOf(spec: Spec): Chip[] {
  const out: Chip[] = [];
  const q = term(spec.search);
  if (q) out.push({ key: TEXT_KEY, label: FILTER_LABEL[TEXT_KEY], text: q });
  for (const [k, v] of Object.entries(spec.filters)) {
    if (!isActive(v)) continue;
    let text: string;
    if (Array.isArray(v)) text = v.map((x) => (VOCAB_OF[k] && x !== "(none)" ? display(VOCAB_OF[k]!, String(x)) : String(x))).join(", ");
    else if (k === "primary_only" || k === "current_only") text = "on";
    else if (k === "is_primary") text = v === "yes" ? "yes" : "no";
    else if (typeof v === "object") text = rangeText(v as Range);
    else text = `contains “${String(v)}”`;
    out.push({ key: k, label: FILTER_LABEL[k] ?? k, text });
  }
  return out;
}

/** Page title: the saved view's name (· edited); "Search results" when the text term is the only filter (a header search); else "Find". */
export function titleOf(current: Current | null, edited: boolean, spec: Spec): { name: string; edited: boolean } {
  if (current) return { name: current.name, edited };
  const onlyText = !!term(spec.search) && !Object.values(spec.filters).some(isActive);
  return { name: onlyText ? "Search results" : "Find", edited: false };
}
