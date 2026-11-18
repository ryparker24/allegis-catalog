/**
 * CAT-WO-03 item 5 · Checklists: requirements (app.v_requirement, the nightly build with the latest person override
 * applied), summary counts, the Gaps matrix, and overrides (link / not required / clear; append-only).
 * Every filter and sort is whitelisted and bound. The best-document cell obeys the live Drive check as the user
 * (R-020 condition 1): a file the user can't open shows "on file (no access)" with its result, but no name or link.
 */
import type { Db } from "./db";
import type { Session } from "./session";
import { driveBatchGet, FILE_ID_RE, isTransient, type FetchLike } from "./google";
import { decodeLabels, INCLUDE_LABELS } from "./labels";
import { logEvent } from "./log";

export const RULES = [
  { id: "LP-SUB", checklist: "lp_subscriptions", title: "LP subscription agreements", subtype: "OFF-03", subject: "entity_partner" },
  { id: "LP-SIDE", checklist: "lp_subscriptions", title: "Side letters", subtype: "OFF-05", subject: "entity_partner" },
  { id: "GP-COMMIT", checklist: "lp_subscriptions", title: "GP commitment", subtype: "OFF-04", subject: "entity_partner" },
  { id: "AUDITED-FS", checklist: "fund_level", title: "Audited financial statements", subtype: "AUD-01", subject: "entity_fy" },
  { id: "K1-SET", checklist: "fund_level", title: "K-1 set", subtype: "AUD-03", subject: "entity_partner_fy" },
  { id: "PCAP-Q", checklist: "fund_level", title: "PCAP (quarterly capital statements)", subtype: null, subject: "entity_partner_quarter" },
] as const;
export const RULE_IDS: readonly string[] = RULES.map((r) => r.id);
export const RESULTS = ["missing", "on_file", "none_found", "met", "not_required", "no_roster", "applicability_not_set"] as const;
const SORT: Record<string, string> = {
  urgency: "urgency", entity: "entity_code", partner: "partner_code", period: "fiscal_year", result: "result",
  best_date: "best_date", candidates: "n_candidates", kind: "best_kind",
};
export const SORTABLE = Object.keys(SORT);
const ENT = /^[A-Za-z0-9()_ -]{1,40}$/;
export const REQ_KEY = /^[A-Z0-9-]{2,20}\|[A-Za-z0-9()_ -]{1,40}\|[A-Z0-9-]{0,20}\|[0-9]{0,4}\|(Q[1-4])?$/;
export const PAGE_SIZES = [10, 25, 100];

export class SpecError extends Error {}
export interface ChecklistSpec {
  rule: string; entity: string | null; fy: number | null; q: number | null; results: string[];
  sort: { col: string; dir: "asc" | "desc" }; page: number; pageSize: number;
}

export function parseChecklistSpec(u: URLSearchParams): ChecklistSpec {
  const rule = u.get("rule") ?? "LP-SUB";
  if (!RULE_IDS.includes(rule)) throw new SpecError("rule");
  const entity = u.get("entity") || null;
  if (entity && !ENT.test(entity)) throw new SpecError("entity");
  const fy = u.get("fy") ? Number(u.get("fy")) : null;
  if (fy !== null && !(Number.isInteger(fy) && fy >= 1990 && fy <= 2100)) throw new SpecError("fy");
  const q = u.get("q") ? Number(u.get("q")) : null;
  if (q !== null && ![1, 2, 3, 4].includes(q)) throw new SpecError("q");
  const results = (u.get("result") ?? "").split(",").filter(Boolean);
  if (!results.every((r) => (RESULTS as readonly string[]).includes(r))) throw new SpecError("result");
  const col = u.get("sort") ?? "urgency";
  if (!SORTABLE.includes(col)) throw new SpecError("sort");
  const pageSize = Number(u.get("pageSize") ?? 25);
  if (!PAGE_SIZES.includes(pageSize)) throw new SpecError("pageSize");
  const page = Math.max(0, Math.min(10_000, Number(u.get("page") ?? 0) || 0));
  return { rule, entity, fy, q, results, sort: { col, dir: u.get("dir") === "desc" ? "desc" : "asc" }, page, pageSize };
}

