"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, show, type NotShown, type Row } from "./client";
import { SidePanel } from "./SidePanel";
import { PageHeader } from "./AppShell";
import { useOutside } from "./ViewTree";
import { emit, EV, on, shownName, type ViewRef } from "./bus";
import { Icon } from "./icons";
import { COLUMN_BY_KEY, COLUMN_DEFS, DEFAULT_COLUMNS, DEFAULT_PAGE_SIZE, PAGE_SIZES, PICK_FILTER_KEY, isSortable, type ColDef } from "@/lib/columns";
import { display, type VocabList } from "@/lib/vocab";

type Facet = { value: string; n: number; label?: string };
type Facets = Record<string, Facet[]>;
type Range = { from?: string; to?: string };
type Filters = Record<string, unknown> & {
  kind?: string[]; entity?: string[]; portco?: string[]; fiscal_year?: string[]; stage?: string[]; tier?: string[];
  period?: string[]; workstream?: string[]; issuer?: string[]; file_type_family?: string[];
  primary_only?: boolean; is_primary?: "yes" | "no"; fy_range?: Range; modified_time?: Range; signed_date?: Range; effective_date?: Range;
  file_id?: string; document_id?: string;
};
type Spec = { filters: Filters; search?: string; sort: { col: string; dir: "asc" | "desc" }; groupBy: string | null; page: number; pageSize: number };
type Layout = { columns: string[]; widths: Record<string, number> };
type FindResp = {
  total: number; page: number; pageSize: number; pageRows: number; rows: Row[]; notShown: NotShown; groups: { value: string; n: number }[];
  search: { nameMatches: number; nameCapped: boolean; nameSearchFailed: boolean } | null;
};
type SavedView = { view_id: number; name: string; spec: Record<string, unknown>; folder_id: number | null };
type Folder = { folder_id: number; name: string; parent_id: number | null };

const EMPTY: Spec = { filters: {}, sort: { col: "modified_time", dir: "desc" }, groupBy: null, page: 0, pageSize: DEFAULT_PAGE_SIZE };
const DEFAULT_LAYOUT: Layout = { columns: DEFAULT_COLUMNS, widths: {} };
const GROUPS: [string, string][] = [["", "No grouping"], ["kind", "Kind"], ["entity", "Entity"], ["portco", "Portco"], ["fiscal_year", "Fiscal year"], ["stage", "Signing stage"], ["tier", "Handling"], ["workstream", "Workstream"]];
/** Filter-bar fields (Datum's filter bar). The same filters also sit in each column header. */
const BAR: { key: string; label: string; facet: string; vocab?: VocabList }[] = [
  { key: "kind", label: "Kind", facet: "kind", vocab: "kind" }, { key: "entity", label: "Entity", facet: "entity" }, { key: "portco", label: "Portco", facet: "portco" },
  { key: "fiscal_year", label: "Fiscal year", facet: "fiscal_year" }, { key: "stage", label: "Signing stage", facet: "stage", vocab: "stage" }, { key: "tier", label: "Handling", facet: "tier", vocab: "tier" },
];
const FILTER_LABEL: Record<string, string> = {
  kind: "Kind", entity: "Entity", portco: "Portco", fiscal_year: "Fiscal year", stage: "Signing stage", tier: "Handling", period: "Period", workstream: "Workstream",
  issuer: "Issuer type", file_type_family: "File type", primary_only: "Primary copy", is_primary: "Primary copy", fy_range: "Fiscal year", modified_time: "Modified",
  signed_date: "Signed date", effective_date: "Effective date", file_id: "File ID", document_id: "Catalog ID",
};
const VOCAB_OF: Record<string, VocabList | undefined> = { kind: "kind", stage: "stage", tier: "tier", period: "period", workstream: "workstream", issuer: "issuer" };
const SAVE_DEBOUNCE = 800;

const width = (layout: Layout, k: string) => layout.widths[k] ?? COLUMN_BY_KEY.get(k)?.width ?? 140;
const isActive = (v: unknown) => Array.isArray(v) ? v.length > 0 : v && typeof v === "object" ? Object.values(v).some((x) => x != null && x !== "") : v != null && v !== "" && v !== false;
const optLabel = (key: string, o: Facet) => o.label ?? (o.value !== "(none)" && VOCAB_OF[key] ? display(VOCAB_OF[key]!, o.value) : o.value);
const rangeText = (r: Range) => r.from && r.to ? `${r.from} – ${r.to}` : r.from ? `from ${r.from}` : `to ${r.to}`;

