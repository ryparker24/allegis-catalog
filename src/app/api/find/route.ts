import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { FIND_VIEW, groupQuery, pageQuery, parseSpec, SpecError, type FindSpec } from "@/lib/find";
import { driveNameSearch } from "@/lib/google";
import { liveCheck, type DbRow } from "@/lib/live";
import { present } from "@/lib/present";
import { logEvent } from "@/lib/log";
import { accessFor } from "@/lib/checklists";

/** CAT-WO-03.1: a Location group header is a path - shown only when its file opens for the user (live, now); the rest
 *  are pooled into one group with no path. Group values for other columns are codes and pass through. */
const NO_ACCESS_GROUP = "(locations you can't open)";
async function liveGroups(token: string, groupBy: string | null | undefined, groups: { value: string; n: number; rep?: string }[]) {
  if (groupBy !== "location" || !groups.length) return { groups: groups.map(({ value, n }) => ({ value, n })), expired: false };
  const acc = await accessFor(token, groups.map((x) => x.rep!).filter(Boolean));
  if (acc.expired) return { groups: [], expired: true };
  const out: { value: string; n: number }[] = [];
  let hidden = 0;
  for (const x of groups) {
    if (x.rep && acc.map.get(x.rep)?.state === "ok") out.push({ value: x.value, n: x.n });
    else hidden += x.n;
  }
  if (hidden) out.push({ value: NO_ACCESS_GROUP, n: hidden });
  return { groups: out, expired: false };
}

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
  const q = pageQuery(spec, FIND_VIEW, { nameIds: names.ids, hideCopies: true });
  const gq = groupQuery(spec, { nameIds: names.ids, hideCopies: true });
  const D = db(env);
  const [rows, cnt, groups] = await Promise.all([
    D.rows<DbRow>(q.sql, q.params),
    D.rows<{ n: number }>(q.countSql, q.params),
    gq ? D.rows<{ value: string; n: number; rep?: string }>(gq.sql, gq.params) : Promise.resolve([]),
  ]);
  const live = await liveCheck(g.session.at, rows);
  if (live.sessionExpired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  const lg = await liveGroups(g.session.at, spec.groupBy, groups);
  if (lg.expired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  const total = cnt[0]?.n ?? 0;
  logEvent("find", { page: q.page, count: rows.length, total, dropped_no_access: live.notShown.noAccess, dropped_check_failed: live.notShown.checkFailed, ms: Date.now() - t0 });
  return json({
    total, page: q.page, pageSize: q.pageSize, pageRows: rows.length, rows: live.rows.map(present), notShown: live.notShown, groups: lg.groups,
    search: spec.search ? { nameMatches: names.ids.length, nameCapped: names.capped, nameSearchFailed: names.failed } : null,
  });
}
