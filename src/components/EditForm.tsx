"use client";
import { useEffect, useMemo, useState } from "react";
import { api, type Row } from "./client";

export type FieldInfo = { key: string; title: string; type: "one" | "many" | "int" | "date"; published: boolean; bulk: boolean; choices: { code: string; meaning: string }[] };
type Val = string | number | string[] | null;

let cache: Promise<{ fields: FieldInfo[]; canWrite: boolean }> | null = null;
export function editInfo() {
  cache ??= api<{ fields: FieldInfo[]; canWrite: boolean }>("/api/edit");
  return cache;
}

function current(row: Row, key: string): Val {
  const v = (row as unknown as Record<string, unknown>)[key];
  if (Array.isArray(v)) return v.map(String);
  if (v == null || v === "") return null;
  return key === "fiscal_year" ? Number(v) : String(v).slice(0, key.endsWith("_date") ? 10 : undefined);
}
const same = (a: Val, b: Val) => JSON.stringify(Array.isArray(a) ? [...a].sort() : a) === JSON.stringify(Array.isArray(b) ? [...b].sort() : b);

/** One field's input, by type. Pick-lists show code + meaning. */
export function FieldInput({ f, value, onChange }: { f: FieldInfo; value: Val; onChange: (v: Val) => void }) {
  if (f.type === "one") {
    return (
      <select className="input" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || null)} aria-label={f.title}>
        <option value="">(blank)</option>
        {f.choices.map((c) => <option key={c.code} value={c.code}>{c.meaning === c.code ? c.code : `${c.meaning} · ${c.code}`}</option>)}
      </select>
    );
  }
  if (f.type === "many") {
    const sel = (value as string[]) ?? [];
    return (
      <div className="multi">
        {sel.map((c) => (
          <span key={c} className="chip"><code>{c}</code><button type="button" aria-label={`Remove ${c}`} onClick={() => onChange(sel.filter((x) => x !== c))}>×</button></span>
        ))}
        <select className="input" value="" onChange={(e) => e.target.value && onChange([...sel, e.target.value])} aria-label={`Add ${f.title}`}>
          <option value="">+ add</option>
          {f.choices.filter((c) => !sel.includes(c.code)).map((c) => <option key={c.code} value={c.code}>{c.meaning === c.code ? c.code : `${c.code} · ${c.meaning}`}</option>)}
        </select>
      </div>
    );
  }
  if (f.type === "int") return <input className="input" type="number" min={1990} max={2100} value={value == null ? "" : String(value)} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)} aria-label={f.title} />;
  return <input className="input" type="date" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || null)} aria-label={f.title} />;
}

/** Item 8 · single edit in Find's side panel and the Review form. Writes the labels on the file as you and marks it Confirmed. */
/** source: where the edit was made (logged on app.review_event): Find's side panel or the Review form. */
export function EditForm({ row, onSaved, source = "find_single" }: { row: Row; onSaved: (patch: Partial<Row>) => void; source?: "find_single" | "review_edit" }) {
  const [info, setInfo] = useState<{ fields: FieldInfo[]; canWrite: boolean } | null>(null);
  const [vals, setVals] = useState<Record<string, Val>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { editInfo().then(setInfo).catch((e) => setMsg((e as Error).message)); }, []);
  useEffect(() => { setVals({}); setMsg(null); }, [row.file_id]);

  const fields = useMemo(() => (info?.fields ?? []).filter((f) => f.published), [info]);
  const pending = (info?.fields ?? []).filter((f) => !f.published).map((f) => f.title);
  const value = (k: string) => (k in vals ? vals[k] : current(row, k));
  const changed = Object.fromEntries(Object.entries(vals).filter(([k, v]) => !same(v, current(row, k))));
  const n = Object.keys(changed).length;

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await api("/api/edit", { method: "POST", body: JSON.stringify({ file_id: row.file_id, set: changed, source }) });
      onSaved({ ...(changed as Partial<Row>), review_status: "confirmed" });
      setVals({}); setMsg("Saved on the file in Drive, and marked Confirmed.");
    } catch (e) {
      const b = (e as { body?: { error?: string; reason?: string; drive_status?: number } }).body;
      setMsg(`Not saved: ${b?.reason ?? b?.error ?? (e as Error).message}${b?.drive_status ? ` (Drive ${b.drive_status})` : ""}`);
    } finally { setBusy(false); }
  };

  if (!info) return msg ? <div className="error small">{msg}</div> : null;
  return (
    <form className="edit-form" onSubmit={(e) => { e.preventDefault(); if (n) save(); }}>
      <div className="cap">Edit labels</div>
      <div className="edit-grid">
        {fields.filter((f) => f.key !== "executed_date" || value("stage") === "fully_executed").map((f) => (
          <label key={f.key} className={vals[f.key] !== undefined && !same(vals[f.key], current(row, f.key)) ? "dirty" : ""}>
            <span className="cap">{f.title}</span>
            <FieldInput f={f} value={value(f.key)} onChange={(v) => setVals((s) => ({ ...s, [f.key]: v, ...(f.key === "stage" && v !== "fully_executed" ? { executed_date: null } : {}) }))} />
          </label>
        ))}
      </div>
      {pending.length ? <p className="small muted">Not published on Drive yet, so not editable: {pending.join(", ")}.</p> : null}
      <p className="small muted">Saving writes these labels on the file as you, sets Catalog Review to Confirmed with you as reviewer, and logs the change. Handling is never editable here.</p>
      <div className="actions">
        <button className="btn primary sm" type="submit" disabled={!n || busy}>{busy ? "Saving…" : n ? `Save ${n} change${n > 1 ? "s" : ""}` : "No changes"}</button>
        {n ? <button className="btn sm" type="button" onClick={() => setVals({})}>Undo</button> : null}
      </div>
      {msg ? <div className="small" role="status">{msg}</div> : null}
    </form>
  );
}

