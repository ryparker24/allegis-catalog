"use client";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, show, type NotShown, type Row } from "./client";
import { SidePanel } from "./SidePanel";
import { PageHeader } from "./AppShell";
import { ContainsInput, pageList, PickList, Pop, RangeInputs } from "./FindClient";
import { LocationCell } from "./Location";
import { shownName } from "./bus";
import { Icon } from "./icons";
import { EditForm, editInfo } from "./EditForm";
import { SubjectForm } from "./SubjectForm";
import { LinkVersionsLane } from "./Versions";
import { VOCAB, display, type VocabList } from "@/lib/vocab";

type Counts = { content_disagrees?: number; portal_kind_conflict?: number; link_versions?: number; match_subject?: number; stage_unknown?: number; status_unknown?: number; low_confidence_executed?: number; no_kind?: number; open_total?: number; reviewed_today?: number; reviewed_total?: number };
export type Resp = { counts: Counts; page: number; pageSize?: number; matched?: number; nextPage: number | null; pageRows: number; rows: Row[]; notShown: NotShown; canWrite: boolean };

// lane order as shown (R-022: "Status unknown" right after signing stage unknown)
const REASON: Record<string, string> = { stage_unknown: "Stage unknown", status_unknown: "Status unknown", low_confidence_executed: "Fully executed (low confidence)", no_kind: "No kind", match_subject: "Match subject", content_disagrees: "Content disagrees" };
// CAT-WO-06: why a content candidate is in Match subject (codes from the reader; never page text)
const SUBJECT_REASON: Record<string, string> = {
  NO_ROSTER_MATCH: "no roster partner found on the page", NOT_IN_FUND: "the name belongs to a partner of another fund",
  MULTIPLE: "several roster partners on the page", CONFLICT_PERSON: "the page names a different partner than the Subject a person set",
  CONFLICT_PORTAL: "the page names a different partner than the portal posting", MEDIUM: "read from the page, not certain",
};
const DISAGREE: Record<string, string> = { fiscal_year: "fiscal year", period: "period", entity: "entity" };
const DOC_STATUSES = ["draft", "in_review", "final", "issued", "superseded"] as const;
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
  filters: { kind?: string[]; entity?: string[]; stage?: string[]; fy_range?: Range; location?: string };
  sort: { col: string; dir: "asc" | "desc" };
  pageSize: number;
  widths: Record<string, number>;
};
export const DEFAULT_LIST: ReviewListState = { lanes: [], filters: {}, sort: { col: "queue", dir: "asc" }, pageSize: 25, widths: {} };
type Col = { key: string; label: string; width: number; sort?: string; filter?: "lane" | "kind" | "entity" | "stage" | "fy" | "location" };
const COLS: Col[] = [
  { key: "name", label: "File", width: 300 },
  { key: "why", label: "Why", width: 300, sort: "queue", filter: "lane" },
  { key: "stage", label: "Signing stage", width: 150, sort: "stage", filter: "stage" },
  { key: "status", label: "Status", width: 120, sort: "status" },
  { key: "kind", label: "Kind", width: 160, sort: "kind", filter: "kind" },
  { key: "entities", label: "Entity", width: 120, sort: "entities", filter: "entity" },
  { key: "fiscal_year", label: "Fiscal year", width: 100, sort: "fiscal_year", filter: "fy" },
  { key: "confidence", label: "Confidence", width: 110, sort: "confidence" },
  { key: "location", label: "Location", width: 260, sort: "location", filter: "location" },   // CAT-WO-03.1
];
type Facet = { value: string; n: number; label?: string };

