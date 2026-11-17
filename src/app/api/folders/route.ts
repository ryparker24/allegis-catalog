import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { createFolder, deleteFolder, patchFolder, type Result } from "@/lib/views";

export const dynamic = "force-dynamic";

const out = (r: Result) => (r.ok ? json(r) : json({ error: r.error }, r.status));
const body = async (req: Request) => (await req.json().catch(() => ({}))) as Record<string, unknown>;

/** POST {name, parent_id?}: create a folder (two levels at most). */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "folders" });
  if (!g.ok) return g.response;
  return out(await createFolder(db(env), g.session.email.toLowerCase(), await body(req)));
}

/** PATCH {folder_id, name?, parent_id?, sort?}: rename / move / reorder. */
export async function PATCH(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "folders" });
  if (!g.ok) return g.response;
  return out(await patchFolder(db(env), g.session.email.toLowerCase(), await body(req)));
}

/** DELETE ?id=: only when the folder is empty (409 folder_not_empty otherwise). */
export async function DELETE(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "folders" });
  if (!g.ok) return g.response;
  const id = Number(new URL(req.url).searchParams.get("id"));
  if (!Number.isInteger(id) || id <= 0) return json({ error: "bad_id" }, 400);
  return out(await deleteFolder(db(env), g.session.email.toLowerCase(), id));
}
