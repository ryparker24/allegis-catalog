import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { canWrite } from "@/lib/session";

export const dynamic = "force-dynamic";
export async function GET(req: Request) {
  const g = await requireUser(req, await getEnv(), { route: "me" });
  if (!g.ok) return g.response;
  return json({ email: g.session.email, canWrite: canWrite(g.session), expiresAt: g.session.exp });
}