function groupValue(r: Row, g: string): string[] {
  const v = g === "entity" ? r.entities : g === "portco" ? r.portcos : (r as unknown as Record<string, unknown>)[g];
  if (Array.isArray(v)) return v.length ? v.map(String) : ["(none)"];
  return [v == null || v === "" ? "(none)" : String(v)];
}
function pageList(cur: number, last: number): (number | "gap")[] {
  const s = new Set([0, last, cur - 1, cur, cur + 1].filter((n) => n >= 0 && n <= last));
  const out: (number | "gap")[] = [];
  let prev = -1;
  for (const n of [...s].sort((a, b) => a - b)) { if (prev >= 0 && n - prev > 1) out.push("gap"); out.push(n); prev = n; }
  return out;
}
/** spec + layout -> what the server stores / runs. Empty filters dropped. */
function wire(spec: Spec): Spec {
  const filters: Filters = {};
  for (const [k, v] of Object.entries(spec.filters)) if (isActive(v)) filters[k] = v;
  return { ...spec, filters, search: spec.search || undefined };
}
function fromStored(x: Record<string, unknown>): { spec: Spec; layout: Layout | null } {
  const spec: Spec = {
    filters: (x.filters as Filters) ?? {}, sort: (x.sort as Spec["sort"]) ?? EMPTY.sort, groupBy: (x.groupBy as string | null) ?? null, page: 0,
    pageSize: PAGE_SIZES.includes(Number(x.pageSize) as never) ? Number(x.pageSize) : DEFAULT_PAGE_SIZE,
  };
  const cols = Array.isArray(x.columns) ? (x.columns as string[]).filter((c) => COLUMN_BY_KEY.has(c)) : null;
  return { spec, layout: cols?.length ? { columns: cols.includes("name") ? cols : ["name", ...cols], widths: (x.widths as Record<string, number>) ?? {} } : null };
}

/** Normalized form of a stored view, for "changed" detection: active filters only, default layout filled in. */
function fingerprint(x: Record<string, unknown>): string {
  const s = fromStored(x);
  const l = s.layout ?? DEFAULT_LAYOUT;
  const w = wire({ ...s.spec, search: undefined });
  const widths = Object.fromEntries(Object.entries(l.widths).filter(([k, v]) => v !== COLUMN_BY_KEY.get(k)?.width).sort());
  return JSON.stringify({ f: Object.fromEntries(Object.entries(w.filters).sort()), s: w.sort, g: w.groupBy ?? null, p: w.pageSize, c: l.columns, w: widths });
}

// ------------------------------------------------------------------ small pieces
function Pop({ open, onClose, children, className = "popover", style }: { open: boolean; onClose: () => void; children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  const ref = useRef<HTMLDivElement | null>(null);
  useOutside(ref, onClose, open);
  return open ? <div ref={ref} className={className} style={style} onClick={(e) => e.stopPropagation()}>{children}</div> : null;
}

function PickList({ options, value, onChange, label }: { options: Facet[]; value: string[]; onChange: (v: string[]) => void; label: (o: Facet) => string }) {
  const [q, setQ] = useState("");
  const t = q.trim().toLowerCase();
  const shown = options.filter((o) => !t || o.value.toLowerCase().includes(t) || label(o).toLowerCase().includes(t));
  return (
    <>
      {options.length > 8 ? <input className="input" type="search" placeholder="Find a code" value={q} onChange={(e) => setQ(e.target.value)} autoFocus style={{ width: "100%" }} /> : null}
      <div className="opts">
        {shown.map((o) => (
          <label key={o.value} className="opt">
            <input type="checkbox" checked={value.includes(o.value)} onChange={(e) => onChange(e.target.checked ? [...value, o.value] : value.filter((x) => x !== o.value))} />
            <span>{label(o)}</span>{label(o) !== o.value ? <span className="code">{o.value}</span> : null}
            <span className="n">{o.n.toLocaleString()}</span>
          </label>
        ))}
        {!shown.length ? <div className="muted small">No match.</div> : null}
      </div>
      <div className="row"><span className="muted small">{value.length ? `${value.length} selected` : "Any"}</span>{value.length ? <button className="link small" onClick={() => onChange([])}>Clear</button> : null}</div>
    </>
  );
}

function RangeInputs({ type, value, onChange }: { type: "year" | "date"; value: Range; onChange: (r: Range) => void }) {
  const [a, setA] = useState(value.from ?? "");
  const [b, setB] = useState(value.to ?? "");
  const commit = () => onChange({ from: a || undefined, to: b || undefined });
  return (
    <>
      <div className="row" style={{ justifyContent: "flex-start" }}>
        <input className="input" type={type === "year" ? "number" : "date"} placeholder="From" value={a} min={type === "year" ? 1990 : undefined} max={type === "year" ? 2100 : undefined}
          onChange={(e) => setA(e.target.value)} onKeyDown={(e) => e.key === "Enter" && commit()} aria-label="From" style={{ width: type === "year" ? 90 : 140 }} />
        <span className="muted">to</span>
        <input className="input" type={type === "year" ? "number" : "date"} placeholder="To" value={b} min={type === "year" ? 1990 : undefined} max={type === "year" ? 2100 : undefined}
          onChange={(e) => setB(e.target.value)} onKeyDown={(e) => e.key === "Enter" && commit()} aria-label="To" style={{ width: type === "year" ? 90 : 140 }} />
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="link small" onClick={() => { setA(""); setB(""); onChange({}); }}>Clear</button>
        <button className="btn sm" onClick={commit}>Apply</button>
      </div>
    </>
  );
}

function ContainsInput({ value, onChange }: { value: string; onChange: (s: string) => void }) {
  const [v, setV] = useState(value);
  return (
    <>
      <input className="input" type="search" placeholder="contains" value={v} maxLength={100} autoFocus onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onChange(v.trim())} style={{ width: "100%" }} />
      <div className="row" style={{ marginTop: 8 }}>
        <button className="link small" onClick={() => { setV(""); onChange(""); }}>Clear</button>
        <button className="btn sm" onClick={() => onChange(v.trim())}>Apply</button>
      </div>
    </>
  );
}

