"use client";
/**
 * CAT-WO-04 · Versions in the side panel: every member of the document's version family that the user can open (live
 * check as the user, R-020; the rest are a count only), each with its role, stage or status, date and Open in Drive.
 * Actions (person-set, never undone by the nightly run): mark as current, remove from family, move to another family,
 * mark as amendment of. In screenshot mode (?mask=1) names are masked like everywhere else.
 */
import { useCallback, useEffect, useState } from "react";
import { api, show, type Row } from "./client";
import { maskNames, shownName } from "./bus";

export type Member = {
  document_id: string; role: string | null; supersedes: string | null; amends: string | null; person_set: boolean; person_current: boolean;
  kind: string | null; stage: string | null; status: string | null; effective_date: string | null; fiscal_year: number | null;
  file_id: string | null; modified_time: string | null; name: string; link: string;
};
type Family = { family_id: string; confidence: string; reason: string[]; current_document_id: string | null; size: number };
type Resp = { family: Family | null; members: Member[]; not_shown: number };

const CONF: Record<string, string> = { high: "matched automatically", medium: "proposed (waiting in Review › Link versions)", person: "reviewed by a person" };
const REASON: Record<string, string> = {
  stem: "same name apart from version marks", "similar stem": "similar name", "same name": "identical name", kind: "kind", entities: "entities",
  subject: "subject", period: "period", "one key missing": "one key missing on a member", "no version marker": "no version marker",
  "amendment base unclear": "which base it amends is unclear", "dates only": "names differ only by a date", person: "set by a person",
};

export function memberLine(m: Member) {
  const st = m.stage && m.stage !== "n_a" ? show("stage", m.stage) : m.status ? show("status", m.status) : "no stage / status";
  const date = m.effective_date ?? (m.modified_time ? `modified ${m.modified_time.slice(0, 10)}` : null);
  return [show("version_role", m.role) || "-", st, date].filter(Boolean).join(" · ");
}

export function VersionsPanel({ row, onChanged }: { row: Row; onChanged?: () => void }) {
  const [d, setD] = useState<Resp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [moveTo, setMoveTo] = useState("");
  const [baseOf, setBaseOf] = useState("");
  const load = useCallback(() => {
    setErr(null);
    api<Resp>(`/api/versions?file_id=${encodeURIComponent(row.file_id)}`).then(setD).catch((e) => setErr((e as Error).message));
  }, [row.file_id]);
  useEffect(() => { setD(null); load(); }, [load]);

  const doc = row.document_id == null ? null : String(row.document_id);
  const act = async (body: Record<string, unknown>, ask?: string) => {
    if (ask && !window.confirm(ask)) return;
    setBusy(true); setErr(null);
    try {
      await api("/api/versions", { method: "POST", body: JSON.stringify(body) });
      load(); onChanged?.();
    } catch (e) {
      const b = (e as { body?: { reason?: string; error?: string } }).body;
      setErr(b?.reason ?? b?.error ?? (e as Error).message);
    } finally { setBusy(false); }
  };

  if (!doc) return null;
  if (err && !d) return <p className="muted small">Versions not loaded: {err}</p>;
  if (!d) return <p className="muted small">Loading versions…</p>;
  const masked = maskNames();
  const me = d.members.find((m) => m.document_id === doc);
  return (
    <div className="versions">
      <div className="cap">Versions{d.family ? ` (${d.family.size})` : ""}</div>
      {!d.family ? <p className="muted small">Not linked to other versions.</p> : (
        <>
          <p className="muted small">
            Family {d.family.family_id} · {CONF[d.family.confidence] ?? d.family.confidence}
            {d.family.reason?.length ? ` · matched on ${d.family.reason.map((r) => REASON[r] ?? r).join(", ")}` : ""}
          </p>
          <ol className="timeline">
            {d.members.map((m) => (
              <li key={m.document_id} className={m.role === "current" ? "cur" : ""}>
                <div><b>{show("version_role", m.role) || "-"}</b>{m.document_id === doc ? <span className="muted small"> · this document</span> : null}{m.person_set ? <span className="muted small"> · set by a person</span> : null}</div>
                <div className="small">{memberLine(m)}</div>
                <div className="small">
                  <span title={masked ? undefined : m.name}>{shownName(m.name, m.file_id ?? m.document_id)}</span>
                  {" · "}<code>catalog {m.document_id}</code>
                  {m.supersedes ? <span className="muted"> · superseded by {m.supersedes}</span> : null}
                  {m.amends ? <span className="muted"> · amends {m.amends}</span> : null}
                  {" · "}<a href={m.link} target="_blank" rel="noopener noreferrer">Open in Drive</a>
                </div>
              </li>
            ))}
          </ol>
          {d.not_shown ? <p className="muted small">{d.not_shown} more version{d.not_shown > 1 ? "s" : ""} you can&apos;t open (not shown).</p> : null}
        </>
      )}
      <div className="row wrap small" style={{ gap: 6, marginTop: 6 }}>
        {d.family && me?.role !== "current" ? <button className="btn sm" disabled={busy} onClick={() => act({ action: "mark_current", document: doc })}>Mark as current</button> : null}
        {d.family ? <button className="btn sm outline" disabled={busy} onClick={() => act({ action: "remove", document: doc }, "Take this document out of its family? It will not be grouped again by the nightly run.")}>Remove from family</button> : null}
      </div>
      <div className="row wrap small" style={{ gap: 6, marginTop: 6 }}>
        <input className="input sm" inputMode="numeric" placeholder="catalog ID in the other family" value={moveTo} onChange={(e) => setMoveTo(e.target.value.replace(/\D/g, "").slice(0, 12))} style={{ width: 200 }} />
        <button className="btn sm outline" disabled={busy || !moveTo} onClick={() => act({ action: "move", document: doc, target: moveTo })}>Move to that family</button>
      </div>
      <div className="row wrap small" style={{ gap: 6, marginTop: 6 }}>
        <input className="input sm" inputMode="numeric" placeholder="catalog ID of the base document" value={baseOf} onChange={(e) => setBaseOf(e.target.value.replace(/\D/g, "").slice(0, 12))} style={{ width: 200 }} />
        <button className="btn sm outline" disabled={busy || !baseOf} onClick={() => act({ action: "amends", document: doc, base: baseOf })}>Mark as amendment of</button>
      </div>
      {err ? <p className="error small">{err}</p> : null}
    </div>
  );
}

