"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./client";
import { PageHeader } from "./AppShell";
import { maskNames, shownName } from "./bus";
import { display } from "@/lib/vocab";
import { LocationCell } from "./Location";

/** CAT-WO-03 item 5 · Checklists (Datum look): pick a checklist and a scope; one row per requirement, most urgent first. */
type Doc = { access: "ok"; file_id: string; name: string; link: string } | { access: "no_access" | "check_failed" | "out_of_scope" } | null;
type Req = {
  req_key: string; rule_id: string; entity_code: string; partner_code: string | null; partner_name: string | null; fiscal_year: number | null;
  fiscal_quarter: number | null; result: string; sub_status: string | null; urgency: number; best: Doc; best_kind: string | null; best_stage: string | null;
  best_status: string | null; best_date: string | null; best_reason: string | null; best_source: string | null; n_candidates: number;
  override_action: string | null; override_note: string | null; override_by: string | null; override_at: string | null;
};
type Rule = { id: string; checklist: string; title: string; subtype: string | null; subject: string };
type Resp = { rules: Rule[]; entities: string[]; years: number[]; quarters: boolean; counts: Record<string, number>; matched: number; rows: Req[]; canWrite: boolean };
type Cand = { kind: string; stage: string | null; status: string | null; date: string | null; satisfying: boolean; partner_conf: string | null; is_primary: boolean; doc: Doc; location?: string | null; location_folder_id?: string | null; other_locations?: number | null };
type State = { rule: string; entity: string | null; fy: number | null; q: number | null; results: string[]; sort: string; dir: "asc" | "desc"; pageSize: number; widths: Record<string, number>; tab: "rows" | "gaps" };
const DEFAULT: State = { rule: "LP-SUB", entity: null, fy: null, q: null, results: [], sort: "urgency", dir: "asc", pageSize: 25, widths: {}, tab: "rows" };

export const RESULT: Record<string, { label: string; cls: string; dot: string }> = {
  met: { label: "Met", cls: "res-met", dot: "🟢" },
  on_file: { label: "On file, not final", cls: "res-onfile", dot: "🟠" },
  missing: { label: "Missing", cls: "res-missing", dot: "🔴" },
  not_required: { label: "Not required", cls: "res-notreq", dot: "⚪" },
  none_found: { label: "None found (not tracked in Datum)", cls: "res-info", dot: "⚪" },
  no_roster: { label: "No roster in Datum", cls: "res-info", dot: "⚪" },
  applicability_not_set: { label: "Applicability not set", cls: "res-info", dot: "⚪" },
};
const SUB: Record<string, string> = {
  unknown: "stage / status unknown", draft: "draft", final_unexecuted: "final, unsigned", partially_executed: "partially executed",
  final_not_issued: "final, not marked issued", superseded: "superseded", not_satisfying_kind: "not the qualifying kind", partner_unconfirmed: "partner match not confirmed",
};
const COLS = [
  { key: "requirement", label: "Requirement", width: 300, sort: "entity" },
  { key: "result", label: "Result", width: 200, sort: "urgency" },
  { key: "best", label: "Best document", width: 300 },
  { key: "kind", label: "Kind", width: 150, sort: "kind" },
  { key: "stage", label: "Stage / status", width: 150 },
  { key: "date", label: "Date", width: 110, sort: "best_date" },
  { key: "why", label: "Why", width: 280 },
  { key: "candidates", label: "Other candidates", width: 140, sort: "candidates" },
];
const FUND_LEVEL = new Set(["AUDITED-FS", "K1-SET", "PCAP-Q"]);

