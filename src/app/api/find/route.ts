import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { groupQuery, pageQuery, parseSpec, SpecError, type FindSpec } from "@/lib/find";
import { driveNameSearch } from "@/lib/google";
import { liveCheck, type DbRow } from "@/lib/live";
import { present } from "@/lib/present";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/** Name matches for the top-bar search come from Drive, as the user (names never reach the DB). */
async function nameIds(accessToken: string, spec: FindSpec): Promise<{ ids: string[]; capped: boolean; failed: boolean; expired: boolean }> {
  if (!spec.search) return { ids: [], capped: false, failed: false, expired: false };
  const r = await driveNameSearch(accessToken, spec.search);
  return { ids: r.ids, capped: r.capped, failed: r.status !== 200, expired: r.status === 401 };
}

/** POST /api/find  body: FindSpec  ->  one live-checked page + total matched + not-shown count (+ group counts) */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "find" });
  if (!g.ok) return g.response;
  let spec;
  try {
    spec = parseSpec(await req.json());
  } catch (e) {
    return json({ error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid_json" }, 400);
  }
  const t0 = Date.now();
  const names = await nameIds(g.session.at, spec);
  if (names.expired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  const q = pageQuery(spec, "app.v_find", { nameIds: names.ids });
  const gq = groupQuery(spec, { nameIds: names.ids });
  const D = db(env);
  const [rows, cnt, groups] = await Promise.all([
    D.rows<DbRow>(q.sql, q.params),
    D.rows<{ n: number }>(q.countSql, q.params),
    gq ? D.rows<{ value: string; n: number }>(gq.sql, gq.params) : Promise.resolve([]),
  ]);
  const live = await liveCheck(g.session.at, rows);
  if (live.sessionExpired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  const total = cnt[0]?.n ?? 0;
  logEvent("find", { page: q.page, count: rows.length, total, dropped_no_access: live.notShown.noAccess, dropped_check_failed: live.notShown.checkFailed, ms: Date.now() - t0 });
  return json({
    total, page: q.page, pageSize: q.pageSize, pageRows: rows.length, rows: live.rows.map(present), notShown: live.notShown, groups,
    search: spec.search ? { nameMatches: names.ids.length, nameCapped: names.capped, nameSearchFailed: names.failed } : null,
  });
}
