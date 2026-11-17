import { getEnv } from "@/lib/env";
import { handleCallback } from "@/lib/authflow";

export const dynamic = "force-dynamic";
export async function GET(req: Request) {
  return handleCallback(req, await getEnv());
}
