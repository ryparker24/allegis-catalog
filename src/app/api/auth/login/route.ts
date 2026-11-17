import { getEnv } from "@/lib/env";
import { handleLogin } from "@/lib/authflow";

export const dynamic = "force-dynamic";
export async function GET(req: Request) {
  return handleLogin(req, await getEnv());
}
