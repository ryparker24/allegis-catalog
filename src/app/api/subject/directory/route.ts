import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { canReadDirectory } from "@/lib/session";
import { directorySearch } from "@/lib/subject";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/**
 * GET /api/subject/directory?q=<text>&next=/path  -> staff accounts matching q (People API, as the user).
 * The ONLY place the app asks for directory.readonly (R-026 guard): without it, 409 consent_required with
 * /api/auth/login?scope=directory. Called only when a person field is edited.
 */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "directory", write: true });   // the directory consent also grants drive.metadata: scopes stay consistent
  if (!g.ok) return g.response;
  const u = new URL(req.url);
  const next = u.searchParams.get("next") === "/review" ? "/review" : "/";
  if (!canReadDirectory(g.session)) return json({ error: "consent_required", login: `/api/auth/login?scope=directory&next=${next}` }, 409);
  const q = (u.searchParams.get("q") ?? "").trim();
  if (q.length < 2 || q.length > 60) return json({ hits: [] });
  const r = await directorySearch(g.session.at, q);
  if (r.status === 401) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  if (r.status === 403) return json({ error: "consent_required", login: `/api/auth/login?scope=directory&next=${next}` }, 409);
  logEvent("directory_search", { count: r.hits.length, http_status: r.status });   // the query and names are never logged
  return json({ hits: r.hits }, r.status === 200 ? 200 : 502);
}
