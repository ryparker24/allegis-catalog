import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { deleteView, listTree, patchView, saveView, type Result } from "@/lib/views";

export const dynamic = "force-dynamic";

const out = (r: Result) => (r.ok ? json(r) : json({ error: r.error }, r.status));
const body = async (req: Request) => (await req.json().catch(() => ({}))) as Record<string, unknown>;

/** GET: the user's folders and saved views (seed folders + views inserted on first use). */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "views" });
  if (!g.ok) return g.response;
  return json(await listTree(db(env), g.session.email.toLowerCase()));
}

/** POST {name, spec, folder_id?}: create or overwrite one of the user's views. */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "views" });
  if (!g.ok) return g.response;
  return out(await saveView(db(env), g.session.email.toLowerCase(), await body(req)));
}

/** PATCH {view_id, name?, folder_id?, pinned?, sort?, spec?}: rename, move, pin, reorder, update. */
export async function PATCH(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "views" });
  if (!g.ok) return g.response;
  return out(await patchView(db(env), g.session.email.toLowerCase(), await body(req)));
}

/** DELETE ?id=: delete one of the user's own views. */
export async function DELETE(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "views" });
  if (!g.ok) return g.response;
  const id = Number(new URL(req.url).searchParams.get("id"));
  if (!Number.isInteger(id) || id <= 0) return json({ error: "bad_id" }, 400);
  return out(await deleteView(db(env), g.session.email.toLowerCase(), id));
}
