import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  chipsOf, clearAll, DEFAULT_LAYOUT, EMPTY, fingerprint, headerSearch, isEdited, openView, restoredText, revert, setFilter, setText,
  storedNow, TEXT_KEY, titleOf, wire, type Spec,
} from "@/lib/findstate";
import { storedSpec } from "@/lib/views";
import { parseSpec } from "@/lib/find";

const src = (f: string) => readFileSync(join(__dirname, "..", "src", ...f.split("/")), "utf8");

/** A saved view like Ryan's "2025 K-1s": Kind = K-1, FY 2025, primary only, grouped by entity, custom columns. */
const K1_VIEW: Record<string, unknown> = {
  filters: { kind: ["k1"], fiscal_year: ["2025"], primary_only: true }, sort: { col: "modified_time", dir: "desc" }, groupBy: "entity", pageSize: 25,
  columns: ["name", "kind", "entities", "fiscal_year"], widths: {},
};
const opened = () => {
  const c = openView(7, "2025 K-1s", K1_VIEW);
  const r = revert(c);
  return { c, spec: r.spec, layout: r.layout };
};

describe("CAT-WO-12 · header search starts fresh", () => {
  it("clears every filter, column filter, sort and grouping; only the term remains", () => {
    const { spec } = opened();
    const withCol = setFilter(setFilter(spec, "signed_date", { from: "2025-01-01" }), "file_id", "1ab");
    const s = headerSearch({ ...withCol, page: 4 }, "  night dragon w-9 ");
    expect(s.filters).toEqual({});
    expect(s.search).toBe("night dragon w-9");
    expect(s.sort).toEqual(EMPTY.sort);
    expect(s.groupBy).toBeNull();
    expect(s.page).toBe(0);
    expect(s.pageSize).toBe(25); // page size is not a filter
  });
  it("leaves the saved view: the title becomes Search results", () => {
    const s = headerSearch(opened().spec, "w-9");
    expect(titleOf(null, false, s)).toEqual({ name: "Search results", edited: false });
    expect(titleOf(null, false, EMPTY)).toEqual({ name: "Find", edited: false });
  });
  it("the shell empties the header box, drops the current view and sends other pages to /?q= (a fresh search)", () => {
    const shell = src("components/AppShell.tsx");
    expect(shell).toMatch(/setQ\(""\)/);
    expect(shell).not.toMatch(/get\("q"\)/); // the box no longer refills from the address
    const find = src("components/FindClient.tsx");
    expect(find).toMatch(/on<\{ q: string \}>\(EV\.search, \(d\) => \{ userActed\.current = true; startFresh\(d\.q\); \}\)/);
    expect(find).toMatch(/const startFresh = [\s\S]*?setCurrent\(null\)[\s\S]*?emit\(EV\.currentView, \{ viewId: null \}\)/);
    expect(find).toMatch(/if \(q != null && q\.trim\(\)\) \{ startFresh\(q\); return; \}/);
  });
});

