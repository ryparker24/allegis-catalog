import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { subjectWrite } from "@/lib/subject";

export const dynamic = "force-dynamic";

/** POST /api/subject {file_id, codes?: string[], none?: true, person?: email|null, source?: "match_subject"} (R-026, as the user) */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "subject", write: true, next: "/review" });
  if (!g.ok) return g.response;
  const body = await req.json().catch(() => null);
  const lane = (body as { source?: string } | null)?.source === "match_subject";   // the audit label only
  const r = await subjectWrite(body, { session: g.session, db: db(env), source: lane ? "match_subject" : "find_single" });
  return json(r.body, r.status);
}
