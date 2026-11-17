"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, show, type NotShown, type Row } from "./client";
import { SidePanel } from "./SidePanel";
import { display, type VocabList } from "@/lib/vocab";

type Facet = { value: string; n: number; label?: string };
type Facets = Record<"kind" | "entity" | "portco" | "fiscal_year" | "stage" | "tier", Facet[]>;
type Filters = { kind?: string[]; entity?: string[]; portco?: string[]; fiscal_year?: string[]; stage?: string[]; tier?: string[]; primary_only?: boolean };
type Spec = { filters: Filters; sort: { col: string; dir: "asc" | "desc" }; groupBy: string | null; page: number; columns?: string[] };
type View = { view_id: number; name: string; spec: Spec; is_seed: boolean };
type FindResp = { total: number; page: number; pageSize: number; pageRows: number; rows: Row[]; notShown: NotShown; groups: { value: string; n: number }[] };

const ALL_COLS = ["name", "kind", "entities", "portcos", "fiscal_year", "period", "stage", "executed_date", "signed_date", "workstream", "issuer", "tier", "is_primary", "modified_time", "file_type_family", "review_status"];
const DEFAULT_COLS = ["name", "kind", "entities", "portcos", "fiscal_year", "period", "stage", "tier"];
const SORTABLE = new Set(["kind", "fiscal_year", "period", "stage", "signed_date", "workstream", "issuer", "tier", "modified_time", "file_type_family"]);
const GROUPS: [string, string][] = [["", "No grouping"], ["kind", "Kind"], ["entity", "Entity"], ["portco", "Portco"], ["fiscal_year", "Fiscal year"], ["stage", "Signing stage"], ["tier", "Tier"], ["workstream", "Workstream"]];
const FILTERS: { key: keyof Facets; label: string; vocab?: VocabList }[] = [
  { key: "kind", label: "Kind", vocab: "kind" }, { key: "entity", label: "Entity" }, { key: "portco", label: "Portco" },
  { key: "fiscal_year", label: "Fiscal year" }, { key: "stage", label: "Signing stage", vocab: "stage" }, { key: "tier", label: "Tier", vocab: "tier" },
];
const EMPTY: Spec = { filters: {}, sort: { col: "modified_time", dir: "desc" }, groupBy: null, page: 0 };

function groupValue(r: Row, g: string): string[] {
  const v = g === "entity" ? r.entities : g === "portco" ? r.portcos : (r as unknown as Record<string, unknown>)[g];
  if (Array.isArray(v)) return v.length ? v.map(String) : ["(none)"];
  return [v == null || v === "" ? "(none)" : String(v)];
}

