"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./client";
import { emit, EV, on, onFindPage, type ViewRef } from "./bus";
import { Icon } from "./icons";

type Folder = { folder_id: number; name: string; parent_id: number | null; sort: number };
type View = ViewRef & { is_seed: boolean; folder_id: number | null; pinned: boolean; sort: number };
/** where: "p" = the PINNED copy of a view, "t" = its place in the tree (a pinned view is drawn twice) */
type Menu = { kind: "view" | "folder"; id: number; where: "p" | "t"; top: number; left: number } | null;
type Editing = { kind: "view" | "folder" | "new-folder"; id: number | null; parent?: number | null } | null;

const OPEN_KEY = "catalog.tree.open";
const MENU_W = 200;

/**
 * Closes a popover on an outside mousedown or Escape. A mousedown on the popover's own trigger is NOT outside
 * (coder review #2): otherwise the mousedown closes it and the click that follows opens it again.
 * The trigger is `trigger`, or else the popover's parent `.pop-wrap`.
 */
export function useOutside(ref: React.RefObject<HTMLElement | null>, onOut: () => void, active: boolean, trigger?: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!active) return;
    const h = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!ref.current || ref.current.contains(t)) return;
      const wrap = trigger?.current ?? ref.current.parentElement?.closest(".pop-wrap");
      if (wrap && wrap.contains(t)) return;
      onOut();
    };
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onOut(); };
    document.addEventListener("mousedown", h);
    document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); };
  }, [ref, onOut, active, trigger]);
}

