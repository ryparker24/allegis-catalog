"use client";
/**
 * CAT-WO-06 · "Matched from content, p. N–M" in the side panel: which roster partner codes were read from the
 * document's page 1 (or each statement of a package / bundle), with page ranges. Codes only (R-033).
 */
import { useEffect, useState } from "react";
import { api, type Row } from "./client";

type Match = { seq: number; page_from: number; page_to: number; partner_code: string | null; confidence: string; anchor: string | null; reason: string | null; lane: boolean };
type Read = { page_count: number | null; outcome: string; ocr_used: boolean; read_at: string | null; content_fiscal_year: number | null;
              content_quarter: number | null; content_entity: string | null; content_disagrees: string[] | null };
type Resp = { read: Read | null; matches: Match[] };

const REASON: Record<string, string> = {
  NO_ROSTER_MATCH: "no roster partner found", NOT_IN_FUND: "a partner of another fund", MULTIPLE: "several partners",
  CONFLICT_PERSON: "differs from a person's Subject", CONFLICT_PORTAL: "differs from the portal posting",
};
const DIS: Record<string, string> = { fiscal_year: "fiscal year", period: "period", entity: "entity" };

export function pageRange(a: number | null | undefined, b: number | null | undefined): string {
  if (!a) return "";
  return !b || b === a ? `p. ${a}` : `p. ${a}–${b}`;
}

export function matchLine(m: Match): string {
  const conf = m.confidence === "high" ? "matched" : m.confidence === "medium" ? "possible (not certain)" : m.confidence === "low" ? "possible" : "no match";
  return [pageRange(m.page_from, m.page_to), m.partner_code ?? "—", conf, m.reason ? REASON[m.reason] ?? m.reason : null,
          m.lane ? "in Match subject" : null].filter(Boolean).join(" · ");
}

export function ContentPanel({ row }: { row: Row }) {
  const [d, setD] = useState<Resp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setD(null); setErr(null);
    if (row.document_id == null) return;
    api<Resp>(`/api/content?file_id=${encodeURIComponent(row.file_id)}`).then(setD).catch((e) => setErr((e as Error).message));
  }, [row.file_id, row.document_id]);
  if (row.document_id == null) return null;
  if (err && !d) return <p className="muted small">Content matches not loaded: {err}</p>;
  if (!d || !d.read) return null;
  const hi = d.matches.filter((m) => m.confidence === "high" && m.partner_code);
  const first = hi.length ? Math.min(...hi.map((m) => m.page_from)) : null;
  const last = hi.length ? Math.max(...hi.map((m) => m.page_to)) : null;
  return (
    <section className="panel-section" aria-label="Matched from content">
      <div className="cap">Matched from content{first ? `, ${pageRange(first, last)}` : ""}</div>
      <p className="muted small">
        Read from the page{d.read.ocr_used ? " (OCR on this machine)" : ""}; only codes and page numbers are kept.
        {d.read.content_disagrees?.length ? ` Page 1 disagrees on: ${d.read.content_disagrees.map((x) => DIS[x] ?? x).join(", ")}.` : ""}
      </p>
      {d.matches.length ? (
        <ol className="timeline">
          {d.matches.map((m) => <li key={`${m.seq}-${m.page_from}-${m.partner_code ?? "none"}`}>{matchLine(m)}</li>)}
        </ol>
      ) : <p className="muted small">No partner read ({d.read.outcome}).</p>}
    </section>
  );
}