function why(r: Row): string {
  const parts = [REASON[r.queue_reason ?? ""] ?? r.queue_reason ?? ""];
  if (r.confidence) parts.push(`confidence ${r.confidence}`);
  if (r.stage_suggested && r.stage_suggested !== "unknown") parts.push(`scan suggests ${show("stage", r.stage_suggested)}`);
  const sig = (r.signals ?? []).map((s) => SIGNAL[s] ?? s);
  if (sig.length) parts.push(sig.join(", "));
  else if (r.queue_reason === "match_subject") {
    parts.push(`${r.subject_candidates?.length ?? 0} possible roster partner(s); pick one, several or none`);
    if (r.subject_reasons?.length) parts.push(r.subject_reasons.map((x) => SUBJECT_REASON[x] ?? x).join("; "));
  }
  else if (r.queue_reason === "content_disagrees") parts.push(`page 1 shows a different ${(r.content_disagrees ?? []).map((x) => DISAGREE[x] ?? x).join(", ")}; check it and confirm or correct (nothing was overwritten)`);
  else if (r.queue_reason !== "no_kind" && r.queue_reason !== "status_unknown") parts.push("no scan signals");
  return parts.join(" · ");
}
function loadSkipped(): string[] {
  try { return JSON.parse(sessionStorage.getItem(SKIP_KEY) ?? "[]"); } catch { return []; }
}
const activeFilters = (l: ReviewListState) =>
  l.lanes.length + (l.filters.kind?.length ? 1 : 0) + (l.filters.entity?.length ? 1 : 0) + (l.filters.stage?.length ? 1 : 0) + (l.filters.fy_range?.from || l.filters.fy_range?.to ? 1 : 0) + (l.filters.location ? 1 : 0);

