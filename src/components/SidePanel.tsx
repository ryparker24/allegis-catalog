"use client";
import { previewUrl, show, type Row } from "./client";
import { shownName } from "./bus";
import { Icon } from "./icons";

/** Drive's own preview in an iframe (Google enforces access inside it) + "Open in Drive". */
export function SidePanel({ row, onClose, children }: { row: Row; onClose: () => void; children?: React.ReactNode }) {
  const name = shownName(row.name, row.file_id);
  return (
    <aside className="panel" aria-label="File preview">
      <div className="panel-head">
        <div className="grow">
          <div className="kicker">Drive preview</div>
          <div className="panel-title" title={name}>{name}</div>
        </div>
        <a className="btn sm" href={row.web_view_link || `https://drive.google.com/file/d/${row.file_id}/view`} target="_blank" rel="noopener noreferrer"><Icon name="external" />Open in Drive</a>
        <button className="btn sm outline" onClick={onClose} aria-label="Close preview"><Icon name="x" /></button>
      </div>
      <div className="panel-body">
        <iframe className="preview" src={previewUrl(row.file_id)} title="Drive preview" allow="autoplay" referrerPolicy="no-referrer" />
        <dl className="facts">
          {(["kind", "entities", "portcos", "fiscal_year", "period", "stage", "executed_date", "tier", "review_status"] as const).map((k) => (
            <div key={k}>
              <dt>{({ entities: "entity", portcos: "portco", tier: "handling" } as Record<string, string>)[k] ?? k.replace(/_/g, " ")}</dt>
              <dd>
                {show(k, row[k as keyof Row]) || <span className="muted">–</span>}
                {row.changed.includes(k) ? <span className="chg" title={`Catalog DB: ${show(k, row.catalog[k]) || "(empty)"}`}>changed in Drive</span> : null}
              </dd>
            </div>
          ))}
          <div><dt>file id</dt><dd><code>{row.file_id}</code></dd></div>
          <div><dt>catalog id</dt><dd><code>{row.document_id ?? ""}</code></dd></div>
        </dl>
        {children}
      </div>
    </aside>
  );
}
