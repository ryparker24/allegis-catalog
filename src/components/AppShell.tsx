"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "./client";
import { emit, EV, onFindPage } from "./bus";
import { Emblem, Icon } from "./icons";
import { LabelsPanel } from "./LabelsPanel";
import { useOutside, ViewTree } from "./ViewTree";

const COLLAPSE_KEY = "catalog.sidebarCollapsed";

/** Item 1: Datum-style shell. Dark rail (brand, nav, saved-view tree) + dark top bar (search, Labels, avatar). */
type Nightly = { status: string; failed_step: string | null; started_at: string | null; last_ok_at: string | null };
/** CAT-WO-03.1: a banner when the nightly run failed, or no run succeeded in 36 hours (labels and checklists go stale). */
export function nightlyBanner(n: Nightly | null): React.ReactNode {
  if (!n) return null;
  const lastOk = n.last_ok_at ? new Date(n.last_ok_at.replace(" ", "T")) : null;
  const stale = !lastOk || Date.now() - lastOk.getTime() > 36 * 3600 * 1000;
  if (n.status === "failed")
    return <div className="banner warn" role="status">The nightly catalog run failed at step <b>{n.failed_step ?? "?"}</b> ({String(n.started_at ?? "").slice(0, 16)}). The log is in C:\DriveCatalog\logs on the ThinkPad.</div>;
  if (stale && n.status !== "running")
    return <div className="banner warn" role="status">{lastOk ? <>No successful nightly catalog run since {String(n.last_ok_at).slice(0, 16)}.</> : <>The nightly catalog run has not completed yet.</>} Filters, checklists and labels may be behind Drive.</div>;
  return null;
}

export function AppShell({ email, active, signedIn, children }: { email: string | null; active: "find" | "review" | "checklists"; signedIn: boolean; children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [labelsOpen, setLabelsOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState<number | null>(null);
  const [nightly, setNightly] = useState<Nightly | null>(null);
  const [q, setQ] = useState("");
  const [userMenu, setUserMenu] = useState(false);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const labelsBtn = useRef<HTMLButtonElement | null>(null);
  const userRef = useRef<HTMLDivElement | null>(null);
  useOutside(userRef, () => setUserMenu(false), userMenu);

  useEffect(() => {
    try { setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1"); } catch { /* ignore */ }
    try { setQ(new URLSearchParams(window.location.search).get("q") ?? ""); } catch { /* ignore */ }
    if (signedIn) api<{ reviewOpen: number; nightly?: Nightly | null }>("/api/nav").then((r) => { setReviewOpen(r.reviewOpen); setNightly(r.nightly ?? null); }).catch(() => {});
    const k = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); searchRef.current?.focus(); searchRef.current?.select(); }
    };
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, [signedIn]);

  const toggleRail = () => setCollapsed((c) => {
    try { localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1"); } catch { /* ignore */ }
    return !c;
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const term = q.trim();
    if (onFindPage()) emit(EV.search, { q: term });
    else window.location.href = term ? `/?q=${encodeURIComponent(term)}` : "/";
  };
  const initials = (email ?? "?").split("@")[0].split(/[._-]/).filter(Boolean).map((s) => s[0]!.toUpperCase()).slice(0, 2).join("") || "?";

  return (
    <div className={`app${collapsed ? " collapsed" : ""}`}>
      <aside className="rail" aria-label="Navigation">
        <div className="brand">
          <Emblem />
          <div className="word-wrap">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="wordmark" src="/allegis-wordmark.svg" alt="Allegis Capital" />
            <div className="sub">Catalog</div>
          </div>
          <button className="icon-btn collapse" onClick={toggleRail} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand" : "Collapse"}>
            <Icon name={collapsed ? "panelOpen" : "panelClose"} />
          </button>
        </div>
        <nav className="nav" aria-label="Screens">
          <a href="/" className={`nav-item${active === "find" ? " on" : ""}`} aria-current={active === "find" ? "page" : undefined} title="Find">
            <Icon name="search" /><span className="lbl">Find</span>
          </a>
          <a href="/review" className={`nav-item${active === "review" ? " on" : ""}`} aria-current={active === "review" ? "page" : undefined} title="Review queue">
            <Icon name="inbox" /><span className="lbl">Review queue</span>
            {reviewOpen != null ? <span className="badge-count" aria-label={`${reviewOpen} open`}>{reviewOpen.toLocaleString()}</span> : null}
          </a>
          <a href="/checklists" className={`nav-item${active === "checklists" ? " on" : ""}`} aria-current={active === "checklists" ? "page" : undefined} title="Checklists">
            <Icon name="gaps" /><span className="lbl">Checklists</span>
          </a>
          <a href="/checklists?tab=gaps" className="nav-item" title="Gaps (fund-level checklists, entity x period)">
            <Icon name="gaps" /><span className="lbl">Gaps</span>
          </a>
        </nav>
        {signedIn ? <ViewTree /> : null}
      </aside>

      <div className="workspace">
        <header className="topbar">
          <form className="search" role="search" onSubmit={submit}>
            <Icon name="search" />
            <input ref={searchRef} type="search" value={q} onChange={(e) => setQ(e.target.value)} disabled={!signedIn}
              placeholder="Search names, codes… ( / )" aria-label="Search names, kinds, entity and portco codes" maxLength={100} />
          </form>
          <div className="right">
            <button ref={labelsBtn} className="btn-rail" onClick={() => setLabelsOpen(true)} aria-haspopup="dialog" disabled={!signedIn}>
              <Icon name="tag" /><span className="lbl">Labels</span>
            </button>
            {email ? (
              <div className="pop-wrap" ref={userRef}>
                <button className="avatar" onClick={() => setUserMenu((m) => !m)} aria-label="Account" aria-haspopup="true" aria-expanded={userMenu} title={email}>{initials}</button>
                {userMenu ? (
                  <div className="menu">
                    <div className="hint">{email}</div>
                    <div className="sep" />
                    <form method="post" action="/api/auth/logout"><button>Sign out</button></form>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </header>
        <main className="main">{nightlyBanner(nightly)}{children}</main>
      </div>
      {labelsOpen ? <LabelsPanel onClose={() => { setLabelsOpen(false); labelsBtn.current?.focus(); }} /> : null}
    </div>
  );
}

/** Page header: mono breadcrumb, serif title with an ⓘ chip, actions on the right. */
export function PageHeader({ title, info, actions, desc }: { title: string; info?: React.ReactNode; actions?: React.ReactNode; desc?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement | null>(null);
  useOutside(ref, () => setOpen(false), open);
  return (
    <div className="page-header">
      <div>
        <div className="crumb">Allegis Capital · Catalog</div>
        <div className="title-row">
          <h1 className="page-title">{title}</h1>
          {info ? (
            <span ref={ref} style={{ position: "relative" }}>
              <button className="info-chip" aria-label={`About this page`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>i</button>
              {open ? <span className="info-pop" role="note">{info}</span> : null}
            </span>
          ) : null}
        </div>
        {desc ? <div className="page-desc">{desc}</div> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </div>
  );
}