export function ReviewClient() {
  const [data, setData] = useState<Resp | null>(null);
  const [cur, setCur] = useState<Row | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [form, setForm] = useState<Form>({ status: "confirmed", stage: "", executed_date: "", note: "", doc_status: "" });
  const [statusPublished, setStatusPublished] = useState(false);
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

  const reqId = useRef(0);          // only the newest load may update the page (coder review: overlapping loads)
  const visited = useRef<number[]>([]); // pages actually shown, so "Previous" goes back even when the server walked forward
  const load = useCallback(async (skip: string[], page = 0, opts: { back?: boolean } = {}) => {
    const id = ++reqId.current;
    const l = listRef.current;
    const spec = { filters: l.filters, sort: l.sort, pageSize: l.pageSize };
    const r = await api<Resp>(`/api/review?page=${page}&skip=${encodeURIComponent(skip.join(","))}&spec=${encodeURIComponent(JSON.stringify(spec))}&lane=${encodeURIComponent(l.lanes.join(","))}`);
    if (id !== reqId.current) return;  // a newer request was made meanwhile: drop this (stale) response
    if (opts.back) visited.current = visited.current.filter((p) => p < r.page);
    if (!visited.current.includes(r.page)) visited.current = [...visited.current.filter((p) => p < r.page), r.page];
    setData(r);
    setLoadError(null);
    setCur(r.rows[0] ?? null);
  }, []);
  const prevPage = (cur: number) => visited.current.filter((p) => p < cur).pop() ?? Math.max(0, cur - 1);
  // start: the last list state for this user (item 2), then the first page
  useEffect(() => {
    api<Record<string, Facet[]>>("/api/facets").then(setFacets).catch(() => {});
    editInfo().then((i) => setStatusPublished(!!i.fields.find((f) => f.key === "status")?.published)).catch(() => {});
    (async () => {
      try {
        const p = await api<{ value: Partial<ReviewListState> & { lanes?: string[] } | null }>("/api/prefs?key=review");
        if (p.value) setList({ ...DEFAULT_LIST, ...p.value, filters: (p.value.filters as ReviewListState["filters"]) ?? {}, lanes: p.value.lanes ?? [], widths: p.value.widths ?? {} });
      } catch { /* defaults */ }
      setReady(true);
    })();
  }, []);
  // reload only when what the SERVER uses changes - not on a column-width drag (coder review: a drag reloaded the queue)
  const loadKey = JSON.stringify({ l: list.lanes, f: list.filters, s: list.sort, p: list.pageSize });
  useEffect(() => {
    if (!ready) return;
    visited.current = [];
    const s = loadSkipped(); setSkipped(s);
    load(s).catch((e) => {
      // a saved state the server no longer accepts must not break every visit: fall back to the defaults once
      if ((e as { body?: { error?: string } }).body?.error === "bad_spec" && loadKey !== JSON.stringify({ l: [], f: {}, s: DEFAULT_LIST.sort, p: DEFAULT_LIST.pageSize })) setList(DEFAULT_LIST);
      else onLoadError(e);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, loadKey, load, onLoadError]);
  // remember the list state (incl. widths) for this user - only after a change, not on every visit
  const saved = useRef<string | null>(null);
  useEffect(() => {
    if (!ready) return;
    const v = JSON.stringify({ filters: list.filters, sort: list.sort, pageSize: list.pageSize, lanes: list.lanes, widths: list.widths });
    if (saved.current === null) { saved.current = v; return; }
    if (saved.current === v) return;
    const t = setTimeout(() => { saved.current = v; api("/api/prefs", { method: "PUT", body: JSON.stringify({ key: "review", value: JSON.parse(v) }) }).catch(() => {}); }, 800);
    return () => clearTimeout(t);
  }, [ready, list]);
  useEffect(() => {
    if (!cur) return;
    const stage = cur.stage && cur.stage !== "unknown" ? cur.stage : cur.stage_suggested && cur.stage_suggested !== "unknown" ? cur.stage_suggested : "";
    setForm({ status: "confirmed", stage, executed_date: cur.executed_date ?? "", note: "", doc_status: cur.status ?? "" });
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
      // R-022: Stage for executable kinds, Status for the rest - the write carries one or the other, never both
      const exec = isExecutable(cur);
      await api("/api/review/confirm", { method: "POST", body: JSON.stringify({
        file_id: cur.file_id, status: form.status, note: form.note || null,
        stage: exec ? form.stage || null : null, executed_date: exec ? form.executed_date || null : null,
        doc_status: !exec && statusPublished && form.doc_status && form.doc_status !== (cur.status ?? "") ? form.doc_status : null,
      }) });
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
      onNextPage={(p) => load(skipped, p, { back: !!data && p < data.page }).catch(onLoadError)}
      onPrevPage={() => data && load(skipped, prevPage(data.page), { back: true }).catch(onLoadError)}
      list={list} setList={setList} facets={facets} onClearSkipped={clearSkipped} statusPublished={statusPublished}
      subjectSlot={cur ? <SubjectForm key={`s${cur.file_id}`} row={cur} lane onSaved={() => { load(skipped, data?.page ?? 0).catch(onLoadError); }} /> : null}
      editSlot={cur ? <EditForm key={cur.file_id} row={cur} source="review_edit" onSaved={() => { load(skipped, data?.page ?? 0).catch(onLoadError); }} /> : null} />
  );
}

/** Error codes only (the API returns codes such as forbidden / bad_origin / access_google_mismatch, never file data). */
export function loadErrorText(e: unknown): string {
  const err = e as { message?: string; status?: number; body?: { error?: string; reason?: string } };
  const code = err.body?.error ?? err.message ?? "unknown_error";
  const reason = err.body?.reason && err.body.reason !== code ? ` (${err.body.reason})` : "";
  return `${code}${reason}${err.status ? `, HTTP ${err.status}` : ""}`;
}

type Form = { status: string; stage: string; executed_date: string; note: string; doc_status?: string };
/** Stage applies to executable kinds; everything else gets a Status (R-022). The lane decides first (the view's
 *  status_unknown also covers requires_execution = NULL); otherwise not known as non-executable: Stage, as before. */
export const isExecutable = (r: Row) =>
  r.queue_reason === "stage_unknown" || (r.queue_reason !== "status_unknown" && r.requires_execution !== false);
export interface ReviewViewProps {
  data: Resp | null; cur: Row | null; skipped: string[]; form: Form; busy: boolean; msg: string | null; loadError?: string | null;
  setCur: (r: Row | null) => void; setForm: (f: Form) => void; onConfirm: () => void; onSkip: () => void; onNextPage: (page: number) => void;
  // CAT-WO-02 (optional, so the CAT-WO-01.1 render tests keep their props)
  list?: ReviewListState; setList?: (u: ReviewListState | ((l: ReviewListState) => ReviewListState)) => void;
  facets?: Record<string, Facet[]> | null; onClearSkipped?: () => void; onPrevPage?: () => void;
  statusPublished?: boolean; editSlot?: ReactNode; subjectSlot?: ReactNode;
}

/** Dashboard-style counter card (Datum): caption, big number, one-line explanation. A lane card filters the list. */
function Kpi({ cap, n, exp, on, onClick }: { cap: string; n: number; exp: string; on?: boolean; onClick?: () => void }) {
  const body = (<><span className="k-cap">{cap}</span><span className="k-num">{n.toLocaleString()}</span><span className="k-exp">{exp}</span></>);
  return onClick
    ? <button type="button" className={`ctr kpi link-card${on ? " on" : ""}`} onClick={onClick} aria-pressed={!!on}>{body}</button>
    : <div className="ctr kpi">{body}</div>;
}

/** Presentational part of the Review page (no fetching), so it can be rendered in tests. */
export function ReviewView({ data, cur, skipped, form, busy, msg, loadError, setCur, setForm, onConfirm, onSkip, onNextPage, list = DEFAULT_LIST, setList, facets, onClearSkipped, onPrevPage, statusPublished = false, editSlot, subjectSlot }: ReviewViewProps) {
  const c = data?.counts ?? {};
  const [pop, setPop] = useState<string | null>(null);
  const [versionsLane, setVersionsLane] = useState(false);   // CAT-WO-04: the "Link versions" lane (families, not files)
  const [popAt, setPopAt] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const closePop = useCallback(() => setPop(null), []);
  const upd = (l: Partial<ReviewListState>) => setList?.((cur0) => ({ ...cur0, ...l }));
  const toggleLane = (lane: string) => upd({ lanes: list.lanes.includes(lane) ? list.lanes.filter((x) => x !== lane) : [...list.lanes, lane] });
  const width = (k: string) => list.widths[k] ?? COLS.find((x) => x.key === k)!.width;
  const startResize = (k: string, e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation();
    const x0 = e.clientX, w0 = width(k);
    const move = (ev: PointerEvent) => setList?.((l) => ({ ...l, widths: { ...l.widths, [k]: Math.max(60, Math.min(900, Math.round(w0 + ev.clientX - x0))) } }));
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
    if (f === "location") return <ContainsInput value={list.filters.location ?? ""} onChange={(x) => { upd({ filters: { ...list.filters, location: x || undefined } }); setPop(null); }} />;
    if (f === "fy") return <RangeInputs type="year" value={list.filters.fy_range ?? {}} onChange={(r) => { upd({ filters: { ...list.filters, fy_range: r } }); setPop(null); }} />;
    const key = f === "kind" ? "kind" : f === "entity" ? "entity" : "stage";
    const v = ((list.filters as Record<string, string[] | undefined>)[key]) ?? [];
    return <PickList options={facets?.[key] ?? []} value={v} onChange={(x) => upd({ filters: { ...list.filters, [key]: x } })} label={label(key === "entity" ? undefined : (key as VocabList))} />;
  };
  const isOn = (f: Col["filter"]) => f === "location" ? !!list.filters.location : f === "lane" ? list.lanes.length > 0 : f === "fy" ? !!(list.filters.fy_range?.from || list.filters.fy_range?.to)
    : !!((list.filters as Record<string, string[] | undefined>)[f === "kind" ? "kind" : f === "entity" ? "entity" : "stage"]?.length);
  const nFilters = activeFilters(list);
  const rows = (data?.rows ?? []).filter((r) => !skipped.includes(r.file_id));
  const pageSize = data?.pageSize ?? list.pageSize;
  const from = data && data.matched ? data.page * pageSize + 1 : 0;
  const to = data ? data.page * pageSize + data.pageRows : 0;
  const lastPage = data?.matched ? Math.max(0, Math.ceil(data.matched / pageSize) - 1) : 0;
  const pager = data && data.matched !== 0 ? (
    <div className="pager">
      <div className="left">
        <span>
          {data.matched != null ? `Page ${(data.page + 1).toLocaleString()} of ${(lastPage + 1).toLocaleString()} · ` : ""}
          {data.matched == null ? `${data.pageRows} on this page` : data.pageRows ? `${from.toLocaleString()}–${to.toLocaleString()} of ${data.matched.toLocaleString()} files` : `None shown on this page · ${data.matched.toLocaleString()} files`}
        </span>
      </div>
      <div className="left">
        {setList ? <><span className="cap">Per page</span>
          <div className="seg">{PAGE_SIZES.map((n) => <button key={n} className={list.pageSize === n ? "on" : ""} onClick={() => upd({ pageSize: n })}>{n}</button>)}</div></> : null}
        <div className="pages">
          <button className="pg" disabled={!data.page} onClick={() => (onPrevPage ? onPrevPage() : onNextPage(Math.max(0, data.page - 1)))} aria-label="Previous page">‹</button>
          {(data.matched != null ? pageList(data.page, lastPage) : [data.page]).map((p, i) => p === "gap" ? <span key={`g${i}`} className="gap">…</span>
            : <button key={p} className={`pg${p === data.page ? " on" : ""}`} onClick={() => onNextPage(p)} aria-current={p === data.page ? "page" : undefined}>{(p + 1).toLocaleString()}</button>)}
          <button className="pg" disabled={data.nextPage == null} onClick={() => data.nextPage != null && onNextPage(data.nextPage)} aria-label="Next page">›</button>
        </div>
      </div>
    </div>
  ) : null;
  const chips: { k: string; label: string; text: string; clear: () => void }[] = [];
  if (list.lanes.length) chips.push({ k: "lane", label: "Lane", text: list.lanes.map((l) => REASON[l] ?? l).join(", "), clear: () => upd({ lanes: [] }) });
  for (const [k, lbl, voc] of [["kind", "Kind", "kind"], ["entity", "Entity", undefined], ["stage", "Signing stage", "stage"]] as const) {
    const v = (list.filters as Record<string, string[] | undefined>)[k];
    if (v?.length) chips.push({ k, label: lbl, text: v.map((x) => (voc && x !== "(none)" ? display(voc, x) : x)).join(", "), clear: () => upd({ filters: { ...list.filters, [k]: [] } }) });
  }
  const fy = list.filters.fy_range;
  if (list.filters.location) chips.push({ k: "location", label: "Location", text: `contains “${list.filters.location}”`, clear: () => upd({ filters: { ...list.filters, location: undefined } }) });
  if (fy?.from || fy?.to) chips.push({ k: "fy", label: "Fiscal year", text: fy.from && fy.to ? `${fy.from} – ${fy.to}` : fy.from ? `from ${fy.from}` : `to ${fy.to}`, clear: () => upd({ filters: { ...list.filters, fy_range: {} } }) });
  const cell = (r: Row, k: string) =>
    k === "name" ? shownName(r.name, r.file_id) : k === "why" ? why(r) : k === "confidence" ? (r.confidence ?? "") : k === "location" ? <LocationCell location={r.location} folderId={r.location_folder_id} other={r.other_locations} /> : show(k, (r as unknown as Record<string, unknown>)[k]);

  return (
    <div className="review">
      <PageHeader
        title="Review queue"
        info={<>Files the catalog wants a person to check, most uncertain first: signing stage unknown, then fully executed at low confidence, then no kind, then match subject (which roster partner a document is about), then status unknown. Each page is checked live against Drive as you; Confirm writes the Stage (or Status) and Catalog Review labels on the file. A bulk edit does not take a file out of the queue; only Confirmed or Wrong does.</>}
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
        <Kpi cap="Open" n={c.open_total ?? 0} exp="Files waiting for a person, across all lanes." on={!!setList && !list.lanes.length} onClick={setList ? () => upd({ lanes: [] }) : undefined} />
        <Kpi cap="Stage unknown" n={c.stage_unknown ?? 0} exp="Signed documents whose signing stage couldn't be read." on={list.lanes.includes("stage_unknown")} onClick={setList ? () => toggleLane("stage_unknown") : undefined} />
        <Kpi cap="Status unknown" n={c.status_unknown ?? 0} exp="Not a signed document, and no Draft / Final / Issued status found." on={list.lanes.includes("status_unknown")} onClick={setList ? () => toggleLane("status_unknown") : undefined} />
        <Kpi cap="Executed, low confidence" n={c.low_confidence_executed ?? 0} exp="Marked fully executed, but the scan isn't sure." on={list.lanes.includes("low_confidence_executed")} onClick={setList ? () => toggleLane("low_confidence_executed") : undefined} />
        <Kpi cap="Match subject" n={c.match_subject ?? 0} exp="Which roster partner is this document about? (R-026)" on={list.lanes.includes("match_subject")} onClick={setList ? () => toggleLane("match_subject") : undefined} />
        <Kpi cap="Content disagrees" n={c.content_disagrees ?? 0} exp="Page 1 shows a different fiscal year, period or entity than the catalog. Nothing was overwritten: check it." on={list.lanes.includes("content_disagrees")} onClick={setList ? () => toggleLane("content_disagrees") : undefined} />
        <Kpi cap="Link versions" n={c.link_versions ?? 0} exp="Proposed version families: accept, split or pick the current one." on={versionsLane} onClick={setList ? () => setVersionsLane((x) => !x) : undefined} />
        <Kpi cap="Portal kind conflict" n={c.portal_kind_conflict ?? 0} exp="Posted in a portal as one document type, but the catalog's kind differs. The kind is not changed: check it." onClick={() => { window.location.href = "/?portal_conflict=1"; }} />
        <Kpi cap="No kind" n={c.no_kind ?? 0} exp="The catalog couldn't tell what the document is." on={list.lanes.includes("no_kind")} onClick={setList ? () => toggleLane("no_kind") : undefined} />
        <Kpi cap="Reviewed today" n={c.reviewed_today ?? 0} exp="Confirmed or marked wrong since midnight." />
        <Kpi cap="Skipped" n={skipped.length} exp="Set aside in this browser session; nothing written." />
      </div>
      {loadError ? (
        <div className="status error" role="alert">
          Could not load the review queue: {loadError}. Reload the page to try again; if it keeps failing, sign in again.
        </div>
      ) : null}
      {versionsLane ? <LinkVersionsLane /> : (
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
          {chips.length && setList ? (
            <div className="chips" aria-label="Active filters">
              {chips.map((ch) => <span key={ch.k} className="chip"><b>{ch.label}</b>{ch.text}<button aria-label={`Remove ${ch.label} filter`} onClick={ch.clear}>×</button></span>)}
            </div>
          ) : null}
          {pager}
          <div className="grid-wrap">
            <table className="grid queue" style={{ width: COLS.reduce((n, x) => n + width(x.key), 0) }}>
              <colgroup>{COLS.map((x) => <col key={x.key} style={{ width: width(x.key) }} />)}</colgroup>
              <thead><tr>{COLS.map((x) => {
                const on = list.sort.col === x.sort;
                const fid = `rf-${x.key}`;
                return (
                  <th key={x.key} aria-sort={on ? (list.sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                    <div className="th">
                      {x.sort && setList
                        ? <button type="button" className="lbl sortable" onClick={() => sortBy(x.sort!)} title={`Sort by ${x.label}`}>{x.label}</button>
                        : <span className="lbl">{x.label}</span>}
                      {x.sort && setList ? <span className={`sort${on ? " on" : ""}`} aria-hidden="true">{on ? (list.sort.dir === "asc" ? "↑" : "↓") : "↕"}</span> : null}
                      {x.filter && setList ? (
                        <span className="pop-wrap" style={{ marginLeft: "auto" }}>
                          <button className={`fbtn${isOn(x.filter) ? " on" : ""}`} aria-label={`Filter ${x.label}`} aria-expanded={pop === fid}
                            onClick={(e) => { e.stopPropagation(); const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); setPopAt({ top: r.bottom + 6, left: Math.max(8, Math.min(r.right - 320, window.innerWidth - 336)) }); setPop(pop === fid ? null : fid); }}>
                            <Icon name="filter" />
                          </button>
                          <Pop open={pop === fid} onClose={closePop} className="popover fixed" style={popAt}>
                            <div className="cap" style={{ marginBottom: 6 }}>{x.filter === "lane" ? "Lane is any of" : x.filter === "fy" ? "Fiscal year from / to" : `${x.label} is any of`}</div>
                            {filterBody(x.filter)}
                          </Pop>
                        </span>
                      ) : null}
                    </div>
                    {setList ? <span className="resize" role="separator" aria-orientation="vertical" aria-label={`Resize ${x.label}`} onPointerDown={(e) => startResize(x.key, e)}
                      onDoubleClick={() => { const w = { ...list.widths }; delete w[x.key]; upd({ widths: w }); }} /> : null}
                  </th>
                );
              })}</tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.file_id} onClick={() => setCur(r)} className={cur?.file_id === r.file_id ? "sel" : ""} tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setCur(r); } }} aria-selected={cur?.file_id === r.file_id}>
                    {COLS.map((x) => (
                      <td key={x.key} className={x.key === "why" ? "why" : x.key === "name" ? "name" : undefined} title={x.key === "why" || x.key === "name" ? String(cell(r, x.key)) : undefined}>
                        {cell(r, x.key)}
                        {(r.changed as string[]).includes(x.key) ? <span className="chg" title={`Catalog DB: ${String((r.catalog as Record<string, unknown>)[x.key] ?? "") || "(empty)"}`}>changed in Drive</span> : null}
                      </td>
                    ))}
                  </tr>
                ))}
                {data && !rows.length ? (
                  <tr><td className="empty" colSpan={COLS.length}>
                    {data.matched === 0 && !nFilters ? "Nothing waiting for review."
                      : data.matched === 0 ? <>No files match these filters. {setList ? <button className="link" onClick={() => upd({ lanes: [], filters: {} })}>Clear all</button> : null}</>
                      : <>Nothing shown on this page.{data.nextPage != null ? <> <button className="link" onClick={() => onNextPage(data.nextPage!)}>Next page</button></> : null}</>}
                  </td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {pager}
        </section>
        {cur ? (
          <SidePanel row={cur} onClose={() => setCur(null)}>
            {cur.queue_reason === "match_subject" && subjectSlot ? subjectSlot : null}
            <form className="review-form" onSubmit={(e) => { e.preventDefault(); onConfirm(); }}>
              <p className="why small"><b>Why:</b> {why(cur)}</p>
              {isExecutable(cur) ? <fieldset>
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
              </fieldset> : <fieldset>
                <legend>Status &amp; Execution label</legend>
                <label>Status
                  <select value={form.doc_status ?? ""} disabled={!statusPublished} onChange={(e) => setForm({ ...form, doc_status: e.target.value })}>
                    <option value="">(leave unchanged)</option>
                    {DOC_STATUSES.map((s) => <option key={s} value={s}>{display("status", s)}</option>)}
                  </select>
                </label>
                {!statusPublished ? <p className="muted small">Status isn&apos;t on the Drive labels yet (it publishes with the Part 2 release), so it can&apos;t be set here. Confirm still records your review.</p> : null}
              </fieldset>}
              <fieldset>
                <legend>Catalog Review label</legend>
                <label className="radio"><input type="radio" name="st" checked={form.status === "confirmed"} onChange={() => setForm({ ...form, status: "confirmed" })} /> Confirmed</label>
                <label className="radio"><input type="radio" name="st" checked={form.status === "wrong"} onChange={() => setForm({ ...form, status: "wrong" })} /> Wrong - see note</label>
                <label>Note<textarea value={form.note} maxLength={2000} rows={3} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
                <p className="muted small">Reviewed by is set to you. No other label or file property is changed; use Edit labels below for kind, entity and the rest.</p>
              </fieldset>
              <div className="actions">
                <button className="btn primary" type="submit" disabled={busy}>Confirm and next</button>
                <button className="btn" type="button" onClick={onSkip} disabled={busy}>Skip</button>
              </div>
              {!data?.canWrite ? <p className="muted small">The first Confirm asks Google once for label-write access.</p> : null}
              {msg ? <p className={`status${msg.startsWith("Not saved") ? " error" : ""}`} role="status" aria-live="polite">{msg}</p> : null}
            </form>
            {editSlot}
          </SidePanel>
        ) : null}
      </div>
      )}
    </div>
  );
}
