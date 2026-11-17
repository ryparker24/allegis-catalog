import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// No incremental cache / KV: the app stores nothing server-side except in the catalog DB (app.saved_view, app.review_event).
export default defineCloudflareConfig({});
