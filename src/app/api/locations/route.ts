import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { FILE_ID_RE } from "@/lib/google";
import { accessFor } from "@/lib/checklists";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/**
 * GET /api/locations?file_id=<id>  (CAT-WO-03.1) -> every location of that file's document: drive › folder path and the
 * parent folder id, for each copy (not secret, live) the user can OPEN, checked live as the user now. A copy the user
 * can't open is counted, never shown. Paths are never logged (counts only).
 */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "locations" });
  if (!g.ok) return g.response;
  const fileId = new URL(req.url).searchParams.get("file_id") ?? "";
  if (!FILE_ID_RE.test(fileId)) return json({ error: "bad_file_id" }, 400);
  const D = db(env);
  const f = await D.rows<{ document_id: string | null }>("SELECT document_id::text AS document_id FROM app.v_find_x WHERE file_id = $1", [fileId]);
  if (!f.length) return json({ error: "no_access" }, 403);          // one answer for out of scope / can't open
  const rows = f[0].document_id
    ? await D.rows<{ file_id: string; location: string; location_folder_id: string | null; is_primary: boolean }>(
        `SELECT file_id, location, location_folder_id, is_primary FROM app.v_document_location
         WHERE document_id = $1::bigint ORDER BY is_primary DESC, location LIMIT 200`, [f[0].document_id])
    : await D.rows<{ file_id: string; location: string; location_folder_id: string | null; is_primary: boolean }>(
        "SELECT file_id, location, location_folder_id, true AS is_primary FROM app.v_find_x WHERE file_id = $1", [fileId]);
  const acc = await accessFor(g.session.at, rows.map((r) => r.file_id));
  if (acc.expired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  const shown = rows.filter((r) => acc.map.get(r.file_id)?.state === "ok");
  // one entry per folder (two copies in one folder are one location)
  const seen = new Set<string>();
  const locations = shown.filter((r) => { const k = r.location_folder_id ?? r.location; if (seen.has(k)) return false; seen.add(k); return true; })
    .map((r) => ({ file_id: r.file_id, location: r.location, folder_id: r.location_folder_id, is_primary: r.is_primary }));
  const hiddenFolders = new Set(rows.filter((r) => acc.map.get(r.file_id)?.state !== "ok").map((r) => r.location_folder_id ?? r.location).filter((k) => !seen.has(k)));
  logEvent("locations_read", { file_id: fileId, count: locations.length, dropped_no_access: hiddenFolders.size });
  return json({ locations, not_shown: hiddenFolders.size });
}
