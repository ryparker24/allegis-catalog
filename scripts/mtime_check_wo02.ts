/**
 * CAT-WO-02 item 8 guard G-E2 - "modifiedTime is unchanged after a single and a bulk edit (one pilot file, restored afterwards)."
 * LIVE on ONE pilot-folder file, through the app's own write paths (src/lib/editflow.ts editOne + editBulk):
 * files.modifyLabels as the user + app.review_event rows on the THROWAWAY BRANCH DB. Then every field of the
 * Allegis Document, Execution and Catalog Review labels is put back exactly as it was. Handling is never touched.
 * Prints the file ID, codes and timestamps only.
 *
 *   npx tsx scripts/mtime_check_wo02.ts --file <id> --token C:\DriveCatalog\token_labels_apply.json --app-db-url-file <branch catalog_app url file>
 */
import { readFileSync } from "node:fs";
import { editBulk, editOne } from "../src/lib/editflow";
import { db } from "../src/lib/db";
import { decodeLabels, LABEL_IDS } from "../src/lib/labels";
import type { Session } from "../src/lib/session";

const arg = (k: string) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : undefined; };
const fileId = arg("--file")!;
const tokenFile = arg("--token")!;
const appDbUrl = readFileSync(arg("--app-db-url-file")!, "utf8").trim();
if (!fileId || !tokenFile || !appDbUrl) throw new Error("usage: --file --token --app-db-url-file");
// ALLOW-list (CISO review): only the CAT-WO-02 throwaway branch endpoint (br-red-band-bd2d79yz). Main is
// ep-calm-violet-bdk7m2ar; anything that isn't the throwaway endpoint is refused, whatever its spelling.
const THROWAWAY_ENDPOINT = (arg("--allow-endpoint") ?? "ep-billowing-truth-bdj6gzs7").toLowerCase();
const host = (appDbUrl.toLowerCase().split("@")[1] ?? "").split(/[/:?]/)[0];
if (!host.startsWith(THROWAWAY_ENDPOINT + ".") && !host.startsWith(THROWAWAY_ENDPOINT + "-pooler.")) throw new Error("refusing: not the throwaway branch endpoint");

const W = [LABEL_IDS.doc, LABEL_IDS.exec, LABEL_IDS.review];
type Field = { selection?: string[]; integer?: string[]; dateString?: string[]; text?: string[]; user?: { emailAddress?: string }[] };
type Snap = { modifiedTime: string; labels: { id: string; fields?: Record<string, Field> }[]; labelInfo: unknown };

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
async function snap(at: string): Promise<Snap> {
  const q = new URLSearchParams({ fields: "modifiedTime,labelInfo", includeLabels: [...W, LABEL_IDS.handling].join(","), supportsAllDrives: "true" });
  const r = await fetch(`https://www.googleapis.com/drive/v3/files/${fileId}?${q}`, { headers: { authorization: `Bearer ${at}` } });
  const j = await r.json() as { modifiedTime: string; labelInfo?: { labels?: { id: string; fields?: Record<string, Field> }[] } };
  return { modifiedTime: j.modifiedTime, labels: j.labelInfo?.labels ?? [], labelInfo: j.labelInfo };
}
function codes(s: Snap) {
  const d = decodeLabels(s.labelInfo as never);
  return { kind: d.kind, fiscal_year: d.fiscal_year, entities: d.entities, stage: d.stage, tier: d.tier, review_status: d.review_status,  };
}
/** Put back every field of doc / exec / review exactly as in `before` (set what was there, unset the rest). */
function restoreMods(before: Snap, after: Snap): unknown[] {
  const mods: unknown[] = [];
  for (const lid of W) {
    const hadBefore = before.labels.some((l) => l.id === lid);
    const hasNow = after.labels.some((l) => l.id === lid);
    if (!hadBefore) { if (hasNow) mods.push({ labelId: lid, removeLabel: true }); continue; } // label wasn't there: remove it
    const b = before.labels.find((l) => l.id === lid)?.fields ?? {};
    const a = after.labels.find((l) => l.id === lid)?.fields ?? {};
    const fm: unknown[] = [];
    for (const fid of new Set([...Object.keys(a), ...Object.keys(b)])) {
      const v = b[fid];
      if (!v) { fm.push({ fieldId: fid, unsetValues: true }); continue; }
      if (v.selection) fm.push({ fieldId: fid, setSelectionValues: v.selection });
      else if (v.integer) fm.push({ fieldId: fid, setIntegerValues: v.integer });
      else if (v.dateString) fm.push({ fieldId: fid, setDateValues: v.dateString.map((s) => { const [year, month, day] = s.split("-").map(Number); return { year, month, day }; }) });
      else if (v.text) fm.push({ fieldId: fid, setTextValues: v.text });
      else if (v.user) fm.push({ fieldId: fid, setUserValues: v.user.map((u) => u.emailAddress!) });
    }
    if (fm.length) mods.push({ labelId: lid, fieldModifications: fm });
  }
  return mods;
}
const same = (a: Snap, b: Snap) => JSON.stringify(a.labels.filter((l) => W.includes(l.id)).map((l) => [l.id, l.fields]).sort()) === JSON.stringify(b.labels.filter((l) => W.includes(l.id)).map((l) => [l.id, l.fields]).sort());
const line = (k: string, v: unknown) => console.log(`${k.padEnd(8)} ${JSON.stringify(v)}`);

