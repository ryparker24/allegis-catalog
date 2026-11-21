import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { contentFor } from "@/lib/content";

export const dynamic = "force-dynamic";

/** GET /api/content?file_id=<id> (CAT-WO-06) -> partner codes matched from the document's pages (codes, pages; no text). */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "content" });
  if (!g.ok) return g.response;
  const r = await contentFor(db(env), g.session.at, new URL(req.url).searchParams.get("file_id") ?? "");
  return json(r.body, r.status);
}
