"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./client";
import { emit, EV, on, onFindPage, type ViewRef } from "./bus";
import { Icon } from "./icons";

type Folder = { folder_id: number; name: string; parent_id: number | null; sort: number };
type View = ViewRef & { is_seed: boolean; folder_id: number | null; pinned: boolean; sort: number };
type Menu = { kind: "view" | "folder"; id: number } | null;
type Editing = { kind: "view" | "folder" | "new-folder"; id: number | null; parent?: number | null } | null;

const OPEN_KEY = "catalog.tree.open";

export function useOutside(ref: React.RefObject<HTMLElement | null>, onOut: () => void, active: boolean) {
  useEffect(() => {
    if (!active) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onOut(); };
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onOut(); };
    document.addEventListener("mousedown", h);
    document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); };
  }, [ref, onOut, active]);
}

function errText(e: unknown): string {
  const b = (e as { body?: { error?: string } }).body;
  const code = b?.error ?? (e as Error).message;
  return ({ folder_not_empty: "Move its views and sub-folders out first.", name_taken: "That name is already used here.", too_deep: "Folders nest two levels at most.", bad_name: "Give it a name (up to 60 characters)." } as Record<string, string>)[code] ?? code;
}

export function ViewTree() {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [views, setViews] = useState<View[]>([]);
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [menu, setMenu] = useState<Menu>(null);
  const [moveOpen, setMoveOpen] = useState(false);
  const [editing, setEditing] = useState<Editing>(null);
  const [draft, setDraft] = useState("");
  const [dropOn, setDropOn] = useState<string | null>(null);
  const [current, setCurrent] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  useOutside(menuRef, () => { setMenu(null); setMoveOpen(false); }, !!menu);

  const load = useCallback(async () => {
    try {
      const r = await api<{ folders: Folder[]; views: View[] }>("/api/views");
      setFolders(r.folders); setViews(r.views);
    } catch (e) { setMsg(errText(e)); }
  }, []);
  useEffect(() => {
    load();
    try { setOpen(JSON.parse(localStorage.getItem(OPEN_KEY) ?? "{}")); } catch { /* ignore */ }
    const a = on(EV.viewsChanged, () => load());
    const b = on<{ viewId: number | null }>(EV.currentView, (d) => setCurrent(d?.viewId ?? null));
    return () => { a(); b(); };
  }, [load]);
  const toggle = (id: number) => setOpen((o) => {
    const n = { ...o, [id]: !(o[id] ?? true) };
    try { localStorage.setItem(OPEN_KEY, JSON.stringify(n)); } catch { /* ignore */ }
    return n;
  });

  const apply = (v: View) => {
    if (onFindPage()) emit<ViewRef>(EV.applyView, { view_id: v.view_id, name: v.name, spec: v.spec });
    else window.location.href = `/?view=${v.view_id}`;
  };
  const call = async (fn: () => Promise<unknown>) => {
    setMsg(null);
    try { await fn(); await load(); emit(EV.viewsChanged + ":local"); } catch (e) { setMsg(errText(e)); }
    setMenu(null); setMoveOpen(false);
  };
  const patchView = (id: number, body: Record<string, unknown>) => call(() => api("/api/views", { method: "PATCH", body: JSON.stringify({ view_id: id, ...body }) }));
  const delView = (id: number) => call(() => api(`/api/views?id=${id}`, { method: "DELETE" }));
  const delFolder = (id: number) => call(() => api(`/api/folders?id=${id}`, { method: "DELETE" }));
  const commitEdit = async () => {
    const name = draft.trim();
    const e = editing;
    setEditing(null);
    if (!e || !name) return;
    if (e.kind === "new-folder") await call(() => api("/api/folders", { method: "POST", body: JSON.stringify({ name, parent_id: e.parent ?? null }) }));
    else if (e.kind === "folder") await call(() => api("/api/folders", { method: "PATCH", body: JSON.stringify({ folder_id: e.id, name }) }));
    else await patchView(e.id!, { name });
  };

  const top = useMemo(() => folders.filter((f) => f.parent_id == null), [folders]);
  const kids = (id: number) => folders.filter((f) => f.parent_id === id);
  const inFolder = (id: number | null) => views.filter((v) => v.folder_id === id);
  const pinned = views.filter((v) => v.pinned);
  const viewCount = (id: number): number => inFolder(id).length + kids(id).reduce((n, k) => n + viewCount(k.folder_id), 0);

  const dropProps = (key: string, folderId: number | null) => ({
    onDragOver: (e: React.DragEvent) => { if (e.dataTransfer.types.includes("text/x-catalog-view")) { e.preventDefault(); setDropOn(key); } },
    onDragLeave: () => setDropOn((k) => (k === key ? null : k)),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault(); setDropOn(null);
      const id = Number(e.dataTransfer.getData("text/x-catalog-view"));
      const v = views.find((x) => x.view_id === id);
      if (v && v.folder_id !== folderId) patchView(id, { folder_id: folderId });
    },
  });

  const editor = (
    <input className="tree-input" autoFocus value={draft} maxLength={editing?.kind === "view" ? 80 : 60}
      onChange={(e) => setDraft(e.target.value)} onBlur={commitEdit}
      onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") setEditing(null); }}
      aria-label="Name" />
  );

  const viewRow = (v: View, keyPrefix = "") => (
    <div key={keyPrefix + v.view_id} className={`tree-row${current === v.view_id ? " on" : ""}`} draggable={!editing}
      onDragStart={(e) => { e.dataTransfer.setData("text/x-catalog-view", String(v.view_id)); e.dataTransfer.effectAllowed = "move"; }}
      onClick={() => apply(v)} title={v.name}>
      <Icon name="view" />
      {editing?.kind === "view" && editing.id === v.view_id && !keyPrefix ? editor : <span className="nm">{v.name}</span>}
      {v.pinned && !keyPrefix ? <span className="pin" title="Pinned"><Icon name="pin" /></span> : null}
      <div className="pop-wrap" ref={menu?.kind === "view" && menu.id === v.view_id ? menuRef : undefined} onClick={(e) => e.stopPropagation()}>
        <button className="icon-btn more" aria-label={`Actions for ${v.name}`} aria-expanded={menu?.kind === "view" && menu.id === v.view_id}
          onClick={() => { setMoveOpen(false); setMenu(menu?.kind === "view" && menu.id === v.view_id ? null : { kind: "view", id: v.view_id }); }}>
          <Icon name="more" />
        </button>
        {menu?.kind === "view" && menu.id === v.view_id ? (
          <div className="menu left" role="menu">
            <button role="menuitem" onClick={() => patchView(v.view_id, { pinned: !v.pinned })}>{v.pinned ? "Unpin" : "Pin"}</button>
            <button role="menuitem" onClick={() => setMoveOpen((m) => !m)}>Move to…</button>
            {moveOpen ? (
              <div style={{ paddingLeft: 12 }}>
                <button role="menuitem" disabled={v.folder_id == null} onClick={() => patchView(v.view_id, { folder_id: null })}>Top level</button>
                {top.map((f) => (
                  <div key={f.folder_id}>
                    <button role="menuitem" disabled={v.folder_id === f.folder_id} onClick={() => patchView(v.view_id, { folder_id: f.folder_id })}>{f.name}</button>
                    {kids(f.folder_id).map((k) => (
                      <button key={k.folder_id} role="menuitem" style={{ paddingLeft: 28 }} disabled={v.folder_id === k.folder_id} onClick={() => patchView(v.view_id, { folder_id: k.folder_id })}>{k.name}</button>
                    ))}
                  </div>
                ))}
              </div>
            ) : null}
            <button role="menuitem" onClick={() => { setMenu(null); setDraft(v.name); setEditing({ kind: "view", id: v.view_id }); }}>Rename</button>
            <div className="sep" />
            <button role="menuitem" className="danger" onClick={() => delView(v.view_id)}>Delete view</button>
          </div>
        ) : null}
      </div>
    </div>
  );

  const folderBlock = (f: Folder, depth: number) => {
    const isOpen = open[f.folder_id] ?? true;
    const n = viewCount(f.folder_id);
    const empty = n === 0 && kids(f.folder_id).length === 0;
    return (
      <div key={f.folder_id}>
        <div className={`tree-row${dropOn === `f${f.folder_id}` ? " drop" : ""}`} onClick={() => toggle(f.folder_id)} {...dropProps(`f${f.folder_id}`, f.folder_id)}>
          <Icon name={isOpen ? "chevDown" : "chevRight"} />
          <Icon name={isOpen ? "folderOpen" : "folder"} />
          {editing?.kind === "folder" && editing.id === f.folder_id ? editor : <span className="nm">{f.name}</span>}
          <div className="pop-wrap" ref={menu?.kind === "folder" && menu.id === f.folder_id ? menuRef : undefined} onClick={(e) => e.stopPropagation()}>
            <button className="icon-btn more" aria-label={`Actions for folder ${f.name}`} aria-expanded={menu?.kind === "folder" && menu.id === f.folder_id}
              onClick={() => setMenu(menu?.kind === "folder" && menu.id === f.folder_id ? null : { kind: "folder", id: f.folder_id })}>
              <Icon name="more" />
            </button>
            {menu?.kind === "folder" && menu.id === f.folder_id ? (
              <div className="menu left" role="menu">
                {depth === 0 ? <button role="menuitem" onClick={() => { setMenu(null); setOpen((o) => ({ ...o, [f.folder_id]: true })); setDraft(""); setEditing({ kind: "new-folder", id: null, parent: f.folder_id }); }}>New sub-folder</button> : null}
                <button role="menuitem" onClick={() => { setMenu(null); setDraft(f.name); setEditing({ kind: "folder", id: f.folder_id }); }}>Rename</button>
                <div className="sep" />
                <button role="menuitem" className="danger" disabled={!empty} onClick={() => delFolder(f.folder_id)}>Delete folder</button>
                {!empty ? <div className="hint">Only an empty folder can be deleted. Move its views out first.</div> : null}
              </div>
            ) : null}
          </div>
        </div>
        {isOpen ? (
          <div className="tree-children">
            {kids(f.folder_id).map((k) => folderBlock(k, depth + 1))}
            {editing?.kind === "new-folder" && editing.parent === f.folder_id ? <div className="tree-row"><Icon name="folder" />{editor}</div> : null}
            {inFolder(f.folder_id).map((v) => viewRow(v))}
            {empty && !(editing?.kind === "new-folder" && editing.parent === f.folder_id) ? <div className="tree-empty">Empty. Drag a view here.</div> : null}
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="tree" aria-label="Saved views">
      <div className={`tree-head${dropOn === "top" ? " drop" : ""}`} {...dropProps("top", null)}>
        <span className="cap">Saved views</span>
        <button className="icon-btn" title="New folder" aria-label="New folder" onClick={() => { setDraft(""); setEditing({ kind: "new-folder", id: null, parent: null }); }}>
          <Icon name="plus" />
        </button>
      </div>
      {msg ? <div className="tree-empty" role="alert" style={{ color: "#f0a59c", fontStyle: "normal" }}>{msg}</div> : null}
      {pinned.length ? (
        <>
          <div className="tree-group">Pinned</div>
          {pinned.map((v) => viewRow(v, "p"))}
          <div className="tree-group" style={{ marginTop: 6 }}>All views</div>
        </>
      ) : null}
      {top.map((f) => folderBlock(f, 0))}
      {editing?.kind === "new-folder" && editing.parent == null ? <div className="tree-row"><Icon name="folder" />{editor}</div> : null}
      {inFolder(null).map((v) => viewRow(v))}
      {!views.length && !folders.length ? <div className="tree-empty">No saved views yet.</div> : null}
    </div>
  );
}
