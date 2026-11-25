import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { subjectBulk } from "@/lib/subjectbulk";

export const dynamic = "force-dynamic";

/** POST /api/review/subject-bulk {spec?, confirm?} -> preview (no confirm) or bulk Confirm of single-candidate Match subject rows, ≤ 500 (CAT-WO-15, R-023). */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "subject_bulk", write: true, next: "/review" });
  if (!g.ok) return g.response;
  const r = await subjectBulk(await req.json().catch(() => null), { session: g.session, db: db(env) });
  return json(r.body, r.status);
}
