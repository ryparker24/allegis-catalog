/**
 * CAT-WO-05 · the side panel's portal postings for one file's document (R-030 / R-031): channel, posted date, the
 * portal's posting ID, the posting's document type and period, and how it was matched (file ID / md5 copy).
 * No partner, no name: the posted-to partner shows as the document's Subject code(s), which the app already gates.
 * The portals are read-only sources; nothing here reaches them.
 */
import type { Db } from "./db";
import { logEvent } from "./log";

const FILE_ID_RE = /^[A-Za-z0-9_-]{10,80}$/;

export type Posting = {
  posting_id: string; channel: "lp_portal" | "gp_portal"; posted_date: string | null; doc_type: string;
  fiscal_year: number | null; fiscal_quarter: number | null; match: "file_id" | "md5";
};

export const CHANNEL_LABEL: Record<string, string> = { lp_portal: "LP portal", gp_portal: "GP portal", datum: "Datum", email: "Email" };
export const DOC_TYPE_LABEL: Record<string, string> = {
  QR: "Quarterly report", CRR: "Capital statement", TAX: "Tax document", CC: "Capital call", K1: "K-1", ST: "Statement",
  CIA: "Carried interest agreement", GPL: "GP legal document", W2: "W-2", OTH: "Other",
};

/** GET /api/postings?file_id=… → {postings, published: {channels, first_date, ids}}. The file must be one Find shows. */
export async function postingsFor(D: Db, fileId: string): Promise<{ status: number; body: Record<string, unknown> }> {
  if (!FILE_ID_RE.test(fileId)) return { status: 400, body: { error: "bad_file_id" } };
  const q = await D.rows<{ document_id: string | null; published_channels: string[]; published_date: string | null; published_ids: string[] }>(
    "SELECT document_id::text AS document_id, published_channels, published_date::text AS published_date, published_ids FROM app.v_find_x WHERE file_id = $1",
    [fileId]);
  if (!q.length) return { status: 403, body: { error: "no_access" } };
  const d = q[0];
  if (!d.document_id) return { status: 200, body: { postings: [], published: null } };
  const rows = await D.rows<Posting>(
    `SELECT posting_id, channel, posted_date::text AS posted_date, doc_type, fiscal_year, fiscal_quarter, match
       FROM app.v_doc_posting WHERE document_id = $1::bigint ORDER BY posted_date NULLS LAST, posting_id LIMIT 100`,
    [d.document_id]);
  logEvent("postings_read", { file_id: fileId, document_id: d.document_id, count: rows.length });
  return {
    status: 200,
    body: {
      postings: rows,
      published: d.published_channels?.length ? { channels: d.published_channels, first_date: d.published_date, ids: d.published_ids } : null,
    },
  };
}
