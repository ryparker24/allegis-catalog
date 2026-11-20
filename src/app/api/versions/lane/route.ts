import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { lane } from "@/lib/versions";

export const dynamic = "force-dynamic";

/** GET /api/versions/lane?page=N (CAT-WO-04) -> the Review lane "Link versions": proposed families, members live-checked. */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "versions_lane" });
  if (!g.ok) return g.response;
  const r = await lane(db(env), g.session.at, Number(new URL(req.url).searchParams.get("page") ?? 0));
  return json(r.body, r.status);
}
