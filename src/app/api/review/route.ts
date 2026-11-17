import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { PAGE_SIZE } from "@/lib/find";
import { liveCheck, type DbRow } from "@/lib/live";
import { present } from "@/lib/present";
import { canWrite } from "@/lib/session";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/** GET /api/review?page=N&skip=id,id  ->  counters + one live-checked page of the queue */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "review" });
  if (!g.ok) return g.response;
  const u = new URL(req.url);
  const page = Math.max(0, Math.min(10_000, Number(u.searchParams.get("page") ?? 0) || 0));
  const skip = (u.searchParams.get("skip") ?? "").split(",").filter((s) => /^[A-Za-z0-9_-]{10,128}$/.test(s)).slice(0, 500);
  const D = db(env);
  const query = (pg: number) => D.rows<DbRow>(
    `SELECT file_id, document_id, kind, entities, portcos, fiscal_year, period, stage, signed_date, effective_date, workstream, issuer,
            tier, is_primary, modified_time, file_type_family, queue_reason, signals, confidence, stage_suggested
     FROM app.v_review_queue WHERE NOT (file_id = ANY($1::text[]))
     ORDER BY queue_rank, confidence_rank, file_id LIMIT ${PAGE_SIZE} OFFSET ${pg * PAGE_SIZE}`,
    [skip],
  );
  const countsP = D.rows("SELECT * FROM app.v_review_counts");
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
  const counts = await countsP;
  const hasMore = rows.length === PAGE_SIZE;
  logEvent("review_page", { page: pg, count: shown.length, dropped_no_access: notShown.noAccess, dropped_check_failed: notShown.checkFailed });
  return json({ counts: counts[0] ?? {}, page: pg, nextPage: hasMore ? pg + 1 : null, pageRows: rows.length, rows: shown, notShown, canWrite: canWrite(g.session) });
}
