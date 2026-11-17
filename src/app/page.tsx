import { pageUser } from "@/lib/pageauth";
import { Shell } from "@/components/Shell";
import { FindClient } from "@/components/FindClient";

export const dynamic = "force-dynamic";

export default async function FindPage() {
  const user = await pageUser();
  return (
    <Shell user={user} active="find">
      <FindClient />
    </Shell>
  );
}