function FlagInput({ value, onChange }: { value: "yes" | "no" | undefined; onChange: (v: "yes" | "no" | undefined) => void }) {
  return (
    <div className="seg" role="radiogroup">
      {([["yes", "Yes"], ["no", "No"], [undefined, "Any"]] as const).map(([v, l]) => (
        <button key={l} role="radio" aria-checked={value === v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>{l}</button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ Find
export function FindClient() {
  const [facets, setFacets] = useState<Facets | null>(null);
  const [spec, setSpec] = useState<Spec>(EMPTY);
  const [layout, setLayout] = useState<Layout>(DEFAULT_LAYOUT);
  const [ready, setReady] = useState(false);
  const [res, setRes] = useState<FindResp | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<Row | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [current, setCurrent] = useState<{ id: number; name: string; stored: string } | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [pop, setPop] = useState<string | null>(null); // which popover is open
  const [popAt, setPopAt] = useState<{ top: number; left: number }>({ top: 0, left: 0 }); // column popovers: fixed, so the grid's scroll box can't clip them
  const [saveName, setSaveName] = useState("");
  const [saveFolder, setSaveFolder] = useState<string>("");
  const [folders, setFolders] = useState<Folder[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [dragCol, setDragCol] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);
  const reqId = useRef(0);
  const userActed = useRef(false); // a rail click or a search before the start-up load finished wins (coder review #7)
  const closePop = useCallback(() => setPop(null), []);

  // ---------------------------------------------------------------- start: URL (?view= / ?q=), else the last state
  useEffect(() => {
    api<Facets>("/api/facets").then(setFacets).catch((e) => setErr((e as Error).message));
    (async () => {
      const u = new URLSearchParams(window.location.search);
      const viewId = Number(u.get("view"));
      const q = u.get("q") ?? "";
      try {
        if (viewId) {
          const r = await api<{ views: SavedView[] }>("/api/views");
          const v = r.views.find((x) => x.view_id === viewId);
          if (v) { applyStored(v.view_id, v.name, v.spec, q); return; }
        }
        const p = await api<{ value: Record<string, unknown> | null }>("/api/prefs?key=find");
        if (userActed.current) return;
        if (p.value) {
          const s = fromStored(p.value);
          setSpec({ ...s.spec, search: q || undefined });
          if (s.layout) setLayout(s.layout);
          const vid = Number(p.value.viewId);
          if (vid) {
            const r = await api<{ views: SavedView[] }>("/api/views").catch(() => ({ views: [] as SavedView[] }));
            const v = r.views.find((x) => x.view_id === vid);
            if (v) { setCurrent({ id: v.view_id, name: v.name, stored: fingerprint(v.spec) }); emit(EV.currentView, { viewId: v.view_id }); }
          }
        } else if (q) setSpec({ ...EMPTY, search: q });
      } catch { /* defaults */ }
      finally { setReady(true); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyStored = (id: number | null, name: string, stored: Record<string, unknown>, search?: string) => {
    const s = fromStored(stored);
    setSpec({ ...s.spec, search: search || undefined });
    setLayout(s.layout ?? DEFAULT_LAYOUT);
    setCurrent(id ? { id, name, stored: fingerprint(stored) } : null);
    setChecked(new Set());
    setReady(true);
    emit(EV.currentView, { viewId: id });
  };

  // shell events: a view clicked in the rail; a search from the top bar
  useEffect(() => {
    const a = on<ViewRef>(EV.applyView, (v) => { userActed.current = true; applyStored(v.view_id, v.name, v.spec, undefined); });
    const b = on<{ q: string }>(EV.search, (d) => { userActed.current = true; setReady(true); setSpec((s) => ({ ...s, page: 0, search: d.q || undefined })); });
    // the rail renamed or deleted the view shown here (coder review #8)
    const c = on(EV.treeChanged, async () => {
      const r = await api<{ views: SavedView[] }>("/api/views").catch(() => null);
      if (!r) return;
      setCurrent((cur) => {
        if (!cur) return cur;
        const v = r.views.find((x) => x.view_id === cur.id);
        if (!v) { emit(EV.currentView, { viewId: null }); return null; }
        return v.name === cur.name ? cur : { ...cur, name: v.name };
      });
    });
    return () => { a(); b(); c(); };
  }, []);

  // ---------------------------------------------------------------- run (server-side SQL + live page check)
  const run = useCallback(async (s: Spec) => {
    const id = ++reqId.current;
    setBusy(true); setErr(null);
    try {
      const r = await api<FindResp>("/api/find", { method: "POST", body: JSON.stringify(wire(s)) });
      if (id === reqId.current) { setRes(r); setChecked(new Set()); }
    } catch (e) {
      if (id === reqId.current) {
        const b = (e as { body?: { reason?: string } }).body;
        setErr(b?.reason ?? (e as Error).message);
      }
    } finally { if (id === reqId.current) setBusy(false); }
  }, []);
  useEffect(() => { if (ready) run(spec); }, [spec, ready, run]);

  // ---------------------------------------------------------------- remember the last state per user (item 2)
  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => {
      const { search: _s, ...rest } = wire(spec);
      void _s;
      api("/api/prefs", { method: "PUT", body: JSON.stringify({ key: "find", value: { ...rest, ...layout, viewId: current?.id ?? null } }) }).catch(() => {});
    }, SAVE_DEBOUNCE);
    return () => clearTimeout(t);
  }, [spec, layout, current, ready]);

  // ---------------------------------------------------------------- spec helpers
  const setFilter = (k: string, v: unknown) => setSpec((s) => {
    const f: Filters = { ...s.filters, [k]: v };
    if (k === "is_primary") delete f.primary_only; // one "primary copy" filter at a time
    if (!isActive(v)) delete f[k];
    return { ...s, page: 0, filters: f };
  });
  const sortBy = (c: string) => { if (!isSortable(c)) return; setSpec((s) => ({ ...s, page: 0, sort: { col: c, dir: s.sort.col === c && s.sort.dir === "desc" ? "asc" : "desc" } })); };
  const setPage = (p: number) => setSpec((s) => ({ ...s, page: p }));

  const chips = useMemo(() => {
    const out: { key: string; label: string; text: string }[] = [];
    const f = spec.filters;
    for (const [k, v] of Object.entries(f)) {
      if (!isActive(v)) continue;
      let text: string;
      if (Array.isArray(v)) text = v.map((x) => (VOCAB_OF[k] && x !== "(none)" ? display(VOCAB_OF[k]!, String(x)) : String(x))).join(", ");
      else if (k === "primary_only") text = "only";
      else if (k === "is_primary") text = v === "yes" ? "yes" : "no";
      else if (typeof v === "object") text = rangeText(v as Range);
      else text = `contains “${String(v)}”`;
      out.push({ key: k, label: FILTER_LABEL[k] ?? k, text });
    }
    return out;
  }, [spec.filters]);

  // ---------------------------------------------------------------- views
  const loadFolders = () => api<{ folders: Folder[] }>("/api/views").then((r) => setFolders(r.folders)).catch(() => {});
  const storedNow = () => ({ ...wire({ ...spec, search: undefined }), ...layout });
  const dirty = current ? fingerprint(storedNow() as unknown as Record<string, unknown>) !== current.stored : false;
  const saveView = async () => {
    const name = saveName.trim();
    if (!name) return;
    try {
      const r = await api<{ id: number }>("/api/views", { method: "POST", body: JSON.stringify({ name, spec: storedNow(), folder_id: saveFolder ? Number(saveFolder) : null }) });
      setCurrent({ id: r.id, name, stored: fingerprint(storedNow() as unknown as Record<string, unknown>) });
      emit(EV.currentView, { viewId: r.id });
      emit(EV.viewsChanged);
      setPop(null); setSaveName(""); setNote(`Saved “${name}”.`);
    } catch (e) { setNote(`Not saved: ${(e as { body?: { error?: string } }).body?.error ?? (e as Error).message}`); }
  };
  const updateView = async () => {
    if (!current) return;
    try {
      await api("/api/views", { method: "PATCH", body: JSON.stringify({ view_id: current.id, spec: storedNow() }) });
      setCurrent({ ...current, stored: fingerprint(storedNow() as unknown as Record<string, unknown>) });
      emit(EV.viewsChanged); setNote(`Updated “${current.name}”.`); setPop(null);
    } catch (e) { setNote(`Not updated: ${(e as Error).message}`); }
  };
  const resetAll = () => { setSpec(EMPTY); setLayout(DEFAULT_LAYOUT); setCurrent(null); emit(EV.currentView, { viewId: null }); setPop(null); };

  // ---------------------------------------------------------------- export
  const download = async (format: "csv" | "xlsx") => {
    setPop(null);
    const r = await fetch(`/api/export?format=${format}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(wire(spec)) });
    if (r.status === 401) { window.location.href = `/api/auth/login?next=${encodeURIComponent(window.location.pathname)}`; return; }
    if (r.status === 413) { const b = await r.json().catch(() => ({})) as { limit?: number }; setNote(`Excel is limited to ${(b.limit ?? 10000).toLocaleString()} rows. Narrow the filters, or use Download CSV (up to 50,000).`); return; }
    if (!r.ok) { setErr(`export failed (${r.status})`); return; }
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a"); a.href = url; a.download = `catalog-export-${new Date().toISOString().slice(0, 10)}.${format}`; a.click();
    URL.revokeObjectURL(url);
  };

  // ---------------------------------------------------------------- columns: resize, reorder, show/hide
  const startResize = (k: string, e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation();
    const x0 = e.clientX, w0 = width(layout, k);
    const target = e.currentTarget as HTMLElement;
    target.classList.add("active");
    document.body.style.cursor = "col-resize"; document.body.style.userSelect = "none";
    const move = (ev: PointerEvent) => setLayout((l) => ({ ...l, widths: { ...l.widths, [k]: Math.max(60, Math.min(900, Math.round(w0 + ev.clientX - x0))) } }));
    const up = () => {
      target.classList.remove("active");
      document.body.style.cursor = ""; document.body.style.userSelect = "";
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  const moveCol = (from: string, to: string) => {
    if (from === to) return;
    setLayout((l) => {
      const c = l.columns.filter((x) => x !== from);
      c.splice(c.indexOf(to), 0, from);
      return { ...l, columns: c };
    });
  };
  const toggleCol = (k: string, onOff: boolean) => setLayout((l) => {
    if (onOff) {
      const order = [...l.columns, k];
      return { ...l, columns: COLUMN_DEFS.map((c) => c.key).filter((x) => order.includes(x)).sort((a, b) => (l.columns.includes(a) && l.columns.includes(b) ? l.columns.indexOf(a) - l.columns.indexOf(b) : 0)) };
    }
    return l.columns.length > 1 ? { ...l, columns: l.columns.filter((x) => x !== k) } : l;
  });

  // ---------------------------------------------------------------- rendering helpers
  const filterOf = (c: ColDef): { active: boolean; body: React.ReactNode } | null => {
    if (c.source !== "db") return null;
    const f = spec.filters;
    if (c.type === "pick") {
      const key = PICK_FILTER_KEY[c.key];
      const v = (f[key] as string[] | undefined) ?? [];
      return { active: v.length > 0, body: <PickList options={facets?.[c.facet!] ?? []} value={v} onChange={(x) => setFilter(key, x)} label={(o) => optLabel(key, o)} /> };
    }
    if (c.type === "year") { const v = (f.fy_range ?? {}) as Range; return { active: isActive(v), body: <RangeInputs type="year" value={v} onChange={(r) => { setFilter("fy_range", r); setPop(null); }} /> }; }
    if (c.type === "date") { const v = (f[c.key] ?? {}) as Range; return { active: isActive(v), body: <RangeInputs type="date" value={v} onChange={(r) => { setFilter(c.key, r); setPop(null); }} /> }; }
    if (c.type === "text") { const v = (f[c.key] as string | undefined) ?? ""; return { active: !!v, body: <ContainsInput value={v} onChange={(s) => { setFilter(c.key, s || undefined); setPop(null); }} /> }; }
    if (c.type === "flag") {
      const v = f.is_primary ?? (f.primary_only ? "yes" : undefined);
      return { active: !!v, body: <FlagInput value={v} onChange={(x) => setFilter("is_primary", x)} /> };
    }
    return null;
  };
  const cell = (r: Row, k: string) => {
    const v = (r as unknown as Record<string, unknown>)[k];
    if (k === "name") return shownName(r.name, r.file_id);
    if (k === "tier") return r.tier ? <span className={`badge ${r.tier}`}>{show("tier", r.tier)}</span> : null;
    if (k === "review_status") return r.review_status ? <span className={`badge review-${r.review_status}`}>{show("review", r.review_status) || r.review_status}</span> : null;
    if (k === "kind" && v) return <span title={String(v)}>{show(k, v)}</span>;
    if (k === "file_id" || k === "document_id") return <code>{v == null ? "" : String(v)}</code>;
    return show(k, v);
  };

  const cols = layout.columns.map((k) => COLUMN_BY_KEY.get(k)!).filter(Boolean);
  const tableWidth = 40 + cols.reduce((n, c) => n + width(layout, c.key), 0);
  const groupCounts = useMemo(() => new Map((res?.groups ?? []).map((g) => [g.value, g.n])), [res]);
  const grouped = useMemo(() => {
    if (!res) return [];
    if (!spec.groupBy) return [{ key: "", rows: res.rows }];
    const m = new Map<string, Row[]>();
    for (const r of res.rows) for (const k of groupValue(r, spec.groupBy)) m.set(k, [...(m.get(k) ?? []), r]);
    return [...m.entries()].map(([key, rows]) => ({ key, rows }));
  }, [res, spec.groupBy]);
  const pageIds = res?.rows.map((r) => r.file_id) ?? [];
  const allChecked = pageIds.length > 0 && pageIds.every((id) => checked.has(id));
  const someChecked = pageIds.some((id) => checked.has(id));
  const from = res && res.total ? res.page * res.pageSize + 1 : 0;
  const to = res ? res.page * res.pageSize + res.pageRows : 0;
  const lastPage = res ? Math.max(0, Math.ceil(res.total / res.pageSize) - 1) : 0;

  const pager = res && res.total > 0 ? (
    <div className="pager">
      <div className="left">
        <span>Page {(res.page + 1).toLocaleString()} of {(lastPage + 1).toLocaleString()} · {from.toLocaleString()}–{to.toLocaleString()} of {res.total.toLocaleString()} files</span>
      </div>
      <div className="left">
        <span className="cap">Per page</span>
        <div className="seg">{PAGE_SIZES.map((n) => <button key={n} className={spec.pageSize === n ? "on" : ""} onClick={() => setSpec((s) => ({ ...s, page: 0, pageSize: n }))}>{n}</button>)}</div>
        <div className="pages">
          <button className="pg" disabled={res.page === 0} onClick={() => setPage(res.page - 1)} aria-label="Previous page">‹</button>
          {pageList(res.page, lastPage).map((p, i) => p === "gap" ? <span key={`g${i}`} className="gap">…</span>
            : <button key={p} className={`pg${p === res.page ? " on" : ""}`} onClick={() => setPage(p)} aria-current={p === res.page ? "page" : undefined}>{(p + 1).toLocaleString()}</button>)}
          <button className="pg" disabled={res.page >= lastPage} onClick={() => setPage(res.page + 1)} aria-label="Next page">›</button>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div data-find-page>
      <PageHeader
        title={current ? current.name : "Find"}
        info={<>Every file carrying the Allegis Document label, filtered and sorted in the catalog database. Each page is checked live against Drive as you: files you can&apos;t open are left out and counted, and values shown are the labels on the file today.</>}
        desc={spec.search ? <>Search: “{spec.search}” <button className="link small" onClick={() => setSpec((s) => ({ ...s, page: 0, search: undefined }))}>clear</button></> : current ? <span className="cap">Saved view{dirty ? " · changed" : ""}</span> : null}
        actions={<>
          {current && dirty ? <button className="btn" onClick={updateView}>Update view</button> : null}
          <div className="pop-wrap">
            <button className="btn primary" onClick={() => { loadFolders(); setSaveName(current && !dirty ? `${current.name} (copy)` : ""); setPop(pop === "save" ? null : "save"); }} aria-expanded={pop === "save"}>Save view</button>
            <Pop open={pop === "save"} onClose={closePop} className="popover right">
              <div className="field" style={{ minWidth: 260 }}>
                <span className="cap">View name</span>
                <input className="input" value={saveName} maxLength={80} autoFocus onChange={(e) => setSaveName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveView()} />
              </div>
              <div className="field" style={{ marginTop: 8 }}>
                <span className="cap">Folder</span>
                <select className="input" value={saveFolder} onChange={(e) => setSaveFolder(e.target.value)}>
                  <option value="">Top level</option>
                  {folders.filter((f) => f.parent_id == null).flatMap((f) => [
                    <option key={f.folder_id} value={f.folder_id}>{f.name}</option>,
                    ...folders.filter((k) => k.parent_id === f.folder_id).map((k) => <option key={k.folder_id} value={k.folder_id}>{`  ${f.name} / ${k.name}`}</option>),
                  ])}
                </select>
              </div>
              <p className="small muted" style={{ margin: "8px 0" }}>Saves filters, sort, columns, order and widths. A name already in use is overwritten.</p>
              <div className="row"><span /><button className="btn sm primary" onClick={saveView} disabled={!saveName.trim()}>Save</button></div>
            </Pop>
          </div>
          <div className="pop-wrap">
            <button className="btn" aria-label="More actions" aria-expanded={pop === "more"} onClick={() => setPop(pop === "more" ? null : "more")}><Icon name="more" /></button>
            <Pop open={pop === "more"} onClose={closePop} className="menu">
              <button onClick={() => { setSpec((s) => ({ ...s, page: 0, filters: {} })); setPop(null); }}>Clear filters</button>
              <button onClick={() => { setLayout(DEFAULT_LAYOUT); setPop(null); }}>Reset columns and widths</button>
              <button onClick={resetAll}>Start over (all labelled files)</button>
            </Pop>
          </div>
        </>}
      />
      {note ? <div className="status" role="status">{note} <button className="link small" onClick={() => setNote(null)}>dismiss</button></div> : null}

      <div className={open ? "find with-panel" : "find"}>
        <section className="card list-card" aria-label="Files">
          {/* Datum filter bar */}
          <div className="filterbar">
            <button className="btn sm" onClick={() => setFiltersOpen((o) => !o)} aria-expanded={filtersOpen}><Icon name="filter" />Filters</button>
            <span className="summary">{chips.length ? `${chips.length} filter${chips.length > 1 ? "s" : ""}` : "No filters"}</span>
            {chips.length ? <button className="link small" onClick={() => setSpec((s) => ({ ...s, page: 0, filters: {} }))}>Clear all</button> : null}
            <div className="tools">
              <div className="pop-wrap">
                <button className="btn sm" onClick={() => setPop(pop === "cols" ? null : "cols")} aria-expanded={pop === "cols"}><Icon name="columns" />Columns</button>
                <Pop open={pop === "cols"} onClose={closePop} className="popover right">
                  <div className="cap">Show columns</div>
                  <div className="opts">
                    {[...layout.columns, ...COLUMN_DEFS.map((c) => c.key).filter((k) => !layout.columns.includes(k))].map((k) => (
                      <label key={k} className="opt">
                        <input type="checkbox" checked={layout.columns.includes(k)} disabled={k === "name" || (layout.columns.length === 1 && layout.columns.includes(k))} onChange={(e) => toggleCol(k, e.target.checked)} />
                        {COLUMN_BY_KEY.get(k)!.label}
                        {COLUMN_BY_KEY.get(k)!.source === "live" ? <span className="n">live</span> : null}
                      </label>
                    ))}
                  </div>
                  <div className="small muted">Drag a header to reorder; drag its right edge to resize.</div>
                </Pop>
              </div>
              <button className="btn sm" onClick={() => download("csv")}><Icon name="download" />Download CSV</button>
              <button className="btn sm" onClick={() => download("xlsx")}><Icon name="download" />Download Excel</button>
            </div>
          </div>
          {filtersOpen ? (
            <div className="filter-fields">
              {BAR.map((b) => {
                const v = (spec.filters[b.key] as string[] | undefined) ?? [];
                const id = `bar-${b.key}`;
                return (
                  <div key={b.key} className="field pop-wrap">
                    <span className="cap">{b.label}</span>
                    <button className="trigger" onClick={() => setPop(pop === id ? null : id)} aria-expanded={pop === id}>
                      <span className="val">{v.length ? v.map((x) => optLabel(b.key, { value: x, n: 0 })).join(", ") : "Any"}</span><Icon name="chevDown" className="small" />
                    </button>
                    <Pop open={pop === id} onClose={closePop}>
                      <PickList options={facets?.[b.facet] ?? []} value={v} onChange={(x) => setFilter(b.key, x)} label={(o) => optLabel(b.key, o)} />
                    </Pop>
                  </div>
                );
              })}
              <div className="field">
                <span className="cap">Primary copy</span>
                <FlagInput value={spec.filters.is_primary ?? (spec.filters.primary_only ? "yes" : undefined)} onChange={(x) => setFilter("is_primary", x)} />
              </div>
              <div className="field">
                <span className="cap">Group by</span>
                <select className="input" value={spec.groupBy ?? ""} onChange={(e) => setSpec((s) => ({ ...s, page: 0, groupBy: e.target.value || null }))}>
                  {GROUPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            </div>
          ) : null}
          {chips.length ? (
            <div className="chips" aria-label="Active filters">
              {chips.map((c) => (
                <span key={c.key} className="chip"><b>{c.label}</b>{c.text}<button aria-label={`Remove ${c.label} filter`} onClick={() => setFilter(c.key, undefined)}>×</button></span>
              ))}
            </div>
          ) : null}

          {/* selection + status */}
          <div className="selbar">
            <div className="pop-wrap">
              <button className="btn sm outline" onClick={() => setPop(pop === "actions" ? null : "actions")} aria-expanded={pop === "actions"} disabled={!checked.size}>
                Actions{checked.size ? ` (${checked.size})` : ""} <Icon name="chevDown" />
              </button>
              <Pop open={pop === "actions"} onClose={closePop} className="menu left">
                <div className="hint">Bulk edits (set kind, entity, fiscal year, status…) arrive with CAT-WO-02 Part 2. Nothing here writes yet.</div>
              </Pop>
            </div>
            <span>{checked.size ? `${checked.size} of ${pageIds.length} on this page selected` : pageIds.length ? `Select files on this page (${pageIds.length})` : ""}</span>
            <span className="status-text" role="status">
              {res ? <><b style={{ color: "var(--ink)" }}>{res.total.toLocaleString()}</b> files match</> : null}
              {res?.notShown.noAccess ? <> · <span className="warn">{res.notShown.noAccess} not shown (no access)</span></> : null}
              {res?.notShown.checkFailed ? <> · <span className="warn">{res.notShown.checkFailed} not shown (Drive check failed, retry)</span></> : null}
              {res?.search?.nameCapped ? <> · <span className="warn">name search used the first 2,000 Drive matches</span></> : null}
              {res?.search?.nameSearchFailed ? <> · <span className="warn">name search failed; codes only</span></> : null}
              {busy ? <span className="muted"> · loading…</span> : null}
              {err ? <span className="error"> · {err}</span> : null}
            </span>
          </div>
          {pager}

          <div className="grid-wrap">
            <table className="grid" style={{ width: tableWidth }}>
              <colgroup>
                <col style={{ width: 40 }} />
                {cols.map((c) => <col key={c.key} style={{ width: width(layout, c.key) }} />)}
              </colgroup>
              <thead>
                <tr>
                  <th className="chk">
                    <input type="checkbox" aria-label="Select all on this page" checked={allChecked} ref={(el) => { if (el) el.indeterminate = someChecked && !allChecked; }}
                      onChange={(e) => setChecked(e.target.checked ? new Set(pageIds) : new Set())} />
                  </th>
                  {cols.map((c) => {
                    const sortable = isSortable(c.key);
                    const on = spec.sort.col === c.key;
                    const flt = filterOf(c);
                    const fid = `col-${c.key}`;
                    return (
                      <th key={c.key} className={overCol === c.key && dragCol !== c.key ? "drag-over" : ""} aria-sort={on ? (spec.sort.dir === "asc" ? "ascending" : "descending") : undefined}
                        onDragOver={(e) => { if (dragCol) { e.preventDefault(); setOverCol(c.key); } }}
                        onDragLeave={() => setOverCol((o) => (o === c.key ? null : o))}
                        onDrop={(e) => { e.preventDefault(); if (dragCol) moveCol(dragCol, c.key); setDragCol(null); setOverCol(null); }}>
                        <div className="th">
                          <span className={`lbl${sortable ? " sortable" : ""}`} draggable onDragStart={(e) => { setDragCol(c.key); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", c.key); }}
                            onDragEnd={() => { setDragCol(null); setOverCol(null); }}
                            onClick={() => sortBy(c.key)} title={sortable ? `Sort by ${c.label}` : `${c.label} (live from Drive: not sortable)`}>
                            {c.label}
                          </span>
                          {sortable ? <span className={`sort${on ? " on" : ""}`} aria-hidden="true">{on ? (spec.sort.dir === "asc" ? "↑" : "↓") : "↕"}</span> : null}
                          {flt ? (
                            <span className="pop-wrap" style={{ marginLeft: "auto" }}>
                              <button className={`fbtn${flt.active ? " on" : ""}`} aria-label={`Filter ${c.label}`} aria-expanded={pop === fid} onClick={(e) => {
                                e.stopPropagation();
                                const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
                                setPopAt({ top: r.bottom + 6, left: Math.max(8, Math.min(r.right - 320, window.innerWidth - 336)) });
                                setPop(pop === fid ? null : fid);
                              }}>
                                <Icon name="filter" />
                              </button>
                              <Pop open={pop === fid} onClose={closePop} className="popover fixed" style={popAt}>
                                <div className="cap" style={{ marginBottom: 6 }}>{c.label}{c.type === "text" ? " contains" : c.type === "flag" ? "" : c.type === "pick" ? " is any of" : " from / to"}</div>
                                {flt.body}
                              </Pop>
                            </span>
                          ) : null}
                        </div>
                        <span className="resize" role="separator" aria-orientation="vertical" aria-label={`Resize ${c.label}`} onPointerDown={(e) => startResize(c.key, e)}
                          onDoubleClick={() => setLayout((l) => { const w = { ...l.widths }; delete w[c.key]; return { ...l, widths: w }; })} />
                      </th>
                    );
                  })}
                </tr>
              </thead>
              {grouped.map((g) => (
                <tbody key={g.key || "all"}>
                  {spec.groupBy ? (
                    <tr className="grp"><td colSpan={cols.length + 1}>
                      {g.key === "(none)" ? "(none)" : show(spec.groupBy === "entity" || spec.groupBy === "portco" ? "x" : spec.groupBy, g.key)}
                      <span className="muted"> · {g.rows.length} on this page{groupCounts.has(g.key) ? ` of ${groupCounts.get(g.key)!.toLocaleString()} matched` : ""}</span>
                    </td></tr>
                  ) : null}
                  {g.rows.map((r) => (
                    <tr key={`${g.key}:${r.file_id}`} onClick={() => setOpen(r)} className={`${open?.file_id === r.file_id ? "sel" : ""}${checked.has(r.file_id) ? " checked" : ""}`}>
                      <td className="chk" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" aria-label="Select file" checked={checked.has(r.file_id)} onChange={(e) => setChecked((s) => { const n = new Set(s); if (e.target.checked) n.add(r.file_id); else n.delete(r.file_id); return n; })} />
                      </td>
                      {cols.map((c) => (
                        <td key={c.key} title={c.key === "name" ? shownName(r.name, r.file_id) : undefined}>
                          {cell(r, c.key)}
                          {r.changed.includes(c.key) ? <span className="chg" title={`Catalog DB: ${show(c.key, r.catalog[c.key]) || "(empty)"}`}>changed in Drive</span> : null}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              ))}
              {res && !res.rows.length ? (
                <tbody><tr><td className="empty" colSpan={cols.length + 1}>
                  {res.total ? "Nothing on this page that you can open in Drive. Try the next page." : "No files match. Remove a filter or clear the search."}
                </td></tr></tbody>
              ) : null}
            </table>
          </div>
          {pager}
        </section>

        {open ? <SidePanel row={open} onClose={() => setOpen(null)} /> : null}
      </div>
    </div>
  );
}
