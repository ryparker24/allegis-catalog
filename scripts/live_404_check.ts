/**
 * G3 live variant: the app's liveCheck() against REAL Drive, as Ryan, for one real labelled file ID plus one
 * well-formed ID that does not exist (Drive answers 404 exactly as for a file the user cannot open).
 * Prints counts and IDs only.
 *   npx tsx scripts/live_404_check.ts --token C:\DriveCatalog\token_labels_apply.json --real <labelled fileId>
 */
import { readFileSync } from "node:fs";
import { liveCheck } from "../src/lib/live";

const arg = (k: string) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : undefined; };
const tok = JSON.parse(readFileSync(arg("--token")!, "utf8"));
const real = arg("--real")!;
const fake = "1CATWO01noSuchFileXXXXXXXXXXXXXXX";

(async () => {
  const r = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: tok.client_id, client_secret: tok.client_secret, refresh_token: tok.refresh_token, grant_type: "refresh_token" }) });
  const at = ((await r.json()) as { access_token: string }).access_token;
  const res = await liveCheck(at, [{ file_id: real, kind: null, tier: "normal" }, { file_id: fake, kind: null, tier: "normal" }]);
  const shown = res.rows.map((x) => x.db.file_id);
  console.log(JSON.stringify({ requested: [real, fake], shown, notShown: res.notShown }));
  const pass = shown.length === 1 && shown[0] === real && res.notShown.noAccess === 1;
  console.log(`${pass ? "PASS" : "FAIL"}  G3 live: the unopenable id is dropped and counted (noAccess=${res.notShown.noAccess}); the real file is shown`);
  process.exit(pass ? 0 : 1);
})();
