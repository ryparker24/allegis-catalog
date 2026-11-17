"use client";
/**
 * Tiny window-event bus between the shell (rail, top bar) and the Find page. On any other page the shell
 * navigates to Find with the request in the URL instead (/?view=ID, /?q=...).
 */
export type ViewRef = { view_id: number; name: string; spec: Record<string, unknown> };
export const EV = {
  applyView: "catalog:apply-view",     // detail: ViewRef
  search: "catalog:search",            // detail: { q: string }
  viewsChanged: "catalog:views-changed",
  currentView: "catalog:current-view", // detail: { viewId: number | null }
  findReady: "catalog:find-ready",
} as const;

export function emit<T>(name: string, detail?: T) {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}
export function on<T>(name: string, fn: (d: T) => void): () => void {
  const h = (e: Event) => fn((e as CustomEvent<T>).detail);
  window.addEventListener(name, h);
  return () => window.removeEventListener(name, h);
}
export function onFindPage(): boolean {
  return typeof document !== "undefined" && !!document.querySelector("[data-find-page]");
}

/** Screenshot mode for proofs (?mask=1): file names are replaced by a masked stand-in. Display only. */
export function maskNames(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get("mask") === "1") sessionStorage.setItem("catalog.mask", "1");
    return sessionStorage.getItem("catalog.mask") === "1";
  } catch { return false; }
}
export function shownName(name: string, fileId: string): string {
  return maskNames() ? `File ••••${fileId.slice(-4)}` : name;
}