export function checklistQuery(s: ChecklistSpec): { sql: string; countsSql: string; params: unknown[]; scopeParams: unknown[] } {
  const params: unknown[] = [];
  const p = (v: unknown) => { params.push(v); return `$${params.length}`; };
  const scope = [`r.rule_id = ${p(s.rule)}`];
  if (s.entity) scope.push(`r.entity_code = ${p(s.entity)}`);
  if (s.fy !== null) scope.push(`r.fiscal_year = ${p(s.fy)}`);
  if (s.q !== null) scope.push(`r.fiscal_quarter = ${p(s.q)}`);
  const scopeParams = [...params];
  const where = [...scope];
  if (s.results.length) where.push(`r.result = ANY(${p(s.results)}::text[])`);
  const dir = s.sort.dir === "desc" ? "DESC NULLS LAST" : "ASC NULLS LAST";
  const order = `${SORT[s.sort.col]} ${dir}, urgency, entity_code, partner_code NULLS FIRST, fiscal_year, fiscal_quarter`;
  return {
    params, scopeParams,
    // names: app.v_party only (display name beside the code; to the screen, never logged)
    sql: `SELECT r.req_key, r.rule_id, r.entity_code, r.partner_code, r.fiscal_year, r.fiscal_quarter, r.result, r.sub_status, r.urgency,
                 r.best_file_id, r.best_kind, r.best_stage, r.best_status, r.best_date, r.best_reason, r.best_source, r.best_out_of_scope,
                 r.n_candidates, r.override_action, r.override_note, r.override_by, r.override_at,
                 (SELECT v.display_name FROM app.v_party v WHERE v.entity_code = r.entity_code AND v.partner_code = r.partner_code LIMIT 1) AS partner_name,
                 count(*) OVER ()::int AS matched
          FROM app.v_requirement r WHERE ${where.join(" AND ")}
          ORDER BY ${order} LIMIT ${s.pageSize} OFFSET ${s.page * s.pageSize}`,
    countsSql: `SELECT r.result, count(*)::int AS n FROM app.v_requirement r WHERE ${scope.join(" AND ")} GROUP BY r.result`,
  };
}

/** Gaps matrix for a fund-level rule: entity x period cells with counts by result. */
export function gapsQuery(rule: string, entity: string | null): { sql: string; params: unknown[] } {
  if (!RULE_IDS.includes(rule)) throw new SpecError("rule");
  if (entity && !ENT.test(entity)) throw new SpecError("entity");
  const params: unknown[] = [rule];
  const ent = entity ? (params.push(entity), ` AND entity_code = $${params.length}`) : "";
  return {
    params,
    sql: `SELECT entity_code, fiscal_year, fiscal_quarter, result, count(*)::int AS n
          FROM app.v_requirement WHERE rule_id = $1${ent}
          GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3`,
  };
}

/** The remembered Checklists state per user (app.user_pref 'checklists'): whitelisted, null when invalid. */
export const CHECKLIST_COLUMNS = ["requirement", "result", "best", "kind", "stage", "date", "why", "candidates"];
export function checklistPref(x: unknown): Record<string, unknown> | null {
  const o = (x ?? {}) as Record<string, unknown>;
  try {
    const u = new URLSearchParams();
    for (const k of ["rule", "entity", "fy", "q", "sort", "dir", "pageSize"]) if (o[k] != null && o[k] !== "") u.set(k, String(o[k]));
    if (Array.isArray(o.results)) u.set("result", (o.results as unknown[]).map(String).join(","));
    const s = parseChecklistSpec(u);
    const widths: Record<string, number> = {};
    for (const [k, v] of Object.entries((o.widths ?? {}) as Record<string, unknown>)) {
      const n = Math.round(Number(v));
      if (CHECKLIST_COLUMNS.includes(k) && Number.isFinite(n)) widths[k] = Math.max(60, Math.min(900, n));
    }
    const tab = o.tab === "gaps" ? "gaps" : "rows";
    return { rule: s.rule, entity: s.entity, fy: s.fy, q: s.q, results: s.results, sort: s.sort.col, dir: s.sort.dir, pageSize: s.pageSize, widths, tab };
  } catch { return null; }
}

// ------------------------------------------------------------------ live access on the best document
export type Access = { state: "ok"; name: string; link: string } | { state: "no_access" } | { state: "check_failed" } | { state: "out_of_scope" };

