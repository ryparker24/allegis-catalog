/**
 * LOCAL ONLY (CAT-WO-15 screenshot): like dev_proxy.ts, but the session carries NO Google token (a placeholder), so it
 * never reads a token file and the Worker can make no Drive call that succeeds. For screens whose data comes from the
 * DB alone (counters, an empty list). Nothing is printed except the port.
 *
 *   npx tsx scripts/dev_proxy_nodrive.ts [--upstream 8787] [--port 8788] --secret-file <the local .dev.vars SESSION_SECRET>
 */
import { createServer, request } from "node:http";
import { readFileSync } from "node:fs";
import { sealSession, SESSION_COOKIE } from "../src/lib/session";

const arg = (k: string) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : undefined; };
const secret = readFileSync(arg("--secret-file")!, "utf8").trim();
const UPPORT = Number(arg("--upstream") ?? 8787);
const PORT = Number(arg("--port") ?? UPPORT + 1);
const ORIGIN = `http://localhost:${UPPORT}`;
const exp = Math.floor(Date.now() / 1000) + 3600;

(async () => {
  const cookie = `${SESSION_COOKIE}=${await sealSession({ v: 1, email: "ryan@allegiscapital.com", sub: "dev-proxy-nodrive", hd: "allegiscapital.com", at: "no-drive-token",
    scopes: ["openid", "email"], exp }, secret)}`;
  createServer((req, res) => {
    const headers = { ...req.headers, host: `localhost:${UPPORT}`, cookie } as unknown as Record<string, string>;
    if (headers.origin) headers.origin = ORIGIN;
    delete headers.referer;
    const up = request({ host: "127.0.0.1", port: UPPORT, path: req.url, method: req.method, headers }, (u) => {
      const h = { ...u.headers };
      delete h["set-cookie"];
      res.writeHead(u.statusCode ?? 502, h);
      u.pipe(res);
    });
    up.on("error", () => { res.writeHead(502); res.end(); });
    req.pipe(up);
  }).listen(PORT, "127.0.0.1", () => console.log(`proxy on ${PORT}`));
})();
