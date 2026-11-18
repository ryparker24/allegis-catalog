"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, show, type NotShown, type Row } from "./client";
import { SidePanel } from "./SidePanel";
import { PageHeader } from "./AppShell";
import { PickList, Pop, RangeInputs } from "./FindClient";
import { shownName } from "./bus";
import { Icon } from "./icons";
import { VOCAB, display, type VocabList } from "@/lib/vocab";

type Counts = { stage_unknown?: number; low_confidence_executed?: number; no_kind?: number; open_total?: number; reviewed_today?: number; reviewed_total?: number };
export type Resp = { counts: Counts; page: number; pageSize?: number; matched?: number; nextPage: number | null; pageRows: number; rows: Row[]; notShown: NotShown; canWrite: boolean };

const REASON: Record<string, string> = { stage_unknown: "Stage unknown", low_confidence_executed: "Fully executed (low confidence)", no_kind: "No kind" };
const SIGNAL: Record<string, string> = {
  sig_block: "signature block found", sig_page_image: "signature page is an image", scanned: "scanned", blank_line: "blank signature line",
  docusign: "DocuSign", digital_sig: "digital signature", exec_version: "'executed' in name", conformed: "conformed (/s/)", draft_mark: "draft mark",
  certificate: "e-sign certificate", esign_other: "other e-signature",
};
const STAGES = ["draft", "final_unexecuted", "partially_executed", "fully_executed", "n_a"] as const;
const SKIP_KEY = "catalog.review.skipped";
const SKIP_MAX = 400; // the server reads at most 500; keeps the query string well under URL limits
const PAGE_SIZES = [10, 25, 100];

// ------------------------------------------------------------------ list state (CAT-WO-02 item 2: Datum lists on the queue)
type Range = { from?: string; to?: string };
export type ReviewListState = {
  lanes: string[];
  filters: { kind?: string[]; entity?: string[]; stage?: string[]; fy_range?: Range };
  sort: { col: string; dir: "asc" | "desc" };
  pageSize: number;
  widths: Record<string, number>;
};
export const DEFAULT_LIST: ReviewListState = { lanes: [], filters: {}, sort: { col: "queue", dir: "asc" }, pageSize: 25, widths: {} };
type Col = { key: string; label: string; width: number; sort?: string; filter?: "lane" | "kind" | "entity" | "stage" | "fy" };
const COLS: Col[] = [
  { key: "name", label: "File", width: 300 },
  { key: "why", label: "Why", width: 300, sort: "queue", filter: "lane" },
  { key: "stage", label: "Signing stage", width: 150, sort: "stage", filter: "stage" },
  { key: "kind", label: "Kind", width: 160, sort: "kind", filter: "kind" },
  { key: "entities", label: "Entity", width: 120, sort: "entities", filter: "entity" },
  { key: "fiscal_year", label: "Fiscal year", width: 100, sort: "fiscal_year", filter: "fy" },
  { key: "confidence", label: "Confidence", width: 110, sort: "confidence" },
];
type Facet = { value: string; n: number; label?: string };

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
const activeFilters = (l: ReviewListState) =>
  l.lanes.length + (l.filters.kind?.length ? 1 : 0) + (l.filters.entity?.length ? 1 : 0) + (l.filters.stage?.length ? 1 : 0) + (l.filters.fy_range?.from || l.filters.fy_range?.to ? 1 : 0);

