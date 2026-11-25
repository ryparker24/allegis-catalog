import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { accessFor, checklistQuery, parseChecklistSpec, RULES, shownDoc, SpecError } from "@/lib/checklists";
import { canWrite } from "@/lib/session";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/**
 * GET /api/checklists?rule=&entity=&fy=&q=&cadence=&result=a,b&sort=&dir=&page=&pageSize=
 *   -> rules, entities in scope, summary counts, one page of requirements. The best document of each row is checked
 *      live as the user: name + link only when the user can open it ("on file (no access)" otherwise).
 */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "checklists" });
  if (!g.ok) return g.response;
  let s;
  try { s = parseChecklistSpec(new URL(req.url).searchParams); }
  catch (e) { return json({ error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid" }, 400); }
  const D = db(env);
  const q = checklistQuery(s);
  const [rows, counts, ents, periods] = await Promise.all([
    D.rows<Record<string, unknown> & { best_file_id: string | null; best_out_of_scope: boolean; matched: number }>(q.sql, q.params),
    D.rows<{ result: string; n: number }>(q.countsSql, q.scopeParams),
    D.rows<{ entity_code: string; cadence: string | null }>("SELECT DISTINCT entity_code, cadence FROM app.v_requirement WHERE rule_id = $1 ORDER BY 1", [s.rule]),
    D.rows<{ fiscal_year: number | null; fiscal_quarter: number | null }>("SELECT DISTINCT fiscal_year, fiscal_quarter FROM app.v_requirement WHERE rule_id = $1 ORDER BY 1, 2", [s.rule]),
  ]);
  const acc = await accessFor(g.session.at, rows.map((r) => r.best_file_id).filter((x): x is string => !!x));
  if (acc.expired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  const out = rows.map(({ matched: _m, best_file_id, best_out_of_scope, ...r }) => ({ ...r, best: shownDoc(best_file_id, best_file_id ? acc.map.get(best_file_id) : undefined, best_out_of_scope) }));
  const noAccess = out.filter((r) => r.best && r.best.access !== "ok").length;
  logEvent("checklists_page", { rule_id: s.rule, page: s.page, count: out.length, dropped_no_access: noAccess });
  return json({
    rules: RULES, spec: s, entities: ents.map((e) => e.entity_code),
    // CAT-WO-13: the entity's cadence for a rule with one (PCAP-Q); empty otherwise
    cadences: Object.fromEntries(ents.filter((e) => e.cadence).map((e) => [e.entity_code, e.cadence])),
    years: [...new Set(periods.map((p) => p.fiscal_year).filter((y): y is number => y != null))],
    quarters: periods.some((p) => p.fiscal_quarter != null),
    // matched from the scope counts (a page past the end must not read as an empty scope: coder review)
    counts: Object.fromEntries(counts.map((c) => [c.result, c.n])),
    matched: counts.filter((c) => !s.results.length || s.results.includes(c.result)).reduce((a, c) => a + c.n, 0),
    rows: out, canWrite: canWrite(g.session),
  });
}
