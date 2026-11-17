/**
 * CAT-WO-02 item 4 · saved views in folders (two levels at most), pinned views, seeds.
 * Every statement is scoped by owner_email; the DB triggers in 003 enforce depth and same-owner folders too.
 */
import type { Db } from "./db";
import { parseLayout, parseSpec, SEED_FOLDERS, SEED_VIEWS, SpecError } from "./find";

export interface FolderRow { folder_id: number; name: string; parent_id: number | null; sort: number }
export interface ViewRow { view_id: number; name: string; spec: Record<string, unknown>; is_seed: boolean; folder_id: number | null; pinned: boolean; sort: number }

export const NAME_MAX = { view: 80, folder: 60 };

export function cleanName(x: unknown, max: number): string | null {
  const s = String(x ?? "").replace(/[\u0000-\u001f]/g, "").trim();
  return s && s.length <= max ? s : null;
}

/** View spec as stored: the validated FindSpec plus its layout (columns, order, widths), page reset to 0. */
export function storedSpec(x: unknown): Record<string, unknown> {
  const spec = parseSpec(x);
  return { ...spec, page: 0, ...parseLayout(x) };
}

export async function listTree(D: Db, owner: string): Promise<{ folders: FolderRow[]; views: ViewRow[] }> {
  let views = await D.rows<ViewRow>("SELECT view_id::int AS view_id, name, spec, is_seed, folder_id::int AS folder_id, pinned, sort FROM app.saved_view WHERE owner_email = $1 ORDER BY sort, name", [owner]);
  if (!views.length) {
    await seed(D, owner);
    views = await D.rows<ViewRow>("SELECT view_id::int AS view_id, name, spec, is_seed, folder_id::int AS folder_id, pinned, sort FROM app.saved_view WHERE owner_email = $1 ORDER BY sort, name", [owner]);
  }
  const folders = await D.rows<FolderRow>("SELECT folder_id::int AS folder_id, name, parent_id::int AS parent_id, sort FROM app.view_folder WHERE owner_email = $1 ORDER BY sort, lower(name)", [owner]);
  return { folders, views };
}

/** First visit: the three seed folders and the four seed views inside them. */
export async function seed(D: Db, owner: string): Promise<void> {
  for (const f of SEED_FOLDERS) {
    await D.exec(
      `INSERT INTO app.view_folder (owner_email, name, sort) SELECT $1, $2, $3
       WHERE NOT EXISTS (SELECT 1 FROM app.view_folder WHERE owner_email = $1 AND parent_id IS NULL AND lower(name) = lower($2))`,
      [owner, f.name, f.sort]);
  }
  for (const s of SEED_VIEWS) {
    await D.exec(
      `INSERT INTO app.saved_view (owner_email, name, spec, is_seed, sort, folder_id)
       VALUES ($1, $2, $3::jsonb, true, $4, (SELECT folder_id FROM app.view_folder WHERE owner_email = $1 AND parent_id IS NULL AND name = $5 LIMIT 1))
       ON CONFLICT (owner_email, name) DO NOTHING`,
      [owner, s.name, JSON.stringify(s.spec), s.sort, s.folder]);
  }
}

export type Result = { ok: true; id?: number } | { ok: false; status: number; error: string };
const bad = (error: string, status = 400): Result => ({ ok: false, status, error });

async function ownsFolder(D: Db, owner: string, id: number): Promise<FolderRow | null> {
  const r = await D.rows<FolderRow>("SELECT folder_id::int AS folder_id, name, parent_id::int AS parent_id, sort FROM app.view_folder WHERE folder_id = $1 AND owner_email = $2", [id, owner]);
  return r[0] ?? null;
}
const intId = (x: unknown) => { const n = Number(x); return Number.isInteger(n) && n > 0 ? n : null; };

export async function saveView(D: Db, owner: string, body: Record<string, unknown>): Promise<Result> {
  const name = cleanName(body.name, NAME_MAX.view);
  if (!name) return bad("bad_name");
  let spec;
  try { spec = storedSpec(body.spec); } catch (e) { return bad(e instanceof SpecError ? `bad_spec: ${e.message}` : "bad_spec"); }
  let folder: number | null = null;
  if (body.folder_id != null) {
    folder = intId(body.folder_id);
    if (!folder || !(await ownsFolder(D, owner, folder))) return bad("bad_folder");
  }
  const r = await D.rows<{ view_id: number }>(
    `INSERT INTO app.saved_view (owner_email, name, spec, sort, folder_id) VALUES ($1, $2, $3::jsonb, 100, $4)
     ON CONFLICT (owner_email, name) DO UPDATE SET spec = EXCLUDED.spec, updated_at = now()
     RETURNING view_id::int AS view_id`,
    [owner, name, JSON.stringify(spec), folder]);
  return { ok: true, id: r[0]?.view_id };
}