/** Drive files.get AS THE USER for the visible best documents; secret tier (live) is treated as no access. */
export async function accessFor(token: string, ids: string[], f?: FetchLike): Promise<{ map: Map<string, Access>; expired: boolean }> {
  const map = new Map<string, Access>();
  const uniq = [...new Set(ids.filter((x) => FILE_ID_RE.test(x)))];
  let unauth = 0;
  for (let i = 0; i < uniq.length; i += 100) {
    const chunk = uniq.slice(i, i + 100);
    const m = await driveBatchGet(token, chunk, { fields: "id,name,webViewLink,labelInfo", includeLabels: INCLUDE_LABELS }, f);
    for (const id of chunk) {
      const it = m.get(id);
      if (!it) { map.set(id, { state: "check_failed" }); continue; }
      if (it.status === 200 && it.body) {
        const live = decodeLabels(it.body.labelInfo as never);
        if (live.tier === "secret") map.set(id, { state: "no_access" });
        else map.set(id, { state: "ok", name: String(it.body.name ?? ""), link: String(it.body.webViewLink ?? "") });
        continue;
      }
      if (it.status === 401) { unauth++; map.set(id, { state: "check_failed" }); continue; }
      map.set(id, isTransient(it) ? { state: "check_failed" } : { state: "no_access" });
    }
  }
  return { map, expired: uniq.length > 0 && unauth === uniq.length };
}

/** What the browser gets for a best / candidate document: the name and link ONLY when the live check passed. */
export function shownDoc(fileId: string | null, a: Access | undefined, outOfScope = false) {
  if (!fileId) return null;
  if (outOfScope) return { access: "out_of_scope" as const };
  if (!a || a.state !== "ok") return { access: (a?.state ?? "check_failed") as "no_access" | "check_failed" };
  return { access: "ok" as const, file_id: fileId, name: a.name, link: a.link };
}

// ------------------------------------------------------------------ overrides (append-only)
type Out = { status: number; body: Record<string, unknown> };
export async function overrideWrite(body: unknown, ctx: { session: Session; db: Db; fetch?: FetchLike }): Promise<Out> {
  const o = (body ?? {}) as Record<string, unknown>;
  const key = String(o.req_key ?? "");
  if (!REQ_KEY.test(key)) return { status: 400, body: { error: "bad_input", reason: "req_key" } };
  const action = String(o.action ?? "");
  if (!["link", "not_required", "clear"].includes(action)) return { status: 400, body: { error: "bad_input", reason: "action" } };
  const note = o.note == null || o.note === "" ? null : String(o.note);
  if (note !== null && note.length > 2000) return { status: 400, body: { error: "bad_input", reason: "note_too_long" } };
  if (action === "not_required" && !note?.trim()) return { status: 400, body: { error: "bad_input", reason: "reason_required" } };
  const req = await ctx.db.rows<{ override_action: string | null }>("SELECT override_action FROM app.v_requirement WHERE req_key = $1", [key]);
  if (!req.length) return { status: 404, body: { error: "not_found" } };
  if (action === "clear" && !req[0].override_action) return { status: 400, body: { error: "bad_input", reason: "nothing_to_clear" } };
  let fileId: string | null = null, docId: string | null = null;
  if (action === "link") {
    fileId = String(o.file_id ?? "");
    if (!FILE_ID_RE.test(fileId)) return { status: 400, body: { error: "bad_input", reason: "file_id" } };
    const f = await ctx.db.rows<{ document_id: string | null }>("SELECT document_id::text AS document_id FROM app.v_find_x WHERE file_id = $1", [fileId]);
    if (!f.length) return { status: 403, body: { error: "no_access" } };       // one answer for out of scope / can't open
    const acc = await accessFor(ctx.session.at, [fileId], ctx.fetch);
    if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
    if (acc.map.get(fileId)?.state !== "ok") return { status: 403, body: { error: "no_access" } };
    docId = f[0].document_id;
  }
  await ctx.db.exec(
    `INSERT INTO app.requirement_override (req_key, action, file_id, document_id, note, by_email) VALUES ($1, $2, $3, $4::bigint, $5, $6)`,
    [key, action, fileId, docId, note, ctx.session.email.toLowerCase()]);
  logEvent("checklist_override", { outcome: "ok", action, rule_id: key.split("|")[0], file_id: fileId ?? undefined });
  return { status: 200, body: { ok: true } };
}