const keep = arg("--keep");          // G-E4 live: edit once, save the BEFORE snapshot here, don't restore yet
const restoreFrom = arg("--restore-from");
import { writeFileSync } from "node:fs";

(async () => {
  const t = await accessToken();
  if (restoreFrom) {
    const before = JSON.parse(readFileSync(restoreFrom, "utf8")) as Snap;
    const cur = await snap(t.at);
    const r = await fetch(`https://www.googleapis.com/drive/v3/files/${fileId}/modifyLabels`, {
      method: "POST", headers: { authorization: `Bearer ${t.at}`, "content-type": "application/json" }, body: JSON.stringify({ kind: "drive#modifyLabelsRequest", labelModifications: restoreMods(before, cur) }),
    });
    const fin = await snap(t.at);
    line("RESTORE", { http: r.status, modifiedTime: fin.modifiedTime, ...codes(fin) });
    console.log(`${same(before, fin) && fin.modifiedTime === before.modifiedTime ? "PASS" : "FAIL"}  restored to BEFORE (fields identical, modifiedTime ${before.modifiedTime} -> ${fin.modifiedTime})`);
    process.exit(0);
  }
  if (keep) {
    const session0 = { v: 1, email: "ryan@allegiscapital.com", sub: "guard", hd: "allegiscapital.com", at: t.at, scopes: t.scopes, exp: Math.floor(Date.now() / 1000) + 3000 } as Session;
    const before = await snap(t.at);
    writeFileSync(keep, JSON.stringify(before));
    line("BEFORE", { file_id: fileId, modifiedTime: before.modifiedTime, ...codes(before) });
    const s = await editOne({ file_id: fileId, set: { fiscal_year: 2020 } }, { session: session0, db: db({ CATALOG_APP_DB_URL: appDbUrl }) });
    const a = await snap(t.at);
    line("EDITED", { http: s.status, modifiedTime: a.modifiedTime, ...codes(a) });
    process.exit(s.status === 200 ? 0 : 1);
  }
  const session = { v: 1, email: "ryan@allegiscapital.com", sub: "guard", hd: "allegiscapital.com", at: t.at, scopes: t.scopes, exp: Math.floor(Date.now() / 1000) + 3000 } as Session;
  const D = db({ CATALOG_APP_DB_URL: appDbUrl });
  const before = await snap(t.at);
  line("BEFORE", { file_id: fileId, modifiedTime: before.modifiedTime, ...codes(before) });
  const fy0 = decodeLabels(before.labelInfo as never).fiscal_year;
  const fy1 = fy0 && fy0 > 1990 ? fy0 - 1 : 2020;

  const restore = async () => {
    const r = await fetch(`https://www.googleapis.com/drive/v3/files/${fileId}/modifyLabels`, {
      method: "POST", headers: { authorization: `Bearer ${t.at}`, "content-type": "application/json" },
      body: JSON.stringify({ kind: "drive#modifyLabelsRequest", labelModifications: restoreMods(before, await snap(t.at)) }),
    });
    line("RESTORE", { http: r.status });
  };
  let s: { status: number; body: Record<string, unknown> }, b: typeof s, a1: Snap, a2: Snap;
  try {
    s = await editOne({ file_id: fileId, set: { fiscal_year: fy1 } }, { session, db: D });
    line("SINGLE", { http: s.status, ...s.body });
    a1 = await snap(t.at);
    line("AFTER1", { modifiedTime: a1.modifiedTime, ...codes(a1) });

    b = await editBulk({ file_ids: [fileId], set: { fiscal_year: fy1 - 1 }, confirm: true }, { session, db: D });
    line("BULK", { http: b.status, report: (b.body as { report?: unknown }).report });
    a2 = await snap(t.at);
    line("AFTER2", { modifiedTime: a2.modifiedTime, ...codes(a2) });
  } finally {
    await restore(); // always put the pilot file back, even if a step above failed (CISO review)
  }
  const fin = await snap(t.at);
  line("FINAL", { modifiedTime: fin.modifiedTime, ...codes(fin) });
  const handlingSame = JSON.stringify(before.labels.find((l) => l.id === LABEL_IDS.handling)) === JSON.stringify(fin.labels.find((l) => l.id === LABEL_IDS.handling));
  const ok = s.status === 200 && b.status === 200 && before.modifiedTime === a1.modifiedTime && a1.modifiedTime === a2.modifiedTime && a2.modifiedTime === fin.modifiedTime;
  console.log(`${ok ? "PASS" : "FAIL"}  G-E2 modifiedTime unchanged by the single edit, the bulk edit and the restore: ${before.modifiedTime} -> ${a1.modifiedTime} -> ${a2.modifiedTime} -> ${fin.modifiedTime}`);
  console.log(`${same(before, fin) ? "PASS" : "FAIL"}  G-E2 restore: Allegis Document / Execution / Catalog Review fields identical to BEFORE`);
  console.log(`${handlingSame ? "PASS" : "FAIL"}  G-E2 Handling label untouched throughout`);
  process.exit(ok && same(before, fin) && handlingSame ? 0 : 1);
})().catch((e) => { console.error("ERROR", (e as Error).message); process.exit(2); });
