/**
 * Local end-to-end smoke test against the REAL Worker (`wrangler dev`) wired to a THROWAWAY BRANCH DB.
 * Mints a test session cookie locally (sealed with the dev SESSION_SECRET from .dev.vars, carrying an access
 * token minted in memory from the local token file) - the app itself has no bypass. Prints status codes and
 * counts only; file names in responses are never printed.
 *
 *   npx tsx scripts/worker_smoke.ts --base http://127.0.0.1:8787 --secret-file <dev secret> --token C:\DriveCatalog\token_labels_apply.json
 */
import { readFileSync } from "node:fs";
import { sealSession, SESSION_COOKIE } from "../src/lib/session";

const arg = (k: string) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : undefined; };
const base = arg("--base") ?? "http://127.0.0.1:8787";
const secret = readFileSync(arg("--secret-file")!, "utf8").trim();
const tok = JSON.parse(readFileSync(arg("--token")!, "utf8"));

async function accessToken() {
  const r = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: tok.client_id, client_secret: tok.client_secret, refresh_token: tok.refresh_token, grant_type: "refresh_token" }) });
  const j = await r.json() as { access_token: string; scope: string; expires_in: number };
  return j;
}
const line = (label: string, v: unknown) => console.log(`${label.padEnd(58)} ${typeof v === "string" ? v : JSON.stringify(v)}`);

(async () => {
  // unauthenticated / wrong host
  let r = await fetch(`${base}/api/find`, { method: "POST", body: "{}" });
  line("POST /api/find, no session", r.status);
  r = await fetch(`${base}/api/auth/login`, { redirect: "manual" });
  line("GET /api/auth/login (no OAuth client yet, R2)", `${r.status} ${(await r.text()).slice(0, 40)}`);
  r = await fetch(`${base}/`);
  line("GET / localhost, no session", `${r.status} ${/Sign in with Google/.test(await r.text()) ? "(sign-in page)" : "(NOT the sign-in page)"}`);

  const t = await accessToken();
  const mk = async (email: string) => sealSession({ v: 1, email, sub: "smoke", hd: "allegiscapital.com", at: t.access_token, scopes: t.scope.split(" "), exp: Math.floor(Date.now() / 1000) + t.expires_in - 60 }, secret);
  const other = await mk("colleague@allegiscapital.com");
  r = await fetch(`${base}/api/find`, { method: "POST", headers: { cookie: `${SESSION_COOKIE}=${other}` }, body: "{}" });
  line("POST /api/find as non-allowlisted allegiscapital.com", r.status);

  const c = `${SESSION_COOKIE}=${await mk("ryan@allegiscapital.com")}`;
  const H = { cookie: c, "content-type": "application/json" };
  r = await fetch(`${base}/`, { headers: { cookie: c } });
  const html = await r.text();
  line("GET / signed in", `${r.status} ${/Saved views|class="find/.test(html) && /not built \(R-006\)/.test(html) && !/403 - not allowed|Sign in with Google/.test(html) ? "(Find shell; Gaps tab disabled: not built (R-006))" : "(NOT the Find shell)"}`);

  r = await fetch(`${base}/api/facets`, { headers: H });
  const f = await r.json() as Record<string, { value: string; n: number }[]>;
  line("GET /api/facets", `${r.status} kinds=${f.kind?.length} entities=${f.entity?.length} portcos=${f.portco?.length} tiers=${JSON.stringify(f.tier)}`);

  for (const [label, spec] of [
    ["POST /api/find all labelled files, page 1", { filters: {} }],
    ["POST /api/find kind=k1, entity filter, group by fiscal year", { filters: { kind: ["k1"], entity: [f.entity?.[0]?.value] }, groupBy: "fiscal_year", sort: { col: "fiscal_year", dir: "desc" } }],
    ["POST /api/find fully executed + primary only, page 2", { filters: { stage: ["fully_executed"], primary_only: true }, page: 1 }],
  ] as const) {
    const t0 = Date.now();
    r = await fetch(`${base}/api/find`, { method: "POST", headers: H, body: JSON.stringify(spec) });
    const j = await r.json() as any;
    line(label, `${r.status} total=${j.total} pageRows=${j.pageRows} shown=${j.rows?.length} notShown=${JSON.stringify(j.notShown)} changedInDrive=${j.rows?.filter((x: any) => x.changed.length).length} groups=${j.groups?.length} ${Date.now() - t0}ms`);
  }
  r = await fetch(`${base}/api/find`, { method: "POST", headers: H, body: JSON.stringify({ filters: { kind: ["x'; drop table app.saved_view;--"] } }) });
  line("POST /api/find with injection attempt", `${r.status} ${JSON.stringify(await r.json())}`);

  r = await fetch(`${base}/api/export`, { method: "POST", headers: H, body: JSON.stringify({ filters: { kind: ["k1"] } }) });
  const csv = await r.text();
  line("POST /api/export kind=k1", `${r.status} rows=${csv.trim().split("\r\n").length - 1} header=${csv.split("\r\n")[0]}`);

  r = await fetch(`${base}/api/views`, { headers: H });
  const v = await r.json() as any;
  line("GET /api/views (seeds on first use)", `${r.status} views=${v.views?.length} seeds=${v.views?.filter((x: any) => x.is_seed).length}`);

  r = await fetch(`${base}/api/review`, { headers: H });
  const q = await r.json() as any;
  line("GET /api/review", `${r.status} counts=${JSON.stringify(q.counts)} shown=${q.rows?.length} notShown=${JSON.stringify(q.notShown)} first_reason=${q.rows?.[0]?.queue_reason} canWrite=${q.canWrite}`);

  const ro = await sealSession({ v: 1, email: "ryan@allegiscapital.com", sub: "smoke", hd: "allegiscapital.com", at: t.access_token, scopes: ["openid", "email", "https://www.googleapis.com/auth/drive.metadata.readonly"], exp: Math.floor(Date.now() / 1000) + 600 }, secret);
  r = await fetch(`${base}/api/review/confirm`, { method: "POST", headers: { cookie: `${SESSION_COOKIE}=${ro}`, "content-type": "application/json" }, body: JSON.stringify({ file_id: q.rows?.[0]?.file_id, status: "confirmed" }) });
  line("POST /api/review/confirm with read-only session (no write)", `${r.status} ${JSON.stringify(await r.json())}`);
  r = await fetch(`${base}/api/review/confirm`, { method: "POST", headers: H, body: JSON.stringify({ file_id: "1111111111111111111111111", status: "confirmed" }) });
  line("POST /api/review/confirm for a file not in the queue", `${r.status} ${JSON.stringify(await r.json())}`);
})().catch((e) => { console.error("ERROR", e.message); process.exit(2); });
