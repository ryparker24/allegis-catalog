/**
 * LOCAL ONLY (CAT-WO-02 proofs): a proxy on :8788 in front of `wrangler dev -c wrangler.local.jsonc` (:8787,
 * THROWAWAY BRANCH DB) that adds a session cookie minted in memory, so a browser can view the real Worker
 * without the R2 OAuth redirect. Same minting as scripts/worker_smoke.ts. Nothing is printed except the port;
 * the cookie never leaves this process. The app itself has no bypass: every check still runs in the Worker.
 *
 *   npx tsx scripts/dev_proxy.ts [--upstream 8787] [--port 8788] --secret-file <dev secret> --token C:\DriveCatalog\token_labels_apply.json
 */
import { createServer, request } from "node:http";
import { readFileSync } from "node:fs";
import { sealSession, SESSION_COOKIE } from "../src/lib/session";

const arg = (k: string) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : undefined; };
const secret = readFileSync(arg("--secret-file")!, "utf8").trim();
const tok = JSON.parse(readFileSync(arg("--token")!, "utf8"));
const UPPORT = Number(arg("--upstream") ?? 8787);
const PORT = Number(arg("--port") ?? UPPORT + 1);
const UP = { host: "127.0.0.1", port: UPPORT };
const ORIGIN = `http://localhost:${UPPORT}`; // = APP_ORIGIN of the local Worker

let cookie = "", exp = 0;
async function session(): Promise<string> {
  if (cookie && Date.now() / 1000 < exp - 120) return cookie;
  const r = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: tok.client_id, client_secret: tok.client_secret, refresh_token: tok.refresh_token, grant_type: "refresh_token" }) });
  const j = await r.json() as { access_token: string; scope: string; expires_in: number };
  exp = Math.floor(Date.now() / 1000) + j.expires_in;
  cookie = `${SESSION_COOKIE}=${await sealSession({ v: 1, email: "ryan@allegiscapital.com", sub: "dev-proxy", hd: "allegiscapital.com", at: j.access_token, scopes: j.scope.split(" "), exp: exp - 60 }, secret)}`;
  return cookie;
}

createServer(async (req, res) => {
  const headers = { ...req.headers, host: `localhost:${UPPORT}`, cookie: await session() } as unknown as Record<string, string>;
  if (headers.origin) headers.origin = ORIGIN;
  delete headers.referer;
  const up = request({ ...UP, path: req.url, method: req.method, headers }, (u) => {
    const h = { ...u.headers };
    delete h["set-cookie"];
    res.writeHead(u.statusCode ?? 502, h);
    u.pipe(res);
  });
  up.on("error", () => { res.writeHead(502); res.end("upstream down"); });
  req.pipe(up);
}).listen(PORT, "127.0.0.1", () => console.log(`dev proxy on http://localhost:${PORT}`));