export function ReviewClient() {
  const [data, setData] = useState<Resp | null>(null);
  const [cur, setCur] = useState<Row | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [form, setForm] = useState({ status: "confirmed", stage: "", executed_date: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [list, setList] = useState<ReviewListState>(DEFAULT_LIST);
  const [ready, setReady] = useState(false);
  const [facets, setFacets] = useState<Record<string, Facet[]> | null>(null);
  // A failed load must show on the page itself (CAT-WO-01.1): the side panel is closed when nothing is selected.
  const onLoadError = useCallback((e: unknown) => setLoadError(loadErrorText(e)), []);
  const listRef = useRef(list);
  listRef.current = list;

  const load = useCallback(async (skip: string[], page = 0) => {
    const l = listRef.current;
    const spec = { filters: l.filters, sort: l.sort, pageSize: l.pageSize };
    const r = await api<Resp>(`/api/review?page=${page}&skip=${encodeURIComponent(skip.join(","))}&spec=${encodeURIComponent(JSON.stringify(spec))}&lane=${encodeURIComponent(l.lanes.join(","))}`);
    setData(r);
    setLoadError(null);
    setCur(r.rows[0] ?? null);
  }, []);
  // start: the last list state for this user (item 2), then the first page
  useEffect(() => {
    api<Record<string, Facet[]>>("/api/facets").then(setFacets).catch(() => {});
    (async () => {
      try {
        const p = await api<{ value: Partial<ReviewListState> & { lanes?: string[] } | null }>("/api/prefs?key=review");
        if (p.value) setList({ ...DEFAULT_LIST, ...p.value, filters: (p.value.filters as ReviewListState["filters"]) ?? {}, lanes: p.value.lanes ?? [], widths: p.value.widths ?? {} });
      } catch { /* defaults */ }
      setReady(true);
    })();
  }, []);
  useEffect(() => {
    if (!ready) return;
    const s = loadSkipped(); setSkipped(s); load(s).catch(onLoadError);
    const t = setTimeout(() => {
      api("/api/prefs", { method: "PUT", body: JSON.stringify({ key: "review", value: { filters: list.filters, sort: list.sort, pageSize: list.pageSize, lanes: list.lanes, widths: list.widths } }) }).catch(() => {});
    }, 800);
    return () => clearTimeout(t);
  }, [ready, list, load, onLoadError]);
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
    const s = [...skipped, cur.file_id].slice(-SKIP_MAX);
    setSkipped(s);
    try { sessionStorage.setItem(SKIP_KEY, JSON.stringify(s)); } catch { /* storage unavailable: skip for this view only */ }
    const n = next(data.rows, cur.file_id);
    if (n) setCur(n); else load(s, data.page).catch(onLoadError);
  };
  const clearSkipped = () => {
    setSkipped([]);
    try { sessionStorage.removeItem(SKIP_KEY); } catch { /* ignore */ }
    load([], 0).catch(onLoadError);
  };
  const confirm = async () => {
    if (!cur) return;
    setBusy(true); setMsg(null);
    try {
      await api("/api/review/confirm", { method: "POST", body: JSON.stringify({ file_id: cur.file_id, ...form, stage: form.stage || null, executed_date: form.executed_date || null, note: form.note || null }) });
      setMsg("Saved to Drive.");
    } catch (e) {
      const b = (e as { body?: { error?: string; reason?: string; drive_status?: number } }).body;
      setMsg(`Not saved: ${b?.reason ?? b?.error ?? (e as Error).message}${b?.drive_status ? ` (Drive ${b.drive_status})` : ""}`);
      setBusy(false);
      return;
    }
    await load(skipped, data?.page ?? 0).catch(onLoadError); // the save succeeded; a reload failure is a load error, not "Not saved"
    setBusy(false);
  };

  return (
    <ReviewView data={data} cur={cur} skipped={skipped} form={form} busy={busy} msg={msg} loadError={loadError}
      setCur={setCur} setForm={setForm} onConfirm={confirm} onSkip={skip}
      onNextPage={(p) => load(skipped, p).catch(onLoadError)}
      list={list} setList={(l) => setList(l)} facets={facets} onClearSkipped={clearSkipped} />
  );
}

/** Error codes only (the API returns codes such as forbidden / bad_origin / access_google_mismatch, never file data). */
export function loadErrorText(e: unknown): string {
  const err = e as { message?: string; status?: number; body?: { error?: string; reason?: string } };
  const code = err.body?.error ?? err.message ?? "unknown_error";
  const reason = err.body?.reason && err.body.reason !== code ? ` (${err.body.reason})` : "";
  return `${code}${reason}${err.status ? `, HTTP ${err.status}` : ""}`;
}

type Form = { status: string; stage: string; executed_date: string; note: string };
export interface ReviewViewProps {
  data: Resp | null; cur: Row | null; skipped: string[]; form: Form; busy: boolean; msg: string | null; loadError?: string | null;
  setCur: (r: Row | null) => void; setForm: (f: Form) => void; onConfirm: () => void; onSkip: () => void; onNextPage: (page: number) => void;
  // CAT-WO-02 (optional, so the CAT-WO-01.1 render tests keep their props)
  list?: ReviewListState; setList?: (l: ReviewListState) => void; facets?: Record<string, Facet[]> | null; onClearSkipped?: () => void;
}

/** Dashboard-style counter card (Datum): caption, big number, one-line explanation. A lane card filters the list. */
function Kpi({ cap, n, exp, on, onClick }: { cap: string; n: number; exp: string; on?: boolean; onClick?: () => void }) {
  const body = (<><span className="k-cap">{cap}</span><span className="k-num">{n.toLocaleString()}</span><span className="k-exp">{exp}</span></>);
  return onClick
    ? <button type="button" className={`ctr kpi link-card${on ? " on" : ""}`} onClick={onClick} aria-pressed={!!on}>{body}</button>
    : <div className="ctr kpi">{body}</div>;
}

/** Presentational part of the Review page (no fetching), so it can be rendered in tests. */
export function ReviewView({ data, cur, skipped, form, busy, msg, loadError, setCur, setForm, onConfirm, onSkip, onNextPage, list = DEFAULT_LIST, setList, facets, onClearSkipped }: ReviewViewProps) {
  const c = data?.counts ?? {};
  const [pop, setPop] = useState<string | null>(null);
  const [popAt, setPopAt] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const closePop = useCallback(() => setPop(null), []);
  const upd = (l: Partial<ReviewListState>) => setList?.({ ...list, ...l });
  const toggleLane = (lane: string) => upd({ lanes: list.lanes.includes(lane) ? list.lanes.filter((x) => x !== lane) : [...list.lanes, lane] });
  const width = (k: string) => list.widths[k] ?? COLS.find((x) => x.key === k)!.width;
  const startResize = (k: string, e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation();
    const x0 = e.clientX, w0 = width(k);
    const move = (ev: PointerEvent) => upd({ widths: { ...list.widths, [k]: Math.max(60, Math.min(900, Math.round(w0 + ev.clientX - x0))) } });
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const sortBy = (col: string) => upd({ sort: { col, dir: list.sort.col === col && list.sort.dir === "asc" ? "desc" : "asc" } });
  const label = (v: VocabList | undefined) => (o: Facet) => o.label ?? (v && o.value !== "(none)" ? display(v, o.value) : o.value);
  const filterBody = (f: Col["filter"]) => {
    if (f === "lane") return (
      <div className="opts">{Object.entries(REASON).map(([k, l]) => (
        <label key={k} className="opt"><input type="checkbox" checked={list.lanes.includes(k)} onChange={() => toggleLane(k)} /> {l}</label>
      ))}</div>
    );
    if (f === "fy") return <RangeInputs type="year" value={list.filters.fy_range ?? {}} onChange={(r) => { upd({ filters: { ...list.filters, fy_range: r } }); setPop(null); }} />;
    const key = f === "kind" ? "kind" : f === "entity" ? "entity" : "stage";
    const v = ((list.filters as Record<string, string[] | undefined>)[key]) ?? [];
    return <PickList options={facets?.[key] ?? []} value={v} onChange={(x) => upd({ filters: { ...list.filters, [key]: x } })} label={label(key === "entity" ? undefined : (key as VocabList))} />;
  };
  const isOn = (f: Col["filter"]) => f === "lane" ? list.lanes.length > 0 : f === "fy" ? !!(list.filters.fy_range?.from || list.filters.fy_range?.to)
    : !!((list.filters as Record<string, string[] | undefined>)[f === "kind" ? "kind" : f === "entity" ? "entity" : "stage"]?.length);
  const nFilters = activeFilters(list);
  const rows = (data?.rows ?? []).filter((r) => !skipped.includes(r.file_id));
  const pageSize = data?.pageSize ?? list.pageSize;
  const from = data && data.matched ? data.page * pageSize + 1 : 0;
  const to = data ? data.page * pageSize + data.pageRows : 0;
  const cell = (r: Row, k: string) =>
    k === "name" ? shownName(r.name, r.file_id) : k === "why" ? why(r) : k === "confidence" ? (r.confidence ?? "") : show(k, (r as unknown as Record<string, unknown>)[k]);

  return (
    <div className="review">
      <PageHeader
        title="Review queue"
        info={<>Files the catalog wants a person to check, most uncertain first: signing stage unknown, then fully executed at low confidence, then no kind. Each page is checked live against Drive as you; Confirm writes the Execution and Catalog Review labels on the file.</>}
        actions={setList ? <>
          <div className="pop-wrap">
            <button className="btn" aria-label="More actions" aria-expanded={pop === "more"} onClick={() => setPop(pop === "more" ? null : "more")}><Icon name="more" /></button>
            <Pop open={pop === "more"} onClose={closePop} className="menu">
              <button disabled={!skipped.length} onClick={() => { setPop(null); onClearSkipped?.(); }}>Bring back skipped files ({skipped.length})</button>
              <button onClick={() => { setPop(null); setList({ ...DEFAULT_LIST }); }}>Reset filters, sort and columns</button>
            </Pop>
          </div>
        </> : null}
      />
      <div className="counters">
        <Kpi cap="Open" n={c.open_total ?? 0} exp="Files waiting for a person, across all lanes." />
        <Kpi cap="Stage unknown" n={c.stage_unknown ?? 0} exp="Signed documents whose signing stage couldn't be read." on={list.lanes.includes("stage_unknown")} onClick={setList ? () => toggleLane("stage_unknown") : undefined} />
        <Kpi cap="Executed, low confidence" n={c.low_confidence_executed ?? 0} exp="Marked fully executed, but the scan isn't sure." on={list.lanes.includes("low_confidence_executed")} onClick={setList ? () => toggleLane("low_confidence_executed") : undefined} />
        <Kpi cap="No kind" n={c.no_kind ?? 0} exp="The catalog couldn't tell what the document is." on={list.lanes.includes("no_kind")} onClick={setList ? () => toggleLane("no_kind") : undefined} />
        <Kpi cap="Reviewed today" n={c.reviewed_today ?? 0} exp="Confirmed or marked wrong since midnight." />
        <Kpi cap="Skipped" n={skipped.length} exp="Set aside in this browser session; nothing written." />
      </div>
      {loadError ? (
        <div className="status error" role="alert">
          Could not load the review queue: {loadError}. Reload the page to try again; if it keeps failing, sign in again.
        </div>
      ) : null}
      <div className={cur ? "find with-panel" : "find"}>
        <section className="card list-card" aria-label="Review queue">
          <div className="filterbar">
            <span className="summary">{nFilters ? `${nFilters} filter${nFilters > 1 ? "s" : ""}` : "No filters"}</span>
            {nFilters && setList ? <button className="link small" onClick={() => upd({ lanes: [], filters: {} })}>Clear all</button> : null}
            <div className="tools">
              {data?.notShown.total ? (
                <span className="small warn">
                  {data.notShown.noAccess ? `${data.notShown.noAccess} not shown (no access)` : ""}{data.notShown.noAccess && data.notShown.checkFailed ? " · " : ""}
                  {data.notShown.checkFailed ? `${data.notShown.checkFailed} not shown (Drive check failed - retry)` : ""}
                </span>
              ) : null}
            </div>
          </div>
          {data ? (
            <div className="pager">
              <div className="left"><span>{data.matched == null ? `${data.pageRows} on this page` : data.pageRows ? `${from.toLocaleString()}–${to.toLocaleString()} of ${data.matched.toLocaleString()} files` : `None shown on this page · ${data.matched.toLocaleString()} files`}</span></div>
              <div className="left">
                {setList ? <><span className="cap">Per page</span>
                  <div className="seg">{PAGE_SIZES.map((n) => <button key={n} className={list.pageSize === n ? "on" : ""} onClick={() => upd({ pageSize: n })}>{n}</button>)}</div></> : null}
                <div className="pages">
                  <button className="pg" disabled={!data.page} onClick={() => onNextPage(Math.max(0, data.page - 1))} aria-label="Previous page">‹</button>
                  <button className="pg on" aria-current="page">{(data.page + 1).toLocaleString()}</button>
                  <button className="pg" disabled={data.nextPage == null} onClick={() => data.nextPage != null && onNextPage(data.nextPage)} aria-label="Next page">›</button>
                </div>
              </div>
            </div>
          ) : null}
          <div className="grid-wrap">
            <table className="grid queue" style={{ width: COLS.reduce((n, x) => n + width(x.key), 0) }}>
              <colgroup>{COLS.map((x) => <col key={x.key} style={{ width: width(x.key) }} />)}</colgroup>
              <thead><tr>{COLS.map((x) => {
                const on = list.sort.col === x.sort;
                const fid = `rf-${x.key}`;
                return (
                  <th key={x.key} aria-sort={on ? (list.sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                    <div className="th">
                      <span className={`lbl${x.sort && setList ? " sortable" : ""}`} onClick={() => x.sort && setList && sortBy(x.sort)}>{x.label}</span>
                      {x.sort && setList ? <span className={`sort${on ? " on" : ""}`} aria-hidden="true">{on ? (list.sort.dir === "asc" ? "↑" : "↓") : "↕"}</span> : null}
                      {x.filter && setList ? (
                        <span className="pop-wrap" style={{ marginLeft: "auto" }}>
                          <button className={`fbtn${isOn(x.filter) ? " on" : ""}`} aria-label={`Filter ${x.label}`} aria-expanded={pop === fid}
                            onClick={(e) => { e.stopPropagation(); const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); setPopAt({ top: r.bottom + 6, left: Math.max(8, Math.min(r.right - 320, window.innerWidth - 336)) }); setPop(pop === fid ? null : fid); }}>
                            <Icon name="filter" />
                          </button>
                          <Pop open={pop === fid} onClose={closePop} className="popover fixed" style={popAt}>{filterBody(x.filter)}</Pop>
                        </span>
                      ) : null}
                    </div>
                    {setList ? <span className="resize" role="separator" aria-orientation="vertical" aria-label={`Resize ${x.label}`} onPointerDown={(e) => startResize(x.key, e)} /> : null}
                  </th>
                );
              })}</tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.file_id} onClick={() => setCur(r)} className={cur?.file_id === r.file_id ? "sel" : ""}>
                    {COLS.map((x) => (
                      <td key={x.key} className={x.key === "why" ? "why" : x.key === "name" ? "name" : undefined} title={x.key === "why" || x.key === "name" ? String(cell(r, x.key)) : undefined}>
                        {cell(r, x.key)}
                        {x.key === "stage" && r.changed.includes("stage") ? <span className="chg">changed in Drive</span> : null}
                      </td>
                    ))}
                  </tr>
                ))}
                {data && !rows.length ? (
                  <tr><td className="empty" colSpan={COLS.length}>
                    Nothing shown on this page.{data.nextPage != null ? <> <button className="link" onClick={() => onNextPage(data.nextPage!)}>Next page</button></> : null}
                  </td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
        {cur ? (
          <SidePanel row={cur} onClose={() => setCur(null)}>
            <form className="review-form" onSubmit={(e) => { e.preventDefault(); onConfirm(); }}>
              <p className="why small"><b>Why:</b> {why(cur)}</p>
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
                <button className="btn" type="button" onClick={onSkip} disabled={busy}>Skip</button>
              </div>
              {msg ? <p className="status">{msg}</p> : null}
            </form>
          </SidePanel>
        ) : null}
      </div>
    </div>
  );
}
