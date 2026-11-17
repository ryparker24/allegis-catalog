import { handleLogout } from "@/lib/authflow";

export const dynamic = "force-dynamic";
export async function POST() {
  return handleLogout();
}
