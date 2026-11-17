import { changedFields, decodeLabels, INCLUDE_LABELS, type Compared, type LiveValues } from "./labels";
import { driveBatchGet, isTransient, type BatchItem, type FetchLike } from "./google";

/**
 * Condition 1: access is checked live before display. For the visible page, ONE Drive batch files.get
 * as the signed-in user. A row the user cannot open is dropped and counted - never shown.
 */
export const LIVE_FIELDS = "id,name,webViewLink,labelInfo";

export interface DbRow {
  file_id: string;
  [k: string]: unknown;
}
export interface LiveRow<T extends DbRow> {
  db: T;
  name: string; // from Drive, as the user - sent to the browser only, never logged or stored
  web_view_link: string;
  live: LiveValues;
  changed: Compared[];
}
export interface LiveResult<T extends DbRow> {
  rows: LiveRow<T>[];
  notShown: { noAccess: number; checkFailed: number; total: number };
  sessionExpired: boolean;
}

export function applyLiveCheck<T extends DbRow>(rows: T[], drive: Map<string, BatchItem>): LiveResult<T> {
  const out: LiveRow<T>[] = [];
  let noAccess = 0, checkFailed = 0, unauth = 0;
  for (const r of rows) {
    const item = drive.get(r.file_id);
    if (!item) { checkFailed++; continue; }
    if (item.status === 200 && item.body) {
      const live = decodeLabels(item.body.labelInfo as never);
      // defence in depth: a file whose LIVE Handling tier is secret is never displayed (R-010)
      if (live.tier === "secret") { noAccess++; continue; }
      out.push({
        db: r,
        name: String(item.body.name ?? ""),
        web_view_link: String(item.body.webViewLink ?? ""),
        live,
        changed: changedFields(r as Partial<Record<Compared, unknown>>, live),
      });
      continue;
    }
    if (item.status === 401) { unauth++; checkFailed++; continue; }
    if (isTransient(item)) { checkFailed++; continue; }
    noAccess++; // 404 / 403 (permission) / anything else: the user cannot open it
  }
  return { rows: out, notShown: { noAccess, checkFailed, total: noAccess + checkFailed }, sessionExpired: unauth > 0 && unauth === rows.length };
}

export async function liveCheck<T extends DbRow>(accessToken: string, rows: T[], f?: FetchLike): Promise<LiveResult<T>> {
  if (!rows.length) return { rows: [], notShown: { noAccess: 0, checkFailed: 0, total: 0 }, sessionExpired: false };
  const drive = await driveBatchGet(accessToken, rows.map((r) => r.file_id), { fields: LIVE_FIELDS, includeLabels: INCLUDE_LABELS }, f);
  return applyLiveCheck(rows, drive);
}