/** Opens a popover at a trigger, in fixed position (so a scrolling container can't clip it). */
export function anchorAt(el: HTMLElement, width = MENU_W): { top: number; left: number } {
  const r = el.getBoundingClientRect();
  return { top: Math.min(r.bottom + 4, window.innerHeight - 120), left: Math.max(8, Math.min(r.left, window.innerWidth - width - 8)) };
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
  const triggerRef = useRef<HTMLElement | null>(null);
  const closeMenu = useCallback(() => { setMenu(null); setMoveOpen(false); triggerRef.current?.focus(); }, []);
  const editDone = useRef(false);
  useOutside(menuRef, closeMenu, !!menu, triggerRef);

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
    const c = () => setMenu(null);
    window.addEventListener("resize", c);
    return () => { a(); b(); window.removeEventListener("resize", c); };
  }, [load]);
  // focus the first action when a menu opens (keyboard users land inside it)
  useEffect(() => { if (menu) menuRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus(); }, [menu]);

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
    try { await fn(); await load(); emit(EV.treeChanged); } catch (e) { setMsg(errText(e)); }
    setMenu(null); setMoveOpen(false);
  };
  const patchView = (id: number, body: Record<string, unknown>) => call(() => api("/api/views", { method: "PATCH", body: JSON.stringify({ view_id: id, ...body }) }));
  const delView = (id: number) => call(() => api(`/api/views?id=${id}`, { method: "DELETE" }));
  const delFolder = (id: number) => call(() => api(`/api/folders?id=${id}`, { method: "DELETE" }));
  const startEdit = (e: Editing, name: string) => { editDone.current = false; setDraft(name); setEditing(e); };
  const cancelEdit = () => { editDone.current = true; setEditing(null); };
  /** Enter and blur both land here; commit once (coder review #3). */
  const commitEdit = async () => {
    if (editDone.current) return;
    editDone.current = true;
    const name = draft.trim();
    const e = editing;
    setEditing(null);
    if (!e || !name) return;
    if (e.kind === "new-folder") await call(() => api("/api/folders", { method: "POST", body: JSON.stringify({ name, parent_id: e.parent ?? null }) }));
    else if (e.kind === "folder") await call(() => api("/api/folders", { method: "PATCH", body: JSON.stringify({ folder_id: e.id, name }) }));
    else await patchView(e.id!, { name });
  };
  const openMenu = (kind: "view" | "folder", id: number, where: "p" | "t", el: HTMLElement) => {
    if (menu && menu.kind === kind && menu.id === id && menu.where === where) { setMenu(null); return; }
    triggerRef.current = el;
    setMoveOpen(false);
    setMenu({ kind, id, where, ...anchorAt(el) });
  };
  const isMenu = (kind: "view" | "folder", id: number, where: "p" | "t") => !!menu && menu.kind === kind && menu.id === id && menu.where === where;

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
      onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); }}
      aria-label="Name" />
  );
  const moreBtn = (kind: "view" | "folder", id: number, where: "p" | "t", label: string) => (
    <button className="icon-btn more" aria-label={label} aria-haspopup="true" aria-expanded={isMenu(kind, id, where)}
      onClick={(e) => { e.stopPropagation(); openMenu(kind, id, where, e.currentTarget); }}>
      <Icon name="more" />
    </button>
  );

  const viewRow = (v: View, where: "p" | "t") => (
    <div key={where + v.view_id} className={`tree-row${current === v.view_id ? " on" : ""}`} draggable={!editing}
      onDragStart={(e) => { e.dataTransfer.setData("text/x-catalog-view", String(v.view_id)); e.dataTransfer.effectAllowed = "move"; }}>
      {editing?.kind === "view" && editing.id === v.view_id && where === "t" ? <><Icon name="view" />{editor}</> : (
        <button className="nm" onClick={() => apply(v)} title={v.name} aria-current={current === v.view_id ? "true" : undefined}>
          <Icon name="view" /><span>{v.name}</span>
        </button>
      )}
      {v.pinned && where === "t" ? <span className="pin" title="Pinned" aria-label="Pinned"><Icon name="pin" /></span> : null}
      {moreBtn("view", v.view_id, where, `Actions for view ${v.name}`)}
    </div>
  );

  const folderBlock = (f: Folder, depth: number) => {
    const isOpen = open[f.folder_id] ?? true;
    const empty = viewCount(f.folder_id) === 0 && kids(f.folder_id).length === 0;
    return (
      <div key={f.folder_id}>
        <div className={`tree-row${dropOn === `f${f.folder_id}` ? " drop" : ""}`} {...dropProps(`f${f.folder_id}`, f.folder_id)}>
          {editing?.kind === "folder" && editing.id === f.folder_id ? <><Icon name="folder" />{editor}</> : (
            <button className="nm" onClick={() => toggle(f.folder_id)} aria-expanded={isOpen}>
              <Icon name={isOpen ? "chevDown" : "chevRight"} /><Icon name={isOpen ? "folderOpen" : "folder"} /><span>{f.name}</span>
            </button>
          )}
          {moreBtn("folder", f.folder_id, "t", `Actions for folder ${f.name}`)}
        </div>
        {isOpen ? (
          <div className="tree-children">
            {kids(f.folder_id).map((k) => folderBlock(k, depth + 1))}
            {editing?.kind === "new-folder" && editing.parent === f.folder_id ? <div className="tree-row"><Icon name="folder" />{editor}</div> : null}
            {inFolder(f.folder_id).map((v) => viewRow(v, "t"))}
            {empty && !(editing?.kind === "new-folder" && editing.parent === f.folder_id) ? <div className="tree-empty">Empty. Drag a view here.</div> : null}
          </div>
        ) : null}
      </div>
    );
  };

  // ---------------------------------------------------------------- the open menu (one at a time, fixed position)
  const mv = menu?.kind === "view" ? views.find((v) => v.view_id === menu.id) : undefined;
  const mf = menu?.kind === "folder" ? folders.find((f) => f.folder_id === menu.id) : undefined;
  const mfEmpty = mf ? viewCount(mf.folder_id) === 0 && kids(mf.folder_id).length === 0 : false;
  const menuEl = menu ? (
    <div ref={menuRef} className="menu fixed" style={{ top: menu.top, left: menu.left, minWidth: MENU_W }}
      onKeyDown={(e) => {
        if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
        e.preventDefault();
        const items = [...(menuRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
        const i = items.indexOf(document.activeElement as HTMLButtonElement);
        items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
      }}>
      {mv ? (
        <>
          <button onClick={() => patchView(mv.view_id, { pinned: !mv.pinned })}>{mv.pinned ? "Unpin" : "Pin"}</button>
          <button aria-expanded={moveOpen} onClick={() => setMoveOpen((m) => !m)}>Move to… <Icon name={moveOpen ? "chevDown" : "chevRight"} className="small" /></button>
          {moveOpen ? (
            <div className="submenu">
              <button disabled={mv.folder_id == null} onClick={() => patchView(mv.view_id, { folder_id: null })}>Top level</button>
              {top.map((f) => (
                <div key={f.folder_id}>
                  <button disabled={mv.folder_id === f.folder_id} onClick={() => patchView(mv.view_id, { folder_id: f.folder_id })}>{f.name}</button>
                  {kids(f.folder_id).map((k) => (
                    <button key={k.folder_id} className="indent" disabled={mv.folder_id === k.folder_id} onClick={() => patchView(mv.view_id, { folder_id: k.folder_id })}>{k.name}</button>
                  ))}
                </div>
              ))}
            </div>
          ) : null}
          <button onClick={() => { setMenu(null); startEdit({ kind: "view", id: mv.view_id }, mv.name); }}>Rename</button>
          <div className="sep" />
          <button className="danger" onClick={() => delView(mv.view_id)}>Delete view</button>
        </>
      ) : mf ? (
        <>
          {mf.parent_id == null ? <button onClick={() => { setMenu(null); setOpen((o) => ({ ...o, [mf.folder_id]: true })); startEdit({ kind: "new-folder", id: null, parent: mf.folder_id }, ""); }}>New sub-folder</button> : null}
          <button onClick={() => { setMenu(null); startEdit({ kind: "folder", id: mf.folder_id }, mf.name); }}>Rename</button>
          <div className="sep" />
          <button className="danger" disabled={!mfEmpty} onClick={() => delFolder(mf.folder_id)}>Delete folder</button>
          {!mfEmpty ? <div className="hint">Only an empty folder can be deleted. Move its views out first.</div> : null}
        </>
      ) : null}
    </div>
  ) : null;

  return (
    <div className="tree" aria-label="Saved views">
      <div className={`tree-head${dropOn === "top" ? " drop" : ""}`} {...dropProps("top", null)}>
        <span className="cap">Saved views</span>
        <button className="icon-btn" title="New folder" aria-label="New folder" onClick={() => startEdit({ kind: "new-folder", id: null, parent: null }, "")}>
          <Icon name="plus" />
        </button>
      </div>
      {msg ? <div className="tree-msg" role="alert">{msg}</div> : null}
      {pinned.length ? (
        <>
          <div className="tree-group">Pinned</div>
          {pinned.map((v) => viewRow(v, "p"))}
          <div className="tree-group" style={{ marginTop: 6 }}>All views</div>
        </>
      ) : null}
      {top.map((f) => folderBlock(f, 0))}
      {editing?.kind === "new-folder" && editing.parent == null ? <div className="tree-row"><Icon name="folder" />{editor}</div> : null}
      {inFolder(null).map((v) => viewRow(v, "t"))}
      {!views.length && !folders.length ? <div className="tree-empty">No saved views yet.</div> : null}
      {menuEl}
    </div>
  );
}
