/**
 * CAT-WO-01 item 5 guard G4 - "A review write does not change the file's modifiedTime."
 * LIVE check on ONE file in the ACCSO pilot folder, through the app's own write path (src/lib/review.ts):
 *   files.modifyLabels as the user (Execution + Catalog Review) + one app.review_event row (THROWAWAY BRANCH DB).
 * Then the file's Catalog Review values are restored to what they were before (a second write on the same file),
 * and modifiedTime is read again. Prints file ID, codes and timestamps only.
 *
 *   npx tsx scripts/mtime_check.ts --file <fileId> --token C:\DriveCatalog\token_labels_apply.json --app-db-url-file <branch catalog_app url file>
 *
 * The token file's refresh token is used IN MEMORY to mint one access token (this local script only; the app never sees it).
 */
import { readFileSync } from "node:fs";
import { reviewWrite } from "../src/lib/review";
import { db } from "../src/lib/db";
import { driveGet, modifyLabels } from "../src/lib/google";
import { decodeLabels, LABEL_IDS } from "../src/lib/labels";
import schema from "../src/lib/labels_schema.json";
import type { Session } from "../src/lib/session";

const arg = (k: string) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : undefined; };
const fileId = arg("--file")!;
const tokenFile = arg("--token")!;
const appDbUrl = readFileSync(arg("--app-db-url-file")!, "utf8").trim();
if (!fileId || !tokenFile || !appDbUrl) throw new Error("usage: --file --token --app-db-url-file");
if (/main|misty-silence/.test(appDbUrl.split("@")[1] ?? "")) throw new Error("refusing: not a throwaway branch URL");

async function accessToken(): Promise<{ at: string; scopes: string[] }> {
  const t = JSON.parse(readFileSync(tokenFile, "utf8"));
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: t.client_id, client_secret: t.client_secret, refresh_token: t.refresh_token, grant_type: "refresh_token" }),
  });
  if (!r.ok) throw new Error(`token refresh failed ${r.status}`);
  const j = await r.json() as { access_token: string; scope: string };
  return { at: j.access_token, scopes: j.scope.split(" ") };
}

const S = schema as any;
const INCL = `${LABEL_IDS.exec},${LABEL_IDS.review}`;
async function snapshot(at: string) {
  const r = await fetch(`https://www.googleapis.com/drive/v3/files/${fileId}?fields=modifiedTime,labelInfo&includeLabels=${INCL}&supportsAllDrives=true`, { headers: { authorization: `Bearer ${at}` } });
  if (!r.ok) throw new Error(`files.get ${r.status}`);
  const j = await r.json() as { modifiedTime: string; labelInfo: any };
  const v = decodeLabels(j.labelInfo);
  const rev = (j.labelInfo?.labels ?? []).find((l: any) => l.id === LABEL_IDS.review);
  const reviewedBy = rev?.fields?.[S.review.fields.reviewed_by.field_id]?.user?.length ? "set" : "unset";
  return { modifiedTime: j.modifiedTime, stage: v.stage, executed_date: v.executed_date, review_status: v.review_status, reviewed_by: reviewedBy, note: v.review_note ? "set" : "unset", raw: j.labelInfo };
}

(async () => {
  const { at, scopes } = await accessToken();
  const before = await snapshot(at);
  const { raw: _r0, ...b } = before;
  console.log("BEFORE ", JSON.stringify({ file_id: fileId, ...b }));

  // the write, through the app's own code path (same function /api/review/confirm calls)
  const session: Session = { v: 1, email: "ryan@allegiscapital.com", sub: "local-check", hd: "allegiscapital.com", at, scopes, exp: Math.floor(Date.now() / 1000) + 600 };
  const body = {
    file_id: fileId,
    status: "wrong",                               // honest: this is a test write, not a human confirmation
    stage: before.stage ?? null,                   // re-assert the stage already on the label (no semantic change)
    executed_date: before.stage === "fully_executed" ? before.executed_date : null,
    note: "CAT-WO-01 modifiedTime check - test write, values restored",
  };
  const res = await reviewWrite(body, { session, db: db({ CATALOG_APP_DB_URL: appDbUrl }) });
  console.log("WRITE  ", JSON.stringify({ http: res.status, ...res.body }));
  await new Promise((r) => setTimeout(r, 4000));
  const after = await snapshot(at);
  const { raw: _r1, ...a } = after;
  console.log("AFTER  ", JSON.stringify({ file_id: fileId, ...a }));

  // restore the Catalog Review values exactly as they were before
  const rev0 = (before.raw?.labels ?? []).find((l: any) => l.id === LABEL_IDS.review);
  const R = S.review.fields;
  const fm: any[] = [];
  const st0 = rev0?.fields?.[R.status.field_id]?.selection;
  fm.push(st0?.length ? { fieldId: R.status.field_id, setSelectionValues: st0 } : { fieldId: R.status.field_id, unsetValues: true });
  const by0 = rev0?.fields?.[R.reviewed_by.field_id]?.user?.map((u: any) => u.emailAddress);
  fm.push(by0?.length ? { fieldId: R.reviewed_by.field_id, setUserValues: by0 } : { fieldId: R.reviewed_by.field_id, unsetValues: true });
  const n0 = rev0?.fields?.[R.note.field_id]?.text;
  fm.push(n0?.length ? { fieldId: R.note.field_id, setTextValues: n0 } : { fieldId: R.note.field_id, unsetValues: true });
  const restore = await modifyLabels(at, fileId, [{ labelId: LABEL_IDS.review, fieldModifications: fm }]);
  await new Promise((r) => setTimeout(r, 4000));
  const restored = await snapshot(at);
  const { raw: _r2, ...c } = restored;
  console.log("RESTORE", JSON.stringify({ http: restore.status }));
  console.log("FINAL  ", JSON.stringify({ file_id: fileId, ...c }));
  const same = before.modifiedTime === after.modifiedTime && after.modifiedTime === restored.modifiedTime;
  console.log(`${same ? "PASS" : "FAIL"}  G4 modifiedTime unchanged by the review write (and by the restore): ${before.modifiedTime} -> ${after.modifiedTime} -> ${restored.modifiedTime}`);
  void driveGet;
  process.exit(same && res.status === 200 ? 0 : 1);
})().catch((e) => { console.error("ERROR", (e as Error).message); process.exit(2); });
