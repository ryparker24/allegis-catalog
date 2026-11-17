/**
 * Find: filters, column filters, search, sort, group-by, paging - all in SQL against app views, server-side.
 * Every identifier comes from a whitelist (src/lib/columns.ts); every value is a bind parameter.
 */
import { COLUMN_BY_KEY, COLUMN_DEFS, DEFAULT_PAGE_SIZE, PAGE_SIZES, PICK_FILTER_KEY, isSortable } from "./columns";
import { VOCAB } from "./vocab";

/** v1 page size; kept for the Review queue (its route imports it). Find uses spec.pageSize. */
export const PAGE_SIZE = 50;

export const GROUPABLE = ["kind", "entity", "portco", "fiscal_year", "stage", "tier", "workstream"] as const;
export type GroupBy = (typeof GROUPABLE)[number];

export type Range = { from?: string | number | null; to?: string | number | null };
export type Flag = "yes" | "no";

export interface FindSpec {
  filters: {
    // pick-list (multi-select of codes); keys kept from v1
    kind?: string[];
    entity?: string[];
    portco?: string[];
    fiscal_year?: (number | string)[];
    stage?: string[];
    tier?: string[];
    period?: string[];
    workstream?: string[];
    issuer?: string[];
    file_type_family?: string[];
    // v1 "primary copy only" (kept); same as is_primary = "yes"
    primary_only?: boolean;
    // column filters by type (item 2)
    is_primary?: Flag;
    fy_range?: Range;
    modified_time?: Range;
    signed_date?: Range;
    effective_date?: Range;
    file_id?: string;
    document_id?: string;
  };
  search?: string;
  sort?: { col: string; dir: "asc" | "desc" };
  groupBy?: string | null;
  page?: number;
  pageSize?: number;
}

export const NONE = "(none)";
const CODE = /^[A-Za-z0-9_.\-() ]{1,64}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export class SpecError extends Error {}

function codes(x: unknown, field: string, max = 200): string[] {
  if (x == null) return [];
  if (!Array.isArray(x)) throw new SpecError(`${field}: not a list`);
  if (x.length > max) throw new SpecError(`${field}: too many values`);
  return x.map((v) => {
    const s = String(v);
    if (!CODE.test(s)) throw new SpecError(`${field}: bad value`);
    return s;
  });
}
function year(v: unknown, field: string): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!Number.isInteger(n) || n < 1990 || n > 2100) throw new SpecError(`${field}: bad value`);
  return n;
}
function isoDate(v: unknown, field: string): string | null {
  if (v == null || v === "") return null;
  const s = String(v);
  if (!ISO_DATE.test(s) || isNaN(Date.parse(s))) throw new SpecError(`${field}: bad date`);
  return s;
}
function contains(v: unknown, field: string): string | null {
  if (v == null || v === "") return null;
  const s = String(v).trim();
  if (s.length > 100 || /[\u0000-\u001f]/.test(s)) throw new SpecError(`${field}: bad value`);
  return s || null;
}
const likeEscape = (s: string) => s.replace(/[\\%_]/g, (m) => "\\" + m);

export function parseSearch(x: unknown): string | null {
  if (x == null || x === "") return null;
  const s = String(x).trim();
  if (s.length > 100 || /[\u0000-\u001f]/.test(s)) throw new SpecError("search: bad value");
  return s || null;
}

/** Kind codes whose plain-words meaning contains the search term ("schedule" finds k1 via "K-1"? no - only labels). */
export function kindsMatching(term: string): string[] {
  const t = term.toLowerCase();
  return Object.entries(VOCAB.kind).filter(([code, label]) => code.toLowerCase().includes(t) || label.toLowerCase().includes(t)).map(([c]) => c);
}

export interface Built {
  where: string;
  params: unknown[];
}
export interface WhereOpts {
  /** file ids whose NAME matches the search, found by a Drive search as the user (names never reach the DB) */
  nameIds?: string[];
}