export function period(r: { fiscal_year: number | null; fiscal_quarter: number | null }) {
  return r.fiscal_year ? (r.fiscal_quarter ? `${r.fiscal_year} Q${r.fiscal_quarter}` : `FY${r.fiscal_year}`) : "";
}
export function requirementLabel(r: Req, rule?: Rule) {
  const who = r.partner_code ? ` · ${r.partner_code}${r.partner_name && !maskNames() ? ` ${r.partner_name}` : ""}` : "";
  return `${r.entity_code}${who}${period(r) ? ` · ${period(r)}` : ""}${rule ? ` · ${rule.title.toLowerCase()}` : ""}`;
}
export function docCell(d: Doc) {
  if (!d) return <span className="muted">-</span>;
  if (d.access === "ok") return <a href={d.link} target="_blank" rel="noreferrer noopener">{shownName(d.name, d.file_id)}</a>;
  if (d.access === "no_access") return <span className="muted">on file (no access)</span>;
  if (d.access === "out_of_scope") return <span className="muted">on file (outside the catalog&apos;s scope)</span>;
  return <span className="muted">on file (Drive check failed - retry)</span>;
}

function Kpi({ cap, n, total, exp, on, onClick }: { cap: string; n: number; total: number; exp: string; on?: boolean; onClick: () => void }) {
  const pct = total ? Math.round((100 * n) / total) : 0;
  return (
    <button type="button" className={`ctr kpi link-card${on ? " on" : ""}`} onClick={onClick} aria-pressed={!!on}>
      <span className="k-cap">{cap}</span><span className="k-num">{n.toLocaleString()} <small className="muted">{pct}%</small></span><span className="k-exp">{exp}</span>
    </button>
  );
}

