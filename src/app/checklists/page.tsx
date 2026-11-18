import { pageUser } from "@/lib/pageauth";
import { Shell } from "@/components/Shell";
import { ChecklistsClient } from "@/components/ChecklistsClient";

export const dynamic = "force-dynamic";

export default async function ChecklistsPage() {
  const user = await pageUser();
  return (
    <Shell user={user} active="checklists">
      <ChecklistsClient />
    </Shell>
  );
}
