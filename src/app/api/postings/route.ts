import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { postingsFor } from "@/lib/postings";

export const dynamic = "force-dynamic";

/** GET /api/postings?file_id=<id> (CAT-WO-05) -> the document's portal postings (channel, date, posting ID; no partner). */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "postings" });
  if (!g.ok) return g.response;
  const r = await postingsFor(db(env), g.session.at, new URL(req.url).searchParams.get("file_id") ?? "");
  return json(r.body, r.status);
}