type LaneFamily = { family_id: string; reason: string[]; size: number; members: Member[]; not_shown: number };
type LaneResp = { families: LaneFamily[]; total: number; page: number; page_size: number };

/** Review lane "Link versions": proposed (medium) families with their members and why they matched; Accept, Split
 *  (the ticked members leave) and Pick current. Each decision is person-set; the family then leaves the lane. */
export function LinkVersionsLane() {
  const [d, setD] = useState<LaneResp | null>(null);
  const [page, setPage] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ticked, setTicked] = useState<Record<string, Set<string>>>({});
  const load = useCallback((p: number) => {
    setErr(null);
    api<LaneResp>(`/api/versions/lane?page=${p}`).then((r) => { setD(r); setTicked({}); }).catch((e) => setErr((e as Error).message));
  }, []);
  useEffect(() => { load(page); }, [load, page]);
  const act = async (body: Record<string, unknown>) => {
    setBusy(true); setErr(null);
    try { await api("/api/versions", { method: "POST", body: JSON.stringify(body) }); load(page); }
    catch (e) { const b = (e as { body?: { reason?: string; error?: string } }).body; setErr(b?.reason ?? b?.error ?? (e as Error).message); }
    finally { setBusy(false); }
  };
  const tick = (f: string, doc: string) => setTicked((t) => {
    const s = new Set(t[f] ?? []); if (s.has(doc)) s.delete(doc); else s.add(doc);
    return { ...t, [f]: s };
  });
  if (err && !d) return <section className="card"><p className="error">Link versions not loaded: {err}</p></section>;
  if (!d) return <section className="card"><p className="muted">Loading proposed families…</p></section>;
  const last = Math.max(0, Math.ceil(d.total / d.page_size) - 1);
  return (
    <section className="card list-card" aria-label="Link versions">
      <div className="filterbar">
        <span className="summary"><b>{d.total.toLocaleString()}</b> proposed families · page {d.page + 1} of {last + 1}</span>
        <div className="tools">
          <button className="btn sm outline" disabled={page <= 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <button className="btn sm outline" disabled={page >= last} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      </div>
      <p className="muted small" style={{ margin: "6px 12px" }}>Families the catalog is not sure of: names similar but not equal, a key (subject or period) missing on a member, identical names with no version mark, or an amendment whose base is unclear. Nothing here is applied until you decide.</p>
      {err ? <p className="error small">{err}</p> : null}
      {d.families.map((f) => (
        <div key={f.family_id} className="lane-family">
          <div className="row wrap" style={{ gap: 8 }}>
            <b>Family {f.family_id}</b>
            <span className="muted small">{f.size} versions · matched on {f.reason.map((r) => REASON[r] ?? r).join(", ")}</span>
            <span className="grow" />
            <button className="btn sm primary" disabled={busy || !!f.not_shown} title={f.not_shown ? "Some members are not shown to you" : undefined} onClick={() => act({ action: "accept", family: f.family_id })}>Accept</button>
            <button className="btn sm outline" disabled={busy || !(ticked[f.family_id]?.size)} onClick={() => act({ action: "split", family: f.family_id, documents: [...(ticked[f.family_id] ?? [])] })}>Split ticked out</button>
          </div>
          <ol className="timeline">
            {f.members.map((m) => (
              <li key={m.document_id} className={m.role === "current" ? "cur" : ""}>
                <label className="row small" style={{ gap: 6 }}>
                  <input type="checkbox" checked={!!ticked[f.family_id]?.has(m.document_id)} onChange={() => tick(f.family_id, m.document_id)} />
                  <b>{show("version_role", m.role) || "-"}</b> · {memberLine(m)}
                </label>
                <div className="small">
                  {shownName(m.name, m.file_id ?? m.document_id)} · <code>catalog {m.document_id}</code> · {show("kind", m.kind)}{m.fiscal_year ? ` · FY ${m.fiscal_year}` : ""}
                  {" · "}<a href={m.link} target="_blank" rel="noopener noreferrer">Open in Drive</a>
                  {m.role !== "current" ? <> · <button className="link small" disabled={busy} onClick={() => act({ action: "mark_current", document: m.document_id })}>Pick as current</button></> : null}
                </div>
              </li>
            ))}
          </ol>
          {f.not_shown ? <p className="muted small">{f.not_shown} member{f.not_shown > 1 ? "s" : ""} you can&apos;t open (not shown); Accept needs every member.</p> : null}
        </div>
      ))}
    </section>
  );
}
