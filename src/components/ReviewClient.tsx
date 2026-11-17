"use client";
import { useCallback, useEffect, useState } from "react";
import { api, show, type NotShown, type Row } from "./client";
import { SidePanel } from "./SidePanel";
import { VOCAB } from "@/lib/vocab";

type Counts = { stage_unknown?: number; low_confidence_executed?: number; no_kind?: number; open_total?: number; reviewed_today?: number; reviewed_total?: number };
type Resp = { counts: Counts; page: number; pageRows: number; rows: Row[]; notShown: NotShown; canWrite: boolean };

const REASON: Record<string, string> = { stage_unknown: "Stage unknown", low_confidence_executed: "Fully executed (low confidence)", no_kind: "No kind" };
const SIGNAL: Record<string, string> = {
  sig_block: "signature block found", sig_page_image: "signature page is an image", scanned: "scanned", blank_line: "blank signature line",
  docusign: "DocuSign", digital_sig: "digital signature", exec_version: "'executed' in name", conformed: "conformed (/s/)", draft_mark: "draft mark",
  certificate: "e-sign certificate", esign_other: "other e-signature",
};
const STAGES = ["draft", "final_unexecuted", "partially_executed", "fully_executed", "n_a"] as const;
const SKIP_KEY = "catalog.review.skipped";

function why(r: Row): string {
  const parts = [REASON[r.queue_reason ?? ""] ?? r.queue_reason ?? ""];
  if (r.confidence) parts.push(`confidence ${r.confidence}`);
  if (r.stage_suggested && r.stage_suggested !== "unknown") parts.push(`scan suggests ${show("stage", r.stage_suggested)}`);
  const sig = (r.signals ?? []).map((s) => SIGNAL[s] ?? s);
  if (sig.length) parts.push(sig.join(", "));
  else if (r.queue_reason !== "no_kind") parts.push("no scan signals");
  return parts.join(" · ");
}
function loadSkipped(): string[] {
  try { return JSON.parse(sessionStorage.getItem(SKIP_KEY) ?? "[]"); } catch { return []; }
}