/** Item 8 · bulk edit: choose a value, preview (count + change), confirm, then a done / skipped / failed report. */
export function BulkEditDialog({ field, ids, onClose, onDone }: { field: FieldInfo; ids: string[]; onClose: () => void; onDone: () => void }) {
  const [value, setValue] = useState<Val>(null);
  const [step, setStep] = useState<"pick" | "preview" | "running" | "done">("pick");
  const [preview, setPreview] = useState<{ files: number; in_scope: number; not_in_scope: number } | null>(null);
  const [report, setReport] = useState<Record<string, number | boolean> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const meaning = (v: Val) => Array.isArray(v) ? v.join(", ") : v == null ? "(blank)" : field.choices.find((c) => c.code === v)?.meaning ?? String(v);
  const call = async (confirm: boolean) => {
    setErr(null);
    try {
      const r = await api<{ preview?: boolean; files: number; in_scope: number; not_in_scope: number; report?: Record<string, number | boolean> }>("/api/edit/bulk", {
        method: "POST", body: JSON.stringify({ file_ids: ids, set: { [field.key]: value }, confirm }),
      });
      if (confirm) { setReport(r.report ?? null); setStep("done"); onDone(); } else { setPreview(r); setStep("preview"); }
    } catch (e) {
      const b = (e as { body?: { error?: string; reason?: string } }).body;
      setErr(b?.reason ?? b?.error ?? (e as Error).message); setStep(confirm ? "preview" : "pick");
    }
  };
  return (
    <div className="drawer-backdrop center-modal" onMouseDown={(e) => { if (e.target === e.currentTarget && step !== "running") onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="bulk-title">
        <header><h2 id="bulk-title">Set {field.title.toLowerCase()} on {ids.length} file{ids.length > 1 ? "s" : ""}</h2></header>
        <div className="modal-body">
          {step === "pick" ? (
            <label className="field"><span className="cap">New {field.title.toLowerCase()}</span><FieldInput f={field} value={value} onChange={setValue} /></label>
          ) : null}
          {step === "preview" && preview ? (
            <div>
              <p>Change <b>{field.title}</b> to <b>{meaning(value)}</b> on <b>{preview.in_scope.toLocaleString()}</b> file{preview.in_scope === 1 ? "" : "s"}.</p>
              {preview.not_in_scope ? <p className="small muted">{preview.not_in_scope} selected file(s) are outside the catalog scope and will be skipped.</p> : null}
              <p className="small muted">Each file is checked against Drive as you first; any you can&apos;t change is skipped. Every written file is marked Confirmed with you as reviewer. At most 500 files per action.</p>
            </div>
          ) : null}
          {step === "running" ? <p>Writing labels in batches…</p> : null}
          {step === "done" && report ? (
            <ul className="report">
              <li><b>{String(report.done)}</b> done</li>
              <li><b>{String(Number(report.skipped_no_access) + Number(report.skipped_not_in_scope))}</b> skipped (no access or out of scope)</li>
              {Number(report.skipped_check_failed) ? <li><b>{String(report.skipped_check_failed)}</b> skipped (Drive check failed, retry)</li> : null}
              <li><b>{String(report.failed)}</b> failed</li>
            </ul>
          ) : null}
          {err ? <p className="error small">{err}</p> : null}
        </div>
        <footer className="actions">
          {step === "pick" ? <button className="btn primary sm" onClick={() => call(false)}>Preview</button> : null}
          {step === "preview" ? <button className="btn primary sm" onClick={() => { setStep("running"); call(true); }} disabled={!preview?.in_scope}>Confirm and write</button> : null}
          <button className="btn sm" onClick={onClose} disabled={step === "running"}>{step === "done" ? "Close" : "Cancel"}</button>
        </footer>
      </div>
    </div>
  );
}
