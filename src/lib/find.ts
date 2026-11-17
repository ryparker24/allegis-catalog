/**
 * Find: filters, sort, group-by, paging - all in SQL against app views, server-side.
 * Every identifier comes from a whitelist below; every value is a bind parameter.
 */
export const PAGE_SIZE = 50; // item 0.4: one 50-file Drive batch ~0.5 s

export const COLUMNS = {
  file_id: "file_id", document_id: "document_id", kind: "kind", entities: "entities", portcos: "portcos",
  fiscal_year: "fiscal_year", period: "period", stage: "stage", signed_date: "signed_date", effective_date: "effective_date",
  workstream: "workstream", issuer: "issuer", tier: "tier", is_primary: "is_primary", modified_time: "modified_time",
  file_type_family: "file_type_family", web_view_link: "web_view_link",
} as const;
export type Column = keyof typeof COLUMNS;

export const SORTABLE: Column[] = ["kind", "fiscal_year", "period", "stage", "signed_date", "effective_date", "workstream", "issuer", "tier", "modified_time", "file_type_family", "file_id"];
export const GROUPABLE = ["kind", "entity", "portco", "fiscal_year", "stage", "tier", "workstream"] as const;
export type GroupBy = (typeof GROUPABLE)[number];

export interface FindSpec {
  filters: {
    kind?: string[];
    entity?: string[];
    portco?: string[];
    fiscal_year?: (number | string)[];
    stage?: string[];
    tier?: string[];
    primary_only?: boolean;
  };
  sort?: { col: string; dir: "asc" | "desc" };
  groupBy?: string | null;
  page?: number;
}

export const NONE = "(none)";
const CODE = /^[A-Za-z0-9_.\-() ]{1,64}$/;

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

export interface Built {
  where: string;
  params: unknown[];
}

/** WHERE clause for a spec ($1..$n). */
export function buildWhere(spec: FindSpec): Built {
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
  const fy = codes(f.fiscal_year, "fiscal_year");
  if (fy.length) {
    const years = fy.filter((v) => v !== NONE).map((v) => {
      const n = Number(v);
      if (!Number.isInteger(n) || n < 1990 || n > 2100) throw new SpecError("fiscal_year: bad value");
      return n;
    });
    const ors: string[] = [];
    if (years.length) ors.push(`fiscal_year = ANY(${p(years)}::int[])`);
    if (fy.includes(NONE)) ors.push("fiscal_year IS NULL");
    parts.push(`(${ors.join(" OR ")})`);
  }
  if (f.primary_only === true) parts.push("is_primary IS TRUE");
  return { where: parts.length ? `WHERE ${parts.join(" AND ")}` : "", params };
}

export function orderBy(spec: FindSpec): string {
  const col = (spec.sort?.col ?? "modified_time") as Column;
  if (!SORTABLE.includes(col)) throw new SpecError("sort: column not sortable");
  const dir = spec.sort?.dir === "asc" ? "ASC" : "DESC";
  return `ORDER BY ${COLUMNS[col]} ${dir} NULLS LAST, file_id ASC`; // file_id: stable paging
}

const SELECT_COLS = "file_id, document_id, kind, entities, portcos, fiscal_year, period, stage, signed_date, effective_date, workstream, issuer, tier, is_primary, modified_time, file_type_family";

export function pageQuery(spec: FindSpec, view = "app.v_find"): Built & { sql: string; countSql: string; page: number } {
  const { where, params } = buildWhere(spec);
  const page = Math.max(0, Math.min(10_000, Math.floor(Number(spec.page ?? 0)) || 0));
  return {
    where, params, page,
    sql: `SELECT ${SELECT_COLS} FROM ${view} ${where} ${orderBy(spec)} LIMIT ${PAGE_SIZE} OFFSET ${page * PAGE_SIZE}`,
    countSql: `SELECT count(*)::int AS n FROM ${view} ${where}`,
  };
}

/** Group counts over the WHOLE filtered set (not just the page). */
export function groupQuery(spec: FindSpec): (Built & { sql: string }) | null {
  const g = spec.groupBy;
  if (!g) return null;
  if (!(GROUPABLE as readonly string[]).includes(g)) throw new SpecError("groupBy: not groupable");
  const { where, params } = buildWhere(spec);
  const expr = g === "entity" ? "unnest(CASE WHEN cardinality(entities)=0 THEN ARRAY[NULL::text] ELSE entities END)"
    : g === "portco" ? "unnest(CASE WHEN cardinality(portcos)=0 THEN ARRAY[NULL::text] ELSE portcos END)"
    : g === "fiscal_year" ? "fiscal_year::text" : g;
  return { where, params, sql: `SELECT coalesce(g, '${NONE}') AS value, count(*)::int AS n FROM (SELECT ${expr} AS g FROM app.v_find ${where}) x GROUP BY 1 ORDER BY 2 DESC LIMIT 500` };
}

export const EXPORT_LIMIT = 50_000;
/** CSV export: codes and Drive links only - no names. */
export function exportQuery(spec: FindSpec): Built & { sql: string } {
  const { where, params } = buildWhere(spec);
  return { where, params, sql: `SELECT file_id, document_id, kind, entities, portcos, fiscal_year, period, stage, signed_date, tier, is_primary, web_view_link FROM app.v_find ${where} ${orderBy(spec)} LIMIT ${EXPORT_LIMIT}` };
}

export function toCsv(rows: Record<string, unknown>[], cols: string[]): string {
  const cell = (v: unknown) => {
    let s = Array.isArray(v) ? v.join("|") : v instanceof Date ? v.toISOString().slice(0, 10) : v == null ? "" : String(v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; // spreadsheet formula injection
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => cell(r[c])).join(","))].join("\r\n") + "\r\n";
}

export function parseSpec(x: unknown): FindSpec {
  const o = (x ?? {}) as Record<string, unknown>;
  const spec: FindSpec = {
    filters: (o.filters ?? {}) as FindSpec["filters"],
    sort: o.sort as FindSpec["sort"],
    groupBy: (o.groupBy as string | null) ?? null,
    page: Number(o.page ?? 0),
  };
  buildWhere(spec); orderBy(spec); groupQuery(spec); // validate eagerly (throws SpecError)
  return spec;
}

export const SEED_VIEWS: { name: string; sort: number; spec: FindSpec & { columns?: string[] } }[] = [
  // Designs v0.1. All four carry "primary copy only".
  // "MTV-II · FY2025 close": no workstream filter. ref.vocab(workstream) has no single close/financial-reporting
  // code (candidates: reporting, regulatory, accounting [legacy]), so per the follow-up order it is left off.
  { name: "ACCSO · subscription docs", sort: 1, spec: { filters: { kind: ["subscription_agreement"], entity: ["ACCSO"], primary_only: true }, sort: { col: "signed_date", dir: "desc" } } },
  { name: "MTV-II · FY2025 close", sort: 2, spec: { filters: { entity: ["MTV-II"], fiscal_year: ["2025"], primary_only: true }, sort: { col: "modified_time", dir: "desc" }, groupBy: "kind" } },
  { name: "Unsigned side letters", sort: 3, spec: { filters: { kind: ["side_letter"], stage: ["draft", "final_unexecuted", "partially_executed"], primary_only: true }, sort: { col: "modified_time", dir: "desc" }, groupBy: "stage" } },
  { name: "K-1s · tax year 2025", sort: 4, spec: { filters: { kind: ["k1"], fiscal_year: ["2025"], primary_only: true }, sort: { col: "modified_time", dir: "desc" }, groupBy: "entity" } },
];