export function ChecklistsClient() {
  const [st, setSt] = useState<State>(DEFAULT);
  const [ready, setReady] = useState(false);
  const [data, setData] = useState<Resp | null>(null);
  const [page, setPage] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<Req | null>(null);
  const reqId = useRef(0);

  useEffect(() => {
    (async () => {
      const u = new URLSearchParams(window.location.search);
      let s = DEFAULT;
      try {
        const p = await api<{ value: Partial<State> | null }>("/api/prefs?key=checklists");
        if (p.value) s = { ...DEFAULT, ...p.value, widths: p.value.widths ?? {} } as State;
      } catch { /* defaults */ }
      if (u.get("tab") === "gaps") s = { ...s, tab: "gaps", rule: FUND_LEVEL.has(s.rule) ? s.rule : "AUDITED-FS" };
      setSt(s); setReady(true);
    })();
  }, []);
  const loadKey = JSON.stringify({ r: st.rule, e: st.entity, f: st.fy, q: st.q, rs: st.results, s: st.sort, d: st.dir, p: st.pageSize, page });
  const load = useCallback(async () => {
    const id = ++reqId.current;
    const u = new URLSearchParams({ rule: st.rule, sort: st.sort, dir: st.dir, pageSize: String(st.pageSize), page: String(page) });
    if (st.entity) u.set("entity", st.entity);
    if (st.fy) u.set("fy", String(st.fy));
    if (st.q) u.set("q", String(st.q));
    if (st.results.length) u.set("result", st.results.join(","));
    try {
      const r = await api<Resp>(`/api/checklists?${u}`);
      if (id === reqId.current) { setData(r); setErr(null); }
    } catch (e) {
      const b = (e as { body?: { error?: string; reason?: string } }).body;
      if (id === reqId.current) setErr(`${b?.error ?? (e as Error).message}${b?.reason ? ` (${b.reason})` : ""}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadKey]);
  useEffect(() => { if (ready) load(); }, [ready, load]);
  // remember the state per user (after a change only)
  const saved = useRef<string | null>(null);
  useEffect(() => {
    if (!ready) return;
    const v = JSON.stringify({ ...st });
    if (saved.current === null) { saved.current = v; return; }
    if (saved.current === v) return;
    const t = setTimeout(() => { saved.current = v; api("/api/prefs", { method: "PUT", body: JSON.stringify({ key: "checklists", value: JSON.parse(v) }) }).catch(() => {}); }, 800);
    return () => clearTimeout(t);
  }, [ready, st]);

  const upd = (p: Partial<State>) => { setSt((s) => ({ ...s, ...p })); setPage(0); };
  const rule = data?.rules.find((r) => r.id === st.rule);
  const total = Object.values(data?.counts ?? {}).reduce((a, b) => a + b, 0);
  const c = data?.counts ?? {};
  const toggleResult = (r: string) => upd({ results: st.results.includes(r) ? st.results.filter((x) => x !== r) : [...st.results, r] });
  const width = (k: string) => st.widths[k] ?? COLS.find((x) => x.key === k)!.width;
  const startResize = (k: string, e: React.PointerEvent) => {
    e.preventDefault();
    const x0 = e.clientX, w0 = width(k);
    const move = (ev: PointerEvent) => setSt((s) => ({ ...s, widths: { ...s.widths, [k]: Math.max(60, Math.min(900, Math.round(w0 + ev.clientX - x0))) } }));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const lastPage = data ? Math.max(0, Math.ceil(data.matched / st.pageSize) - 1) : 0;
  useEffect(() => { if (data && page > lastPage) setPage(lastPage); }, [data, page, lastPage]);   // e.g. the last row of the last page was linked
  const checklist = rule?.checklist ?? (FUND_LEVEL.has(st.rule) ? "fund_level" : "lp_subscriptions");

  return (
    <div className="checklists">
      <PageHeader title="Checklists"
        info={<>Requirements come from Datum (the partner roster and document types, loaded from the dated exports) and the ruled requirement rules. Each row shows the best document on file and why it does or doesn&apos;t qualify. A person&apos;s Link or Not required always wins; the nightly rebuild never undoes it. A file you can&apos;t open shows &quot;on file (no access)&quot;, without its name.</>}
        desc="Expected documents, the best document on file, and the gaps." />
      <div className="cl-bar card">
        <div className="seg" role="tablist" aria-label="Checklist">
          {[["lp_subscriptions", "LP subscriptions"], ["fund_level", "Fund-level set"]].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={checklist === k} className={checklist === k ? "on" : ""}
              onClick={() => upd({ rule: k === "fund_level" ? "AUDITED-FS" : "LP-SUB", fy: null, q: null, results: [], tab: k === "fund_level" ? st.tab : "rows" })}>{l}</button>
          ))}
        </div>
        <div className="seg" aria-label="Requirement">
          {(data?.rules ?? []).filter((r) => r.checklist === checklist).map((r) => (
            <button key={r.id} className={st.rule === r.id ? "on" : ""} onClick={() => upd({ rule: r.id, fy: null, q: null, results: [] })} title={r.subtype ? `Datum ${r.subtype}` : "catalog-only (no Datum subtype)"}>{r.title}</button>
          ))}
        </div>
        <label className="cap">Scope
          <select className="input" value={st.entity ?? ""} onChange={(e) => upd({ entity: e.target.value || null })}>
            <option value="">All entities</option>
            {(data?.entities ?? []).map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
        </label>
        {data?.years.length ? <label className="cap">Fiscal year
          <select className="input" value={st.fy ?? ""} onChange={(e) => upd({ fy: e.target.value ? Number(e.target.value) : null })}>
            <option value="">All</option>{data.years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select></label> : null}
        {data?.quarters ? <label className="cap">Quarter
          <select className="input" value={st.q ?? ""} onChange={(e) => upd({ q: e.target.value ? Number(e.target.value) : null })}>
            <option value="">All</option>{[1, 2, 3, 4].map((q) => <option key={q} value={q}>Q{q}</option>)}
          </select></label> : null}
        {FUND_LEVEL.has(st.rule) ? (
          <div className="seg" role="tablist" aria-label="View" style={{ marginLeft: "auto" }}>
            <button role="tab" aria-selected={st.tab === "rows"} className={st.tab === "rows" ? "on" : ""} onClick={() => setSt((s) => ({ ...s, tab: "rows" }))}>Rows</button>
            <button role="tab" aria-selected={st.tab === "gaps"} className={st.tab === "gaps" ? "on" : ""} onClick={() => setSt((s) => ({ ...s, tab: "gaps" }))}>Gaps</button>
          </div>
        ) : null}
      </div>
      <div className="counters">
        <Kpi cap="Met" n={c.met ?? 0} total={total} exp="An executed / final primary copy, not marked Wrong." on={st.results.includes("met")} onClick={() => toggleResult("met")} />
        <Kpi cap="On file, not final" n={c.on_file ?? 0} total={total} exp="Draft, unsigned, partly signed, or stage/status unknown." on={st.results.includes("on_file")} onClick={() => toggleResult("on_file")} />
        <Kpi cap="Missing" n={c.missing ?? 0} total={total} exp="No candidate found." on={st.results.includes("missing")} onClick={() => toggleResult("missing")} />
        <Kpi cap="Not required" n={c.not_required ?? 0} total={total} exp="Waived by a person, with a note." on={st.results.includes("not_required")} onClick={() => toggleResult("not_required")} />
        {(c.none_found ?? 0) + (c.no_roster ?? 0) + (c.applicability_not_set ?? 0) ? (
          <Kpi cap="Not checked" n={(c.none_found ?? 0) + (c.no_roster ?? 0) + (c.applicability_not_set ?? 0)} total={total}
            exp="None found (not tracked in Datum), no roster in Datum, or applicability not set."
            on={st.results.includes("no_roster")}
            onClick={() => { const info = ["none_found", "no_roster", "applicability_not_set"]; const on = st.results.includes("no_roster"); upd({ results: on ? st.results.filter((x) => !info.includes(x)) : [...new Set([...st.results, ...info])] }); }} />
        ) : null}
      </div>
      {err ? <div className="status error" role="alert">Could not load the checklist: {err}.</div> : null}
      {st.tab === "gaps" && FUND_LEVEL.has(st.rule)
        ? <Gaps rule={st.rule} entity={st.entity} onCell={(e, fy, q) => { upd({ entity: e, fy, q, results: [] }); setSt((s) => ({ ...s, tab: "rows" })); }} />
        : (
          <div className={open ? "find with-panel" : "find"}>
            <section className="card list-card" aria-label="Requirements">
              <div className="filterbar">
                <span className="summary">{data ? `${data.matched.toLocaleString()} requirement${data.matched === 1 ? "" : "s"}` : "Loading…"}{st.results.length ? ` · ${st.results.map((r) => RESULT[r]?.label ?? r).join(", ")}` : ""}</span>
                {st.results.length ? <button className="link small" onClick={() => upd({ results: [] })}>Clear filter</button> : null}
              </div>
              <div className="grid-wrap">
                <table className="grid" style={{ width: COLS.reduce((n, x) => n + width(x.key), 0) }}>
                  <colgroup>{COLS.map((x) => <col key={x.key} style={{ width: width(x.key) }} />)}</colgroup>
                  <thead><tr>{COLS.map((x) => {
                    const on = x.sort && st.sort === x.sort;
                    return (
                      <th key={x.key} aria-sort={on ? (st.dir === "asc" ? "ascending" : "descending") : undefined}>
                        <div className="th">
                          {x.sort ? <button type="button" className="lbl sortable" onClick={() => upd({ sort: x.sort!, dir: st.sort === x.sort && st.dir === "asc" ? "desc" : "asc" })}>{x.label}</button> : <span className="lbl">{x.label}</span>}
                          {x.sort ? <span className={`sort${on ? " on" : ""}`} aria-hidden="true">{on ? (st.dir === "asc" ? "↑" : "↓") : "↕"}</span> : null}
                        </div>
                        <span className="resize" role="separator" aria-orientation="vertical" aria-label={`Resize ${x.label}`} onPointerDown={(e) => startResize(x.key, e)} />
                      </th>
                    );
                  })}</tr></thead>
                  <tbody>
                    {(data?.rows ?? []).map((r) => (
                      <tr key={r.req_key} className={open?.req_key === r.req_key ? "sel" : ""} tabIndex={0} onClick={() => setOpen(r)}
                        onKeyDown={(e) => { if (e.key === "Enter") setOpen(r); }}>
                        <td className="name" title={requirementLabel(r)}>{requirementLabel(r)}</td>
                        <td><span className={`res ${RESULT[r.result]?.cls ?? ""}`}>{RESULT[r.result]?.dot} {RESULT[r.result]?.label ?? r.result}</span>{r.sub_status ? <div className="muted small">{SUB[r.sub_status] ?? r.sub_status}</div> : null}</td>
                        <td className="name">{docCell(r.best)}</td>
                        <td>{r.best_kind ? display("kind", r.best_kind) : ""}</td>
                        <td>{r.best_stage && r.best_stage !== "n_a" ? display("stage", r.best_stage) : r.best_status ? display("status", r.best_status) : ""}</td>
                        <td>{r.best_date ? String(r.best_date).slice(0, 10) : ""}</td>
                        <td className="why" title={r.best_reason ?? ""}>{r.override_action ? `${r.override_action === "link" ? "Linked" : "Not required"} by ${r.override_by ?? "a person"}` : r.best_reason ?? ""}</td>
                        <td>{r.n_candidates > 1 ? `Other candidates (${r.n_candidates - 1})` : ""}</td>
                      </tr>
                    ))}
                    {data && !data.rows.length ? <tr><td className="empty" colSpan={COLS.length}>No requirements in this scope.</td></tr> : null}
                  </tbody>
                </table>
              </div>
              {data && data.matched > st.pageSize ? (
                <div className="pager">
                  <div className="left"><span>Page {page + 1} of {lastPage + 1}</span></div>
                  <div className="left">
                    <span className="cap">Per page</span>
                    <div className="seg">{[10, 25, 100].map((n) => <button key={n} className={st.pageSize === n ? "on" : ""} onClick={() => upd({ pageSize: n })}>{n}</button>)}</div>
                    <div className="pages">
                      <button className="pg" disabled={!page} onClick={() => setPage(page - 1)} aria-label="Previous page">‹</button>
                      <button className="pg" disabled={page >= lastPage} onClick={() => setPage(page + 1)} aria-label="Next page">›</button>
                    </div>
                  </div>
                </div>
              ) : null}
            </section>
            {open ? <RowPanel r={open} rule={rule} onClose={() => setOpen(null)} onChanged={() => { setOpen(null); load(); }} /> : null}
          </div>
        )}
    </div>
  );
}

type Hit = { file_id: string; name: string; kind: string | null; entities?: string[]; fiscal_year?: number | null; period?: string | null; location?: string | null; location_folder_id?: string | null; other_locations?: number | null };
const LINK_KIND_NAME: Record<string, string> = { "LP-SUB": "Subscription Agreement", "LP-SIDE": "Side Letter", "GP-COMMIT": "Subscription Agreement",
  "AUDITED-FS": "Audited Financial Statements", "K1-SET": "K-1", "PCAP-Q": "Capital Statement" };
function linkHint(r: Req): string {
  return [LINK_KIND_NAME[r.rule_id] ?? "the rule's kind", r.entity_code, r.fiscal_year ? `FY${r.fiscal_year}` : null,
    r.rule_id === "AUDITED-FS" ? "annual" : r.fiscal_quarter ? `Q${r.fiscal_quarter}` : null].filter(Boolean).join(", ");
}

/** Row actions: Link document (a candidate, or a Find search), Not required (with a reason), Clear override. */
function RowPanel({ r, rule, onClose, onChanged }: { r: Req; rule?: Rule; onClose: () => void; onChanged: () => void }) {
  const [cands, setCands] = useState<{ candidates: Cand[]; not_in_scope: number } | null>(null);
  const [note, setNote] = useState("");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setCands(null); setMsg(null); setNote(""); setHits(null);
    api<{ candidates: Cand[]; not_in_scope: number }>(`/api/checklists/candidates?key=${encodeURIComponent(r.req_key)}`).then(setCands).catch((e) => setMsg((e as Error).message));
  }, [r.req_key]);
  const post = async (body: Record<string, unknown>) => {
    setBusy(true); setMsg(null);
    try { await api("/api/checklists/override", { method: "POST", body: JSON.stringify({ req_key: r.req_key, ...body }) }); onChanged(); }
    catch (e) { const b = (e as { body?: { error?: string; reason?: string } }).body; setMsg(`Not saved: ${b?.reason ?? b?.error ?? (e as Error).message}`); }
    setBusy(false);
  };
  const search = async () => {
    if (q.trim().length < 2) return;
    try {
      // CAT-WO-03.1 (Ryan): the WHOLE catalog, any kind / entity / year - a Drive name search as the user. Choosing one
      // links it AND labels it to match this requirement (kind, entity, FY, period), as you.
      const f = await api<{ rows: Hit[] }>("/api/find", { method: "POST", body: JSON.stringify({ search: q.trim(), pageSize: 25 }) });
      setHits(f.rows);
    } catch (e) { setMsg((e as Error).message); }
  };
  return (
    <aside className="panel" aria-label="Requirement">
      <div className="panel-head">
        <div className="grow">
          <div className="kicker">{rule?.title ?? r.rule_id}</div>
          <div className="panel-title" title={requirementLabel(r)}>{requirementLabel(r)}</div>
        </div>
        <button className="btn sm outline" onClick={onClose} aria-label="Close">×</button>
      </div>
      <div className="panel-body req-panel">
      <p><span className={`res ${RESULT[r.result]?.cls ?? ""}`}>{RESULT[r.result]?.dot} {RESULT[r.result]?.label}</span> {r.sub_status ? <span className="muted small">· {SUB[r.sub_status] ?? r.sub_status}</span> : null}</p>
      <p className="small"><b>Best document:</b> {docCell(r.best)}{r.best_reason ? <><br /><span className="muted">{r.best_reason}</span></> : null}</p>
      {r.override_action ? <p className="small"><b>Override:</b> {r.override_action === "link" ? "linked" : "not required"} by {r.override_by} on {String(r.override_at ?? "").slice(0, 10)}{r.override_note ? ` - ${r.override_note}` : ""}</p> : null}
      <h3 className="cap">Candidates {cands ? `(${cands.candidates.length})` : ""}</h3>
      {cands?.candidates.length ? (
        <ul className="cands">
          {cands.candidates.map((c, i) => (
            <li key={i}>
              {docCell(c.doc)}{c.location ? <> <LocationCell location={c.location} folderId={c.location_folder_id} other={c.other_locations} /></> : null} <span className="muted small">· {display("kind", c.kind)}{c.stage && c.stage !== "n_a" ? ` · ${display("stage", c.stage)}` : ""}{c.status ? ` · ${display("status", c.status)}` : ""}{c.date ? ` · ${c.date}` : ""}{c.partner_conf ? ` · partner match ${c.partner_conf}` : ""}{c.satisfying ? " · qualifies" : ""}</span>
              {c.doc && c.doc.access === "ok" ? <button className="btn small" disabled={busy} onClick={() => post({ action: "link", file_id: (c.doc as { file_id: string }).file_id })}>This is the one</button> : null}
            </li>
          ))}
        </ul>
      ) : <p className="muted small">{cands ? "No candidates found." : "Loading…"}</p>}
      {cands?.not_in_scope ? <p className="muted small">{cands.not_in_scope} candidate(s) left the catalog&apos;s scope and are not shown.</p> : null}
      <h3 className="cap">Link another document</h3>
      <div className="row-inline">
        <input className="input" value={q} maxLength={100} onChange={(e) => setQ(e.target.value)} placeholder="Find anywhere in the catalog by name" onKeyDown={(e) => { if (e.key === "Enter") search(); }} />
        <button className="btn" onClick={search}>Find</button>
      </div>
      {hits ? (hits.length ? <ul className="cands">{hits.map((h) => (
        <li key={h.file_id}>{shownName(h.name, h.file_id)} <span className="muted small">· {h.kind ? display("kind", h.kind) : "no kind"} · {h.entities?.length ? h.entities.join(", ") : "no entity"} · {h.fiscal_year ? `FY${h.fiscal_year}` : "no FY"}{h.period ? ` ${h.period}` : ""}</span>
          {h.location ? <> <LocationCell location={h.location} folderId={h.location_folder_id} other={h.other_locations} /></> : null}
          <button className="btn small" disabled={busy} onClick={() => post({ action: "link", file_id: h.file_id })}>This is the one</button></li>))}</ul>
        : <p className="muted small">Nothing found in the catalog by that name.</p>) : null}
      <p className="muted small">Choosing a document links it here and sets its labels to match: {linkHint(r)}.</p>
      <h3 className="cap">Not required</h3>
      <textarea className="input" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason (required). Use partner codes, never names." />
      <div className="actions">
        <button className="btn" disabled={busy || !note.trim()} onClick={() => post({ action: "not_required", note })}>Mark not required</button>
        {r.override_action ? <button className="btn" disabled={busy} onClick={() => post({ action: "clear" })}>Clear override</button> : null}
      </div>
      {msg ? <p className="status error" role="status">{msg}</p> : null}
      </div>
    </aside>
  );
}

/** Gaps tab: entity x period for a fund-level checklist. A cell is green when all met, red when anything is missing. */
function Gaps({ rule, entity, onCell }: { rule: string; entity: string | null; onCell: (e: string, fy: number | null, q: number | null) => void }) {
  const [cells, setCells] = useState<{ entity_code: string; fiscal_year: number | null; fiscal_quarter: number | null; result: string; n: number }[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setCells(null);
    api<{ cells: typeof cells }>(`/api/checklists/gaps?rule=${encodeURIComponent(rule)}${entity ? `&entity=${encodeURIComponent(entity)}` : ""}`).then((r) => setCells(r.cells)).catch((e) => setErr((e as Error).message));
  }, [rule, entity]);
  if (err) return <div className="status error">Could not load the gaps: {err}</div>;
  if (!cells) return <p className="muted">Loading…</p>;
  const pk = (c: { fiscal_year: number | null; fiscal_quarter: number | null }) => `${c.fiscal_year ?? ""}|${c.fiscal_quarter ?? ""}`;
  const periods = [...new Map(cells.map((c) => [pk(c), c])).values()].sort((a, b) => (a.fiscal_year ?? 0) - (b.fiscal_year ?? 0) || (a.fiscal_quarter ?? 0) - (b.fiscal_quarter ?? 0));
  const ents = [...new Set(cells.map((c) => c.entity_code))].sort();
  const at = (e: string, p: string) => cells.filter((c) => c.entity_code === e && pk(c) === p);
  const tone = (cs: typeof cells) => {
    const n = (r: string) => cs.filter((c) => c.result === r).reduce((a, c) => a + c.n, 0);
    const tot = cs.reduce((a, c) => a + c.n, 0);
    if (!tot) return { cls: "gap-empty", text: "" };
    if (n("no_roster") + n("applicability_not_set") === tot) return { cls: "gap-info", text: n("no_roster") ? "no roster" : "not set" };
    if (n("missing")) return { cls: "gap-missing", text: `${n("met")}/${tot} met` };
    if (n("on_file")) return { cls: "gap-onfile", text: `${n("met")}/${tot} met` };
    return { cls: "gap-met", text: `${n("met") + n("not_required")}/${tot}` };
  };
  return (
    <section className="card list-card" aria-label="Gaps">
      <div className="grid-wrap">
        <table className="grid gaps">
          <thead><tr><th>Entity</th>{periods.map((p) => <th key={pk(p)}>{period(p)}</th>)}</tr></thead>
          <tbody>{ents.map((e) => (
            <tr key={e}><td className="name">{e}</td>
              {periods.map((p) => { const t = tone(at(e, pk(p))); return (
                <td key={pk(p)} className={`gap ${t.cls}`}>{t.text ? <button className="link" onClick={() => onCell(e, p.fiscal_year, p.fiscal_quarter)}>{t.text}</button> : null}</td>
              ); })}
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p className="muted small">Green: all met (or not required) · orange: on file, not final · red: something missing · grey: no roster in Datum / applicability not set. Click a cell to open its rows.</p>
    </section>
  );
}
