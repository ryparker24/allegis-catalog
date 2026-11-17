"use client";
import { previewUrl, show, type Row } from "./client";

/** Drive's own preview in an iframe (Google enforces access inside it) + "Open in Drive". */
export function SidePanel({ row, onClose, children }: { row: Row; onClose: () => void; children?: React.ReactNode }) {
  return (
    <aside className="panel" aria-label="File preview">
      <div className="panel-head">
        <div className="panel-title" title={row.name}>{row.name}</div>
        <a className="btn" href={row.web_view_link || `https://drive.google.com/file/d/${row.file_id}/view`} target="_blank" rel="noopener noreferrer">Open in Drive</a>
        <button className="btn" onClick={onClose} aria-label="Close">x</button>
      </div>
      <iframe className="preview" src={previewUrl(row.file_id)} title="Drive preview" allow="autoplay" referrerPolicy="no-referrer" />
      <dl className="facts">
        {(["kind", "entities", "portcos", "fiscal_year", "period", "stage", "executed_date", "tier", "review_status"] as const).map((k) => (
          <div key={k}>
            <dt>{k.replace(/_/g, " ")}</dt>
            <dd>
              {show(k, row[k as keyof Row]) || <span className="muted">-</span>}
              {row.changed.includes(k) ? <span className="chg" title={`Catalog DB: ${show(k, row.catalog[k]) || "(empty)"}`}>changed in Drive</span> : null}
            </dd>
          </div>
        ))}
        <div><dt>file id</dt><dd><code>{row.file_id}</code></dd></div>
        <div><dt>catalog id</dt><dd><code>{row.document_id ?? ""}</code></dd></div>
      </dl>
      {children}
    </aside>
  );
}
