import { pageUser } from "@/lib/pageauth";
import { Shell } from "@/components/Shell";
import { ReviewClient } from "@/components/ReviewClient";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  const user = await pageUser();
  return (
    <Shell user={user} active="review">
      <ReviewClient />
    </Shell>
  );
}