export function ReviewClient() {
  const [data, setData] = useState<Resp | null>(null);
  const [cur, setCur] = useState<Row | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [form, setForm] = useState({ status: "confirmed", stage: "", executed_date: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async (skip: string[]) => {
    const r = await api<Resp>(`/api/review?skip=${encodeURIComponent(skip.join(","))}`);
    setData(r);
    setCur(r.rows[0] ?? null);
  }, []);
  useEffect(() => { const s = loadSkipped(); setSkipped(s); load(s).catch((e) => setMsg(e.message)); }, [load]);
  useEffect(() => {
    if (!cur) return;
    const stage = cur.stage && cur.stage !== "unknown" ? cur.stage : cur.stage_suggested && cur.stage_suggested !== "unknown" ? cur.stage_suggested : "";
    setForm({ status: "confirmed", stage, executed_date: cur.executed_date ?? "", note: "" });
  }, [cur]);

  const next = (rows: Row[], fromId: string) => {
    const i = rows.findIndex((r) => r.file_id === fromId);
    return rows[i + 1] ?? null;
  };
  const skip = () => {
    if (!cur || !data) return;
    const s = [...skipped, cur.file_id];
    setSkipped(s);
    try { sessionStorage.setItem(SKIP_KEY, JSON.stringify(s)); } catch { /* storage unavailable: skip for this view only */ }
    const n = next(data.rows, cur.file_id);
    if (n) setCur(n); else load(s);
  };
  const confirm = async () => {
    if (!cur) return;
    setBusy(true); setMsg(null);
    try {
      await api("/api/review/confirm", { method: "POST", body: JSON.stringify({ file_id: cur.file_id, ...form, stage: form.stage || null, executed_date: form.executed_date || null, note: form.note || null }) });
      setMsg("Saved to Drive.");
      await load(skipped);
    } catch (e) {
      const b = (e as { body?: { error?: string; reason?: string; drive_status?: number } }).body;
      setMsg(`Not saved: ${b?.reason ?? b?.error ?? (e as Error).message}${b?.drive_status ? ` (Drive ${b.drive_status})` : ""}`);
    } finally { setBusy(false); }
  };

  const c = data?.counts ?? {};
  return (
    <div className="review">
      <div className="counters">
        <div className="ctr"><b>{(c.open_total ?? 0).toLocaleString()}</b><span>open</span></div>
        <div className="ctr"><b>{(c.stage_unknown ?? 0).toLocaleString()}</b><span>Stage unknown</span></div>
        <div className="ctr"><b>{(c.low_confidence_executed ?? 0).toLocaleString()}</b><span>Executed, low confidence</span></div>
        <div className="ctr"><b>{(c.no_kind ?? 0).toLocaleString()}</b><span>No kind</span></div>
        <div className="ctr"><b>{(c.reviewed_today ?? 0).toLocaleString()}</b><span>reviewed today</span></div>
        <div className="ctr"><b>{skipped.length}</b><span>skipped (this session)</span></div>
      </div>
      {data?.notShown.total ? (
        <div className="status warn">
          {data.notShown.noAccess ? `${data.notShown.noAccess} not shown (no access)` : ""}{data.notShown.noAccess && data.notShown.checkFailed ? " · " : ""}
          {data.notShown.checkFailed ? `${data.notShown.checkFailed} not shown (Drive check failed - retry)` : ""}
        </div>
      ) : null}
      <div className="review-body">
        <table className="grid queue">
          <thead><tr><th>file</th><th>why</th><th>stage</th><th>kind</th></tr></thead>
          <tbody>
            {(data?.rows ?? []).filter((r) => !skipped.includes(r.file_id)).map((r) => (
              <tr key={r.file_id} onClick={() => setCur(r)} className={cur?.file_id === r.file_id ? "sel" : ""}>
                <td className="name">{r.name}</td>
                <td className="why">{why(r)}</td>
                <td>{show("stage", r.stage)}{r.changed.includes("stage") ? <span className="chg">changed in Drive</span> : null}</td>
                <td>{show("kind", r.kind)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {cur ? (
          <SidePanel row={cur} onClose={() => setCur(null)}>
            <form className="review-form" onSubmit={(e) => { e.preventDefault(); confirm(); }}>
              <p className="why"><b>Why:</b> {why(cur)}</p>
              <fieldset>
                <legend>Execution label</legend>
                <label>Stage
                  <select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value, executed_date: e.target.value === "fully_executed" ? form.executed_date : "" })}>
                    <option value="">(leave unchanged)</option>
                    {STAGES.map((s) => <option key={s} value={s}>{VOCAB.stage[s]}</option>)}
                  </select>
                </label>
                <label>Executed date
                  <input type="date" value={form.executed_date} disabled={form.stage !== "fully_executed"} onChange={(e) => setForm({ ...form, executed_date: e.target.value })} />
                </label>
              </fieldset>
              <fieldset>
                <legend>Catalog Review label</legend>
                <label className="radio"><input type="radio" name="st" checked={form.status === "confirmed"} onChange={() => setForm({ ...form, status: "confirmed" })} /> Confirmed</label>
                <label className="radio"><input type="radio" name="st" checked={form.status === "wrong"} onChange={() => setForm({ ...form, status: "wrong" })} /> Wrong - see note</label>
                <label>Note<textarea value={form.note} maxLength={2000} rows={3} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
                <p className="muted small">Reviewed by is set to you. No other label or file property is changed.</p>
              </fieldset>
              <div className="actions">
                <button className="btn primary" type="submit" disabled={busy}>{data?.canWrite ? "Confirm and next" : "Confirm and next (asks for label-write access once)"}</button>
                <button className="btn" type="button" onClick={skip} disabled={busy}>Skip</button>
              </div>
              {msg ? <p className="status">{msg}</p> : null}
            </form>
          </SidePanel>
        ) : data && !data.rows.length ? <p className="center muted">Queue is empty on this page.</p> : null}
      </div>
    </div>
  );
}