/** PATCH a view: rename, move to a folder (or to the top level with null), pin/unpin, reorder. */
export async function patchView(D: Db, owner: string, body: Record<string, unknown>): Promise<Result> {
  const id = intId(body.view_id);
  if (!id) return bad("bad_id");
  const sets: string[] = [];
  const params: unknown[] = [id, owner];
  const p = (v: unknown) => { params.push(v); return `$${params.length}`; };
  if ("name" in body) {
    const name = cleanName(body.name, NAME_MAX.view);
    if (!name) return bad("bad_name");
    sets.push(`name = ${p(name)}`);
  }
  if ("folder_id" in body) {
    if (body.folder_id === null) sets.push("folder_id = NULL");
    else {
      const f = intId(body.folder_id);
      if (!f || !(await ownsFolder(D, owner, f))) return bad("bad_folder");
      sets.push(`folder_id = ${p(f)}`);
    }
  }
  if ("pinned" in body) {
    if (typeof body.pinned !== "boolean") return bad("bad_pinned");
    sets.push(`pinned = ${p(body.pinned)}`);
  }
  if ("sort" in body) {
    const s = Number(body.sort);
    if (!Number.isInteger(s) || s < 0 || s > 30000) return bad("bad_sort");
    sets.push(`sort = ${p(s)}`);
  }
  if ("spec" in body) {
    try { sets.push(`spec = ${p(JSON.stringify(storedSpec(body.spec)))}::jsonb`); } catch (e) { return bad(e instanceof SpecError ? `bad_spec: ${e.message}` : "bad_spec"); }
  }
  if (!sets.length) return bad("nothing_to_change");
  try {
    const n = await D.exec(`UPDATE app.saved_view SET ${sets.join(", ")}, updated_at = now() WHERE view_id = $1 AND owner_email = $2`, params);
    return n === 1 ? { ok: true, id } : bad("not_found", 404);
  } catch (e) {
    if (/duplicate key/i.test(String((e as Error).message))) return bad("name_taken", 409);
    throw e;
  }
}

export async function deleteView(D: Db, owner: string, id: number): Promise<Result> {
  const n = await D.exec("DELETE FROM app.saved_view WHERE view_id = $1 AND owner_email = $2", [id, owner]);
  return n === 1 ? { ok: true } : bad("not_found", 404);
}

export async function createFolder(D: Db, owner: string, body: Record<string, unknown>): Promise<Result> {
  const name = cleanName(body.name, NAME_MAX.folder);
  if (!name) return bad("bad_name");
  let parent: number | null = null;
  if (body.parent_id != null) {
    parent = intId(body.parent_id);
    const pf = parent ? await ownsFolder(D, owner, parent) : null;
    if (!pf) return bad("bad_parent");
    if (pf.parent_id != null) return bad("too_deep"); // two levels at most
  }
  try {
    const r = await D.rows<{ folder_id: number }>(
      "INSERT INTO app.view_folder (owner_email, name, parent_id, sort) VALUES ($1, $2, $3, 100) RETURNING folder_id::int AS folder_id", [owner, name, parent]);
    return { ok: true, id: r[0]?.folder_id };
  } catch (e) {
    const m = String((e as Error).message);
    if (/duplicate key/i.test(m)) return bad("name_taken", 409);
    if (/two levels/i.test(m)) return bad("too_deep");
    throw e;
  }
}

export async function patchFolder(D: Db, owner: string, body: Record<string, unknown>): Promise<Result> {
  const id = intId(body.folder_id);
  if (!id || !(await ownsFolder(D, owner, id))) return bad("not_found", 404);
  const sets: string[] = [];
  const params: unknown[] = [id, owner];
  const p = (v: unknown) => { params.push(v); return `$${params.length}`; };
  if ("name" in body) {
    const name = cleanName(body.name, NAME_MAX.folder);
    if (!name) return bad("bad_name");
    sets.push(`name = ${p(name)}`);
  }
  if ("parent_id" in body) {
    if (body.parent_id === null) sets.push("parent_id = NULL");
    else {
      const pid = intId(body.parent_id);
      const pf = pid ? await ownsFolder(D, owner, pid) : null;
      if (!pf || pid === id) return bad("bad_parent");
      if (pf.parent_id != null) return bad("too_deep");
      sets.push(`parent_id = ${p(pid)}`);
    }
  }
  if ("sort" in body) {
    const s = Number(body.sort);
    if (!Number.isInteger(s) || s < 0 || s > 30000) return bad("bad_sort");
    sets.push(`sort = ${p(s)}`);
  }
  if (!sets.length) return bad("nothing_to_change");
  try {
    await D.exec(`UPDATE app.view_folder SET ${sets.join(", ")}, updated_at = now() WHERE folder_id = $1 AND owner_email = $2`, params);
    return { ok: true, id };
  } catch (e) {
    const m = String((e as Error).message);
    if (/duplicate key/i.test(m)) return bad("name_taken", 409);
    if (/two levels/i.test(m)) return bad("too_deep");
    throw e;
  }
}

/** Delete a folder only when it is empty (no views, no sub-folders): move its views first. */
export async function deleteFolder(D: Db, owner: string, id: number): Promise<Result> {
  if (!(await ownsFolder(D, owner, id))) return bad("not_found", 404);
  const r = await D.rows<{ views: number; subs: number }>(
    `SELECT (SELECT count(*)::int FROM app.saved_view WHERE folder_id = $1 AND owner_email = $2) AS views,
            (SELECT count(*)::int FROM app.view_folder WHERE parent_id = $1 AND owner_email = $2) AS subs`, [id, owner]);
  if ((r[0]?.views ?? 0) > 0 || (r[0]?.subs ?? 0) > 0) return bad("folder_not_empty", 409);
  // the NOT EXISTS guards close the race between the check and the delete
  const n = await D.exec(
    `DELETE FROM app.view_folder f WHERE f.folder_id = $1 AND f.owner_email = $2
       AND NOT EXISTS (SELECT 1 FROM app.saved_view v WHERE v.folder_id = f.folder_id)
       AND NOT EXISTS (SELECT 1 FROM app.view_folder c WHERE c.parent_id = f.folder_id)`, [id, owner]);
  return n === 1 ? { ok: true } : bad("folder_not_empty", 409);
}
