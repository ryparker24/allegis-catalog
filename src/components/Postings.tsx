"use client";
/**
 * CAT-WO-05 · Published To in the side panel: where and when this document was posted (LP / GP portal), with the
 * portal's posting ID. No partner and no name are shown here (the posted-to partner is the document's Subject code).
 */
import { useEffect, useState } from "react";
import { api, type Row } from "./client";

type Posting = { posting_id: string; channel: string; posted_date: string | null; doc_type: string; fiscal_year: number | null; fiscal_quarter: number | null; match: string };
type Resp = { postings: Posting[]; published: { channels: string[]; first_date: string | null; ids: string[] } | null };

const CHANNEL: Record<string, string> = { lp_portal: "LP portal", gp_portal: "GP portal", datum: "Datum", email: "Email" };
const DOC_TYPE: Record<string, string> = {
  QR: "Quarterly report", CRR: "Capital statement", TAX: "Tax document", CC: "Capital call", K1: "K-1", ST: "Statement",
  CIA: "Carried interest agreement", GPL: "GP legal document", W2: "W-2", OTH: "Other",
};

export function postingLine(p: Posting) {
  const per = p.fiscal_year ? `${p.fiscal_year}${p.fiscal_quarter ? ` Q${p.fiscal_quarter}` : ""}` : null;
  return [CHANNEL[p.channel] ?? p.channel, p.posted_date ?? "no date", DOC_TYPE[p.doc_type] ?? p.doc_type, per, p.posting_id,
          p.match === "md5" ? "(an identical copy was posted)" : null].filter(Boolean).join(" · ");
}

export function PostingsPanel({ row }: { row: Row }) {
  const [d, setD] = useState<Resp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setD(null); setErr(null);
    if (row.document_id == null) return;
    api<Resp>(`/api/postings?file_id=${encodeURIComponent(row.file_id)}`).then(setD).catch((e) => setErr((e as Error).message));
  }, [row.file_id, row.document_id]);
  if (row.document_id == null) return null;
  if (err && !d) return <p className="muted small">Published To not loaded: {err}</p>;
  if (!d || !d.postings.length) return null;
  return (
    <section className="panel-section" aria-label="Published To">
      <div className="cap">Published To ({d.postings.length})</div>
      <p className="muted small">Posted in the portal = Issued (R-031). The partner is the document&apos;s Subject code.</p>
      <ol className="timeline">
        {d.postings.map((p) => <li key={p.posting_id}>{postingLine(p)}</li>)}
      </ol>
    </section>
  );
}
