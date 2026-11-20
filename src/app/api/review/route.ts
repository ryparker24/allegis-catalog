import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { SpecError } from "@/lib/find";
import { parseReviewSpec, reviewQuery } from "@/lib/reviewq";
import { liveCheck, type DbRow } from "@/lib/live";
import { present } from "@/lib/present";
import { canWrite } from "@/lib/session";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/**
 * GET /api/review?page=N&skip=id,id[&spec=<json>][&lane=a,b]  ->  counters + one live-checked page of the queue.
 * spec (CAT-WO-02 item 2): Find's filters, a whitelisted sort and pageSize 10/25/100; lane = queue reasons. All in SQL.
 */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "review" });
  if (!g.ok) return g.response;
  const u = new URL(req.url);
  const page = Math.max(0, Math.min(10_000, Number(u.searchParams.get("page") ?? 0) || 0));
  const skip = (u.searchParams.get("skip") ?? "").split(",").filter((s) => /^[A-Za-z0-9_-]{10,128}$/.test(s)).slice(0, 500);
  let rs;
  try {
    rs = parseReviewSpec(u.searchParams.get("spec"), u.searchParams.get("lane"));
  } catch (e) {
    return json({ error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid" }, 400);
  }
  const D = db(env);
  let PAGE_SIZE = 50;
  const query = (pg: number) => {
    const q = reviewQuery(rs, skip, pg);
    PAGE_SIZE = q.pageSize;
    return D.rows<DbRow>(q.sql, q.params);
  };
  // CAT-WO-04: + proposed version families waiting in the "Link versions" lane
  const countsP = D.rows("SELECT c.*, (SELECT count(*)::int FROM app.v_link_versions) AS link_versions FROM app.v_review_counts c");
  const q0 = reviewQuery(rs, skip, 0);
  const matchedP = D.rows<{ n: number }>(q0.countSql, q0.params);
  // Rows the live check drops (no access / check failed) never leave the queue, so a page can come back empty.
  // Walk forward (max MAX_SCAN pages per request) until something is shown; the client can continue from nextPage.
  const MAX_SCAN = 4;
  let pg = page;
  let rows: DbRow[] = [];
  const notShown = { noAccess: 0, checkFailed: 0, total: 0 };
  let shown: ReturnType<typeof present>[] = [];
  for (let i = 0; i < MAX_SCAN; i++) {
    rows = await query(pg);
    const live = await liveCheck(g.session.at, rows);
    if (live.sessionExpired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
    notShown.noAccess += live.notShown.noAccess; notShown.checkFailed += live.notShown.checkFailed; notShown.total += live.notShown.total;
    shown = live.rows.map(present);
    if (shown.length || rows.length < PAGE_SIZE) break;
    pg++;
  }
  const [counts, matched] = await Promise.all([countsP, matchedP]);
  const hasMore = rows.length === PAGE_SIZE;
  logEvent("review_page", { page: pg, count: shown.length, dropped_no_access: notShown.noAccess, dropped_check_failed: notShown.checkFailed });
  return json({ counts: counts[0] ?? {}, page: pg, pageSize: PAGE_SIZE, matched: matched[0]?.n ?? 0, nextPage: hasMore ? pg + 1 : null, pageRows: rows.length, rows: shown, notShown, canWrite: canWrite(g.session) });
}
