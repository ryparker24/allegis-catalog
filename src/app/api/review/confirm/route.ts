import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { reviewWrite } from "@/lib/review";

export const dynamic = "force-dynamic";

/** POST /api/review/confirm  {file_id, status, stage?, executed_date?, note?}  - "Confirm and next" */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { write: true, route: "review_confirm" });
  if (!g.ok) return g.response;
  const body = await req.json().catch(() => null);
  const r = await reviewWrite(body, { session: g.session, db: db(env) });
  return json(r.body, r.status);
}