/** WHERE clause for a spec ($1..$n). */
export function buildWhere(spec: FindSpec, opts: WhereOpts = {}): Built {
  const f = spec.filters ?? {};
  const params: unknown[] = [];
  const parts: string[] = [];
  const p = (v: unknown) => { params.push(v); return `$${params.length}`; };

  const scalarIn = (col: string, vals: string[]) => {
    const real = vals.filter((v) => v !== NONE);
    const ors: string[] = [];
    if (real.length) ors.push(`${col} = ANY(${p(real)}::text[])`);
    if (vals.includes(NONE)) ors.push(`${col} IS NULL`);
    if (ors.length) parts.push(`(${ors.join(" OR ")})`);
  };
  const arrayAny = (col: string, vals: string[]) => {
    const real = vals.filter((v) => v !== NONE);
    const ors: string[] = [];
    if (real.length) ors.push(`${col} && ${p(real)}::text[]`);
    if (vals.includes(NONE)) ors.push(`cardinality(${col}) = 0`);
    if (ors.length) parts.push(`(${ors.join(" OR ")})`);
  };

  scalarIn("kind", codes(f.kind, "kind"));
  arrayAny("entities", codes(f.entity, "entity"));
  arrayAny("portcos", codes(f.portco, "portco"));
  scalarIn("stage", codes(f.stage, "stage"));
  scalarIn("tier", codes(f.tier, "tier"));
  scalarIn("period", codes(f.period, "period"));
  scalarIn("workstream", codes(f.workstream, "workstream"));
  scalarIn("issuer", codes(f.issuer, "issuer"));
  scalarIn("file_type_family", codes(f.file_type_family, "file_type_family"));

  const fy = codes(f.fiscal_year, "fiscal_year");
  if (fy.length) {
    const years = fy.filter((v) => v !== NONE).map((v) => year(v, "fiscal_year")!);
    const ors: string[] = [];
    if (years.length) ors.push(`fiscal_year = ANY(${p(years)}::int[])`);
    if (fy.includes(NONE)) ors.push("fiscal_year IS NULL");
    parts.push(`(${ors.join(" OR ")})`);
  }
  if (f.fy_range) {
    const a = year(f.fy_range.from, "fy_range"), b = year(f.fy_range.to, "fy_range");
    if (a != null) parts.push(`fiscal_year >= ${p(a)}::int`);
    if (b != null) parts.push(`fiscal_year <= ${p(b)}::int`);
  }
  for (const col of ["modified_time", "signed_date", "effective_date"] as const) {
    const r = f[col];
    if (!r) continue;
    const a = isoDate(r.from, col), b = isoDate(r.to, col);
    if (a) parts.push(`${col} >= ${p(a)}::date`);
    if (b) parts.push(`${col} < (${p(b)}::date + 1)`);
  }
  if (f.primary_only === true) parts.push("is_primary IS TRUE");
  if (f.is_primary != null) {
    if (f.is_primary === "yes") parts.push("is_primary IS TRUE");
    else if (f.is_primary === "no") parts.push("is_primary IS NOT TRUE");
    else throw new SpecError("is_primary: bad value");
  }
  const fid = contains(f.file_id, "file_id");
  if (fid) parts.push(`file_id ILIKE ${p("%" + likeEscape(fid) + "%")}`);
  const did = contains(f.document_id, "document_id");
  if (did) parts.push(`document_id::text ILIKE ${p("%" + likeEscape(did) + "%")}`);

  const term = parseSearch(spec.search);
  if (term) {
    const like = p("%" + likeEscape(term) + "%");
    const ors = [
      `kind ILIKE ${like}`,
      `EXISTS (SELECT 1 FROM unnest(entities) e WHERE e ILIKE ${like})`,
      `EXISTS (SELECT 1 FROM unnest(portcos) pc WHERE pc ILIKE ${like})`,
    ];
    const kinds = kindsMatching(term);
    if (kinds.length) ors.push(`kind = ANY(${p(kinds)}::text[])`);
    const ids = (opts.nameIds ?? []).filter((x) => /^[A-Za-z0-9_-]{10,128}$/.test(x));
    if (ids.length) ors.push(`file_id = ANY(${p(ids)}::text[])`);
    parts.push(`(${ors.join(" OR ")})`);
  }
  return { where: parts.length ? `WHERE ${parts.join(" AND ")}` : "", params };
}