export function FindClient() {
  const [facets, setFacets] = useState<Facets | null>(null);
  const [views, setViews] = useState<View[]>([]);
  const [spec, setSpec] = useState<Spec>(EMPTY);
  const [cols, setCols] = useState<string[]>(DEFAULT_COLS);
  const [res, setRes] = useState<FindResp | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<Row | null>(null);
  const [saveName, setSaveName] = useState("");

  useEffect(() => {
    api<Facets>("/api/facets").then(setFacets).catch((e) => setErr(String(e.message)));
    api<{ views: View[] }>("/api/views").then((r) => setViews(r.views)).catch(() => {});
  }, []);

  const run = useCallback(async (s: Spec) => {
    setBusy(true); setErr(null);
    try { setRes(await api<FindResp>("/api/find", { method: "POST", body: JSON.stringify(s) })); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { run(spec); }, [spec, run]);

  const setFilter = (k: keyof Filters, v: string[] | boolean | undefined) => setSpec((s) => ({ ...s, page: 0, filters: { ...s.filters, [k]: v } }));
  const applyView = (v: View) => { setSpec({ ...EMPTY, ...v.spec, page: 0 }); if (v.spec.columns?.length) setCols(v.spec.columns); };
  const saveView = async () => {
    if (!saveName.trim()) return;
    await api("/api/views", { method: "POST", body: JSON.stringify({ name: saveName.trim(), spec: { ...spec, columns: cols } }) });
    setSaveName("");
    setViews((await api<{ views: View[] }>("/api/views")).views);
  };
  const delView = async (id: number) => { await api(`/api/views?id=${id}`, { method: "DELETE" }); setViews((await api<{ views: View[] }>("/api/views")).views); };
  const exportCsv = async () => {
    const r = await fetch("/api/export", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(spec) });
    if (r.status === 401) { window.location.href = `/api/auth/login?next=${encodeURIComponent(window.location.pathname)}`; return; }
    if (!r.ok) { setErr(`export failed (${r.status})`); return; }
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a"); a.href = url; a.download = `catalog-export-${new Date().toISOString().slice(0, 10)}.csv`; a.click();
    URL.revokeObjectURL(url);
  };
  const sortBy = (c: string) => { if (!SORTABLE.has(c)) return; setSpec((s) => ({ ...s, page: 0, sort: { col: c, dir: s.sort.col === c && s.sort.dir === "desc" ? "asc" : "desc" } })); };

  const groupCounts = useMemo(() => new Map((res?.groups ?? []).map((g) => [g.value, g.n])), [res]);
  const grouped = useMemo(() => {
    if (!res) return [];
    if (!spec.groupBy) return [{ key: "", rows: res.rows }];
    const m = new Map<string, Row[]>();
    for (const r of res.rows) for (const k of groupValue(r, spec.groupBy)) m.set(k, [...(m.get(k) ?? []), r]);
    return [...m.entries()].map(([key, rows]) => ({ key, rows }));
  }, [res, spec.groupBy]);

  const from = res ? res.page * res.pageSize + 1 : 0;
  const to = res ? res.page * res.pageSize + res.pageRows : 0;

  return (
    <div className={open ? "find with-panel" : "find"}>
      <aside className="views">
        <h3>Saved views</h3>
        <ul>
          <li><button className="link" onClick={() => { setSpec(EMPTY); setCols(DEFAULT_COLS); }}>All labelled files</button></li>
          {views.map((v) => (
            <li key={v.view_id}>
              <button className="link" onClick={() => applyView(v)}>{v.name}</button>
              {!v.is_seed ? <button className="x" title="Delete view" onClick={() => delView(v.view_id)}>x</button> : null}
            </li>
          ))}
        </ul>
        <div className="save">
          <input value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="Save current as..." maxLength={80} />
          <button className="btn" onClick={saveView} disabled={!saveName.trim()}>Save</button>
        </div>
      </aside>

      <section className="results">
        <div className="filters">
          {FILTERS.map((f) => {
            const sel = (spec.filters[f.key as keyof Filters] as string[] | undefined) ?? [];
            return (
              <details key={f.key} className="filter">
                <summary>{f.label}{sel.length ? <b> ({sel.length})</b> : null}</summary>
                <div className="opts">
                  {(facets?.[f.key] ?? []).map((o) => (
                    <label key={o.value}>
                      <input type="checkbox" checked={sel.includes(o.value)}
                        onChange={(e) => setFilter(f.key as keyof Filters, e.target.checked ? [...sel, o.value] : sel.filter((x) => x !== o.value))} />
                      {o.label ?? (f.vocab && o.value !== "(none)" ? display(f.vocab, o.value) : o.value)} <span className="muted">{o.n.toLocaleString()}</span>
                    </label>
                  ))}
                </div>
              </details>
            );
          })}
          <label className="chk"><input type="checkbox" checked={!!spec.filters.primary_only} onChange={(e) => setFilter("primary_only", e.target.checked || undefined)} /> Primary copy only</label>
          <select value={spec.groupBy ?? ""} onChange={(e) => setSpec((s) => ({ ...s, page: 0, groupBy: e.target.value || null }))} aria-label="Group by">
            {GROUPS.map(([v, l]) => <option key={v} value={v}>{v ? `Group: ${l}` : l}</option>)}
          </select>
          <details className="filter">
            <summary>Columns</summary>
            <div className="opts">
              {ALL_COLS.map((c) => (
                <label key={c}><input type="checkbox" checked={cols.includes(c)} disabled={c === "name"}
                  onChange={(e) => setCols(e.target.checked ? ALL_COLS.filter((x) => x === c || cols.includes(x)) : cols.filter((x) => x !== c))} /> {c.replace(/_/g, " ")}</label>
              ))}
            </div>
          </details>
          <button className="btn" onClick={exportCsv}>Export CSV</button>
          {Object.values(spec.filters).some((v) => (Array.isArray(v) ? v.length : v)) ? <button className="link" onClick={() => setSpec((s) => ({ ...s, page: 0, filters: {} }))}>Clear filters</button> : null}
        </div>

        <div className="status" role="status">
          {res ? (
            <>
              <b>{res.total.toLocaleString()}</b> matched{res.total ? <> · rows {from.toLocaleString()}–{to.toLocaleString()}</> : null}
              {res.notShown.noAccess ? <span className="warn"> · {res.notShown.noAccess} not shown (no access)</span> : null}
              {res.notShown.checkFailed ? <span className="warn"> · {res.notShown.checkFailed} not shown (Drive check failed - retry)</span> : null}
            </>
          ) : null}
          {busy ? <span className="muted"> · loading…</span> : null}
          {err ? <span className="error"> · {err}</span> : null}
        </div>

        <table className="grid">
          <thead>
            <tr>{cols.map((c) => (
              <th key={c} onClick={() => sortBy(c)} className={SORTABLE.has(c) ? "sortable" : ""}>
                {c.replace(/_/g, " ")}{spec.sort.col === c ? (spec.sort.dir === "desc" ? " ↓" : " ↑") : ""}
              </th>
            ))}</tr>
          </thead>
          {grouped.map((g) => (
            <tbody key={g.key || "all"}>
              {spec.groupBy ? (
                <tr className="grp"><td colSpan={cols.length}>
                  {show(spec.groupBy === "entity" || spec.groupBy === "portco" ? "x" : spec.groupBy, g.key === "(none)" ? "(none)" : g.key)}
                  <span className="muted"> · {g.rows.length} on this page{groupCounts.has(g.key) ? ` of ${groupCounts.get(g.key)!.toLocaleString()} matched` : ""}</span>
                </td></tr>
              ) : null}
              {g.rows.map((r) => (
                <tr key={`${g.key}:${r.file_id}`} onClick={() => setOpen(r)} className={open?.file_id === r.file_id ? "sel" : ""}>
                  {cols.map((c) => (
                    <td key={c} className={c === "name" ? "name" : ""}>
                      {c === "tier" && r.tier === "restricted" ? <span className="badge restricted">Restricted</span> : show(c, (r as unknown as Record<string, unknown>)[c])}
                      {r.changed.includes(c) ? <span className="chg" title={`Catalog DB: ${show(c, r.catalog[c]) || "(empty)"}`}>changed in Drive</span> : null}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          ))}
        </table>

        {res && res.total > res.pageSize ? (
          <div className="pager">
            <button className="btn" disabled={res.page === 0} onClick={() => setSpec((s) => ({ ...s, page: s.page - 1 }))}>‹ Prev</button>
            <span>page {res.page + 1} of {Math.ceil(res.total / res.pageSize).toLocaleString()}</span>
            <button className="btn" disabled={to >= res.total} onClick={() => setSpec((s) => ({ ...s, page: s.page + 1 }))}>Next ›</button>
          </div>
        ) : null}
      </section>

      {open ? <SidePanel row={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}
