import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { act, timeline } from "@/lib/versions";

export const dynamic = "force-dynamic";

/** GET /api/versions?file_id=<id> (CAT-WO-04) -> the Versions timeline of that file's document (members live-checked as the user). */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "versions" });
  if (!g.ok) return g.response;
  const r = await timeline(db(env), g.session.at, new URL(req.url).searchParams.get("file_id") ?? "");
  return json(r.body, r.status);
}

/** POST /api/versions {action, document?, target?, base?, family?, documents?} -> one person-set version action. */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "versions", write: true, next: "/" });
  if (!g.ok) return g.response;
  const body = await req.json().catch(() => null);
  const r = await act(body, { session: g.session, db: db(env) });
  return json(r.body, r.status);
}