export function orderBy(spec: FindSpec): string {
  const col = spec.sort?.col ?? "modified_time";
  if (!isSortable(col)) throw new SpecError("sort: column not sortable");
  const expr = col === "document_id" ? "document_id" : COLUMN_BY_KEY.get(col)!.sql!;
  const dir = spec.sort?.dir === "asc" ? "ASC" : "DESC";
  return `ORDER BY ${expr} ${dir} NULLS LAST, file_id ASC`; // file_id: stable paging
}

export function pageSizeOf(spec: FindSpec): number {
  const n = Number(spec.pageSize ?? DEFAULT_PAGE_SIZE);
  return (PAGE_SIZES as readonly number[]).includes(n) ? n : DEFAULT_PAGE_SIZE;
}

const SELECT_COLS = "file_id, document_id, kind, entities, portcos, fiscal_year, period, stage, signed_date, effective_date, workstream, issuer, tier, is_primary, modified_time, file_type_family";

export function pageQuery(spec: FindSpec, view = "app.v_find", opts: WhereOpts = {}): Built & { sql: string; countSql: string; page: number; pageSize: number } {
  const { where, params } = buildWhere(spec, opts);
  const pageSize = pageSizeOf(spec);
  const page = Math.max(0, Math.min(100_000, Math.floor(Number(spec.page ?? 0)) || 0));
  return {
    where, params, page, pageSize,
    sql: `SELECT ${SELECT_COLS} FROM ${view} ${where} ${orderBy(spec)} LIMIT ${pageSize} OFFSET ${page * pageSize}`,
    countSql: `SELECT count(*)::int AS n FROM ${view} ${where}`,
  };
}

/** Group counts over the WHOLE filtered set (not just the page). */
export function groupQuery(spec: FindSpec, opts: WhereOpts = {}): (Built & { sql: string }) | null {
  const g = spec.groupBy;
  if (!g) return null;
  if (!(GROUPABLE as readonly string[]).includes(g)) throw new SpecError("groupBy: not groupable");
  const { where, params } = buildWhere(spec, opts);
  const expr = g === "entity" ? "unnest(CASE WHEN cardinality(entities)=0 THEN ARRAY[NULL::text] ELSE entities END)"
    : g === "portco" ? "unnest(CASE WHEN cardinality(portcos)=0 THEN ARRAY[NULL::text] ELSE portcos END)"
    : g === "fiscal_year" ? "fiscal_year::text" : g;
  return { where, params, sql: `SELECT coalesce(g, '${NONE}') AS value, count(*)::int AS n FROM (SELECT ${expr} AS g FROM app.v_find ${where}) x GROUP BY 1 ORDER BY 2 DESC LIMIT 500` };
}

export const EXPORT_LIMIT = 50_000;
/** Excel is built in Worker memory (~85 bytes of XML per cell): capped well under the 128 MB isolate limit. */
export const XLSX_LIMIT = 10_000;
export const EXPORT_COLS = ["file_id", "document_id", "kind", "entities", "portcos", "fiscal_year", "period", "stage", "signed_date", "effective_date", "workstream", "tier", "is_primary", "modified_time", "web_view_link"];
/** CSV / Excel export: codes and Drive links only - no names. */
export function exportQuery(spec: FindSpec, opts: WhereOpts = {}, limit = EXPORT_LIMIT): Built & { sql: string } {
  const { where, params } = buildWhere(spec, opts);
  return { where, params, sql: `SELECT ${EXPORT_COLS.join(", ")} FROM app.v_find ${where} ${orderBy(spec)} LIMIT ${Math.max(1, Math.min(EXPORT_LIMIT, Math.floor(limit)))}` };
}

export function exportCell(v: unknown): string {
  return Array.isArray(v) ? v.join("|") : v instanceof Date ? v.toISOString().slice(0, 10) : v == null ? "" : String(v);
}
export function toCsv(rows: Record<string, unknown>[], cols: string[]): string {
  const cell = (v: unknown) => {
    let s = exportCell(v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; // spreadsheet formula injection
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => cell(r[c])).join(","))].join("\r\n") + "\r\n";
}

