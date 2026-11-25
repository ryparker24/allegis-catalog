import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { FILE_ID_RE } from "@/lib/google";
import { accessFor } from "@/lib/checklists";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";
const MAX_MEMBERS = 500;

/**
 * GET /api/zip?file_id=<id>  (CAT-WO-17 R-062) -> what is inside a zip: member names, sizes, dates, and the catalog file
 * with the same md5 ("also on Drive"). The zip itself is checked live as the user; a matching file is linked only when the
 * user can open it. Names are never logged (counts only).
 */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "zip" });
  if (!g.ok) return g.response;
  const fileId = new URL(req.url).searchParams.get("file_id") ?? "";
  if (!FILE_ID_RE.test(fileId)) return json({ error: "bad_file_id" }, 400);
  const D = db(env);
  const z = await D.rows<{ status: string; member_count: number; listed_at: string }>(
    "SELECT status, member_count, listed_at::text AS listed_at FROM cat.zip_listing WHERE zip_file_id = $1", [fileId]);
  const acc0 = await accessFor(g.session.at, [fileId]);
  if (acc0.expired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  if (acc0.map.get(fileId)?.state !== "ok") return json({ error: "no_access" }, 403);
  if (!z.length) return json({ listed: false });
  const rows = await D.rows<{ parent_member: string; member_path: string; is_dir: boolean; size_bytes: number | null; member_mtime: string | null; encrypted: boolean; on_drive_file_id: string | null }>(
    `SELECT parent_member, member_path, is_dir, size_bytes, member_mtime::text AS member_mtime, encrypted, on_drive_file_id
     FROM app.v_zip_member WHERE zip_file_id = $1 AND NOT is_dir ORDER BY parent_member, member_path LIMIT ${MAX_MEMBERS}`, [fileId]);
  const ids = [...new Set(rows.map((r) => r.on_drive_file_id).filter((x): x is string => !!x))];
  const acc = ids.length ? await accessFor(g.session.at, ids) : { expired: false, map: new Map() };
  const members = rows.map((r) => ({
    ...r, on_drive_file_id: r.on_drive_file_id && acc.map.get(r.on_drive_file_id)?.state === "ok" ? r.on_drive_file_id : null,
    on_drive: !!r.on_drive_file_id,
  }));
  logEvent("zip_read", { file_id: fileId, count: members.length });
  return json({ listed: true, status: z[0].status, member_count: z[0].member_count, listed_at: z[0].listed_at, members, truncated: rows.length === MAX_MEMBERS });
}
