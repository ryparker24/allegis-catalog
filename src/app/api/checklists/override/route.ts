import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { overrideWrite } from "@/lib/checklists";

export const dynamic = "force-dynamic";

/** POST /api/checklists/override {req_key, action: link|not_required|clear, file_id?, note?} -> one append-only row. No Drive write. */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "checklists_override" });
  if (!g.ok) return g.response;
  const r = await overrideWrite(await req.json().catch(() => null), { session: g.session, db: db(env) });
  return json(r.body, r.status);
}
