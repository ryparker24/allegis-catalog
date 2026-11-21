/**
 * CAT-WO-06 · the side panel's "Matched from content, p. N–M" for one file's document (R-033 .. R-036): partner codes,
 * page ranges, anchor, confidence and reason codes read from page 1 (or each statement of a package). Codes only: no
 * page text and no name is stored anywhere, so none can be shown; names for the codes come from app.v_party as elsewhere.
 */
import type { Db } from "./db";
import { logEvent } from "./log";
import { accessFor } from "./checklists";
import type { FetchLike } from "./google";

const FILE_ID_RE = /^[A-Za-z0-9_-]{10,80}$/;
const CODE_RE = /^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$/;

export type ContentMatch = {
  seq: number; page_from: number; page_to: number; partner_code: string | null; confidence: "high" | "medium" | "low" | "none";
  anchor: string | null; reason: string | null; lane: boolean;
};
export type ContentRead = {
  page_count: number | null; outcome: string; ocr_used: boolean; read_at: string | null;
  content_fiscal_year: number | null; content_quarter: number | null; content_entity: string | null; content_disagrees: string[] | null;
};

export const REASON_LABEL: Record<string, string> = {
  NO_ROSTER_MATCH: "no roster partner found on the page", NOT_IN_FUND: "a partner of another fund",
  MULTIPLE: "several partners", CONFLICT_PERSON: "differs from a person's Subject", CONFLICT_PORTAL: "differs from the portal posting",
  MEDIUM: "not certain",
};

/** pages "p. 3" or "p. 3–5" */
export function pageRange(a: number | null | undefined, b: number | null | undefined): string {
  if (!a) return "";
  return !b || b === a ? `p. ${a}` : `p. ${a}–${b}`;
}

/** GET /api/content?file_id=… → {read, matches}. The file must be one the user can open right now. */
export async function contentFor(D: Db, token: string, fileId: string, f?: FetchLike): Promise<{ status: number; body: Record<string, unknown> }> {
  if (!FILE_ID_RE.test(fileId)) return { status: 400, body: { error: "bad_file_id" } };
  const acc = await accessFor(token, [fileId], f);
  if (acc.expired) return { status: 401, body: { error: "signin_required", login: "/api/auth/login" } };
  if (acc.map.get(fileId)?.state !== "ok") {
    logEvent("content_read", { file_id: fileId, count: 0, dropped_no_access: 1 });
    return { status: 403, body: { error: "no_access" } };
  }
  const q = await D.rows<{ document_id: string | null }>("SELECT document_id::text AS document_id FROM app.v_find_x WHERE file_id = $1", [fileId]);
  if (!q.length) return { status: 403, body: { error: "no_access" } };
  const did = q[0].document_id;
  if (!did) return { status: 200, body: { read: null, matches: [] } };
  const rows = await D.rows<ContentMatch & ContentRead>(
    `SELECT seq, page_from, page_to, partner_code, confidence, anchor, reason, lane, page_count, outcome, ocr_used, read_at::text AS read_at,
            content_fiscal_year, content_quarter, content_entity, content_disagrees
       FROM app.v_doc_content WHERE document_id = $1::bigint ORDER BY seq, page_from LIMIT 400`, [did]);
  const matches: ContentMatch[] = rows
    .filter((r) => r.partner_code == null || CODE_RE.test(r.partner_code))
    .map(({ seq, page_from, page_to, partner_code, confidence, anchor, reason, lane }) => ({ seq, page_from, page_to, partner_code, confidence, anchor, reason, lane }));
  const r0 = rows[0];
  const read: ContentRead | null = r0 ? {
    page_count: r0.page_count, outcome: r0.outcome, ocr_used: r0.ocr_used, read_at: r0.read_at, content_fiscal_year: r0.content_fiscal_year,
    content_quarter: r0.content_quarter, content_entity: r0.content_entity, content_disagrees: r0.content_disagrees,
  } : null;
  logEvent("content_read", { file_id: fileId, document_id: did, count: matches.length });
  return { status: 200, body: { read, matches } };
}