/** UI-only parts of a view, stored with it (item 2): visible columns, order, widths. */
export interface ViewLayout {
  columns?: string[];
  widths?: Record<string, number>;
}
export function parseLayout(x: unknown): ViewLayout {
  const o = (x ?? {}) as Record<string, unknown>;
  const out: ViewLayout = {};
  if (Array.isArray(o.columns)) {
    const seen = new Set<string>();
    out.columns = o.columns.map(String).filter((c) => COLUMN_BY_KEY.has(c) && !seen.has(c) && (seen.add(c), true)).slice(0, COLUMN_DEFS.length);
  }
  if (o.widths && typeof o.widths === "object") {
    out.widths = {};
    for (const [k, v] of Object.entries(o.widths as Record<string, unknown>)) {
      const n = Math.round(Number(v));
      if (COLUMN_BY_KEY.has(k) && Number.isFinite(n)) out.widths[k] = Math.max(60, Math.min(900, n));
    }
  }
  return out;
}

const FILTER_KEYS = new Set([
  ...Object.values(PICK_FILTER_KEY), "fiscal_year", "primary_only", "is_primary", "fy_range", "modified_time", "signed_date", "effective_date", "file_id", "document_id",
]);

export function parseSpec(x: unknown): FindSpec {
  const o = (x ?? {}) as Record<string, unknown>;
  const filters = (o.filters ?? {}) as Record<string, unknown>;
  if (typeof filters !== "object" || Array.isArray(filters)) throw new SpecError("filters: not an object");
  for (const k of Object.keys(filters)) if (!FILTER_KEYS.has(k)) throw new SpecError(`filters: unknown key ${k.slice(0, 40).replace(/[^a-z_]/gi, "")}`);
  // rebuild nested objects so nothing beyond the known shape is ever stored (coder review #5)
  const clean: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(filters)) {
    clean[k] = v && typeof v === "object" && !Array.isArray(v) ? { from: (v as Range).from ?? undefined, to: (v as Range).to ?? undefined } : v;
  }
  const so = o.sort as { col?: unknown; dir?: unknown } | undefined;
  const spec: FindSpec = {
    filters: clean as FindSpec["filters"],
    search: parseSearch(o.search) ?? undefined,
    sort: so ? { col: String(so.col ?? ""), dir: so.dir === "asc" ? "asc" : "desc" } : undefined,
    groupBy: (o.groupBy as string | null) ?? null,
    page: Number(o.page ?? 0),
    pageSize: o.pageSize == null ? undefined : Number(o.pageSize),
  };
  buildWhere(spec); orderBy(spec); groupQuery(spec); // validate eagerly (throws SpecError)
  return spec;
}

export const SEED_FOLDERS: { name: string; sort: number }[] = [
  { name: "Tax", sort: 1 }, { name: "Agreements", sort: 2 }, { name: "Close", sort: 3 },
];

export const SEED_VIEWS: { name: string; sort: number; folder: string; spec: FindSpec & ViewLayout }[] = [
  // Designs v0.1. All four carry "primary copy only".
  // "MTV-II · FY2025 close": no workstream filter. ref.vocab(workstream) has no single close/financial-reporting
  // code (candidates: reporting, regulatory, accounting [legacy]), so per the follow-up order it is left off.
  { name: "ACCSO · subscription docs", sort: 1, folder: "Agreements", spec: { filters: { kind: ["subscription_agreement"], entity: ["ACCSO"], primary_only: true }, sort: { col: "signed_date", dir: "desc" } } },
  { name: "MTV-II · FY2025 close", sort: 2, folder: "Close", spec: { filters: { entity: ["MTV-II"], fiscal_year: ["2025"], primary_only: true }, sort: { col: "modified_time", dir: "desc" }, groupBy: "kind" } },
  { name: "Unsigned side letters", sort: 3, folder: "Agreements", spec: { filters: { kind: ["side_letter"], stage: ["draft", "final_unexecuted", "partially_executed"], primary_only: true }, sort: { col: "modified_time", dir: "desc" }, groupBy: "stage" } },
  { name: "K-1s · tax year 2025", sort: 4, folder: "Tax", spec: { filters: { kind: ["k1"], fiscal_year: ["2025"], primary_only: true }, sort: { col: "modified_time", dir: "desc" }, groupBy: "entity" } },
];
