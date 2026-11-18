import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { editBulk } from "@/lib/editflow";

export const dynamic = "force-dynamic";

/** POST /api/edit/bulk {file_ids[], set, confirm?} -> preview (no confirm) or write, capped at 500 (item 8). */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "edit_bulk", write: true, next: "/" });
  if (!g.ok) return g.response;
  const r = await editBulk(await req.json().catch(() => null), { session: g.session, db: db(env) });
  return json(r.body, r.status);
}