describe("CAT-WO-12 · in-window search keeps the filters", () => {
  it("adds the term to a Kind filter without touching it, and resets to page 1", () => {
    const s0 = setFilter(EMPTY, "kind", ["w9"]);
    const s1 = setText({ ...s0, page: 3 }, "night dragon");
    expect(s1.filters).toEqual({ kind: ["w9"] });
    expect(s1.search).toBe("night dragon");
    expect(s1.page).toBe(0);
    expect(setText(s1, "night dragon ")).toBe(s1);  // same term: nothing changes, no refetch
    expect(setText(s1, "").search).toBeUndefined();
  });
  it("the term goes to the server and the export like any other filter", () => {
    const s = setText(setFilter(EMPTY, "kind", ["w9"]), "dragon");
    expect(wire(s)).toMatchObject({ filters: { kind: ["w9"] }, search: "dragon" });
    expect(parseSpec(wire(s)).search).toBe("dragon");
    expect(src("components/FindClient.tsx")).toMatch(/\/api\/export\?format=\$\{format\}`, \{ method: "POST"[^)]*JSON\.stringify\(wire\(spec\)\)/);
  });
  it("the field debounces ~300 ms, commits on Enter, clears on Esc and shows × when non-empty", () => {
    const f = src("components/FindClient.tsx");
    expect(f).toMatch(/export const TEXT_DEBOUNCE = 300;/);
    expect(f).toMatch(/e\.key === "Enter"\) \{ e\.preventDefault\(\); commit\(v\); \}/);
    expect(f).toMatch(/e\.key === "Escape"\) \{ e\.preventDefault\(\); setV\(""\); commit\(""\); \}/);
    expect(f).toMatch(/\{v \? <button className="clear"/);
    expect(f).toMatch(/<TextSearchField value=\{spec\.search \?\? ""\} onChange=\{setTerm\}/);
    // the Filters panel lists Text and takes you to the field
    expect(f).toMatch(/<span className="cap">Text<\/span>\s*<button className="trigger" onClick=\{focusText\}/);
  });
  it("the old Search: \"…\" clear line under the title is gone", () => {
    expect(src("components/FindClient.tsx")).not.toMatch(/Search: “\{spec\.search\}”/);
  });
});

describe("CAT-WO-12 · TEXT chip", () => {
  it("is a chip, first, and counts in N filters", () => {
    const s = setText(setFilter(EMPTY, "kind", ["w9"]), "night dragon w-9");
    const c = chipsOf(s);
    expect(c.map((x) => x.key)).toEqual([TEXT_KEY, "kind"]);
    expect(c[0]).toEqual({ key: TEXT_KEY, label: "Text", text: "night dragon w-9" });
    expect(c.length).toBe(2);
  });
  it("× removes only the term; Clear all removes the term and every filter", () => {
    const s = setText(setFilter(EMPTY, "kind", ["w9"]), "dragon");
    const x = setFilter(s, TEXT_KEY, undefined);
    expect(x.search).toBeUndefined();
    expect(x.filters).toEqual({ kind: ["w9"] });
    const all = clearAll(s);
    expect(all.search).toBeUndefined();
    expect(all.filters).toEqual({});
    expect(chipsOf(all)).toEqual([]);
  });
});

describe("CAT-WO-12 · saved views keep their text", () => {
  it("a view with a term round-trips through storage and reopens with chip and field", () => {
    const { spec, layout } = opened();
    const withQ = setText(spec, "night dragon");
    const stored = storedSpec(storedNow(withQ, layout));         // what POST/PATCH /api/views writes
    expect(stored.search).toBe("night dragon");
    const back = revert(openView(9, "K-1s dragon", JSON.parse(JSON.stringify(stored))));
    expect(back.spec.search).toBe("night dragon");
    expect(back.spec.filters).toEqual(K1_VIEW.filters);
    expect(chipsOf(back.spec)[0].key).toBe(TEXT_KEY);
  });
  it("a view without a term stores none (old views unchanged)", () => {
    expect("search" in storedSpec(K1_VIEW)).toBe(false);
    expect(fingerprint(K1_VIEW)).toBe(fingerprint(storedSpec(K1_VIEW)));
  });
  it("the last-state pref still never stores the text term", () => {
    expect(src("components/FindClient.tsx")).toMatch(/const \{ search: _s, \.\.\.rest \} = wire\(spec\);/);
    expect(src("app/api/prefs/route.ts")).toMatch(/const \{ search: _search, \.\.\.rest \} = parseSpec/);
  });
  it("on return, Find takes this tab's term, else the open view's", () => {
    expect(restoredText(null, { search: "dragon" })).toBe("dragon");
    expect(restoredText("", { search: "dragon" })).toBeUndefined(); // cleared in this tab
    expect(restoredText("w-9", { search: "dragon" })).toBe("w-9");
    expect(restoredText(null, null)).toBeUndefined();
  });
});

describe("CAT-WO-12 · edited saved view and Revert", () => {
  it("opening a view shows its name, not edited", () => {
    const { c, spec, layout } = opened();
    expect(isEdited(c, spec, layout)).toBe(false);
    expect(titleOf(c, false, spec)).toEqual({ name: "2025 K-1s", edited: false });
  });
  it("text, filters, columns or sort each mark it edited, name kept", () => {
    const { c, spec, layout } = opened();
    expect(isEdited(c, setText(spec, "dragon"), layout)).toBe(true);
    expect(isEdited(c, setFilter(spec, "entity", ["MTV-II"]), layout)).toBe(true);
    expect(isEdited(c, spec, { ...layout, columns: [...layout.columns, "stage"] })).toBe(true);
    expect(isEdited(c, { ...spec, sort: { col: "signed_date", dir: "asc" } }, layout)).toBe(true);
    expect(isEdited(c, { ...spec, page: 3 }, layout)).toBe(false); // paging is not an edit
    expect(titleOf(c, true, spec)).toEqual({ name: "2025 K-1s", edited: true });
  });
  it("Revert restores the stored filters, text and layout", () => {
    const { c, layout } = opened();
    const withQ = openView(7, "2025 K-1s", { ...K1_VIEW, search: "dragon" });
    const edited: Spec = clearAll(revert(withQ).spec);
    expect(isEdited(withQ, edited, layout)).toBe(true);
    const r = revert(withQ);
    expect(isEdited(withQ, r.spec, r.layout)).toBe(false);
    expect(r.spec.search).toBe("dragon");
    expect(revert(c).layout.columns).toEqual(K1_VIEW.columns);
    expect(revert(openView(1, "x", { filters: {} })).layout).toEqual(DEFAULT_LAYOUT);
  });
  it("the page shows Update view / Save as new view / Revert when edited, and \"· edited\" after the name", () => {
    const f = src("components/FindClient.tsx");
    expect(f).toMatch(/current && dirty \? <button className="btn" onClick=\{updateView\}>Update view<\/button>/);
    expect(f).toMatch(/current && dirty \? <button className="btn" onClick=\{revertView\}>Revert<\/button>/);
    expect(f).toMatch(/"Save as new view" : "Save view"/);
    expect(f).toMatch(/<span className="edited"> · edited<\/span>/);
    expect(f).not.toMatch(/Saved view\{dirty \? " · changed"/);
  });
});
