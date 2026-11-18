import { describe, expect, it } from "vitest";
import { buildWhere, exportQuery, kindsMatching, orderBy, pageQuery, parseLayout, parseSpec, SEED_FOLDERS, SEED_VIEWS, SpecError } from "@/lib/find";
import { driveNameSearch, driveQueryLiteral, NAME_SEARCH_CAP } from "@/lib/google";
import { crc32, toXlsx } from "@/lib/xlsx";
import { createFolder, deleteFolder, patchFolder, patchView, saveView } from "@/lib/views";
import { buildLabelsPanel } from "@/lib/labelinfo";
import type { Db } from "@/lib/db";
import { COLUMN_DEFS, isSortable } from "@/lib/columns";

describe("item 2 · column filters by type, all server-side and bound", () => {
  it("pick / year / date / text / flag filters become bind parameters", () => {
    const b = buildWhere({ filters: {
      period: ["q4"], workstream: ["tax"], fy_range: { from: 2020, to: 2024 }, signed_date: { from: "2024-01-01", to: "2024-12-31" },
      file_id: "ab_c%", is_primary: "no",
    } });
    expect(b.where).toContain("period = ANY($1::text[])");
    expect(b.where).toContain("fiscal_year >= $3::int");
    expect(b.where).toContain("signed_date < ($6::date + 1)");
    expect(b.where).toContain("is_primary IS NOT TRUE");
    expect(b.where).toContain("file_id ILIKE $7");
    expect(b.params[6]).toBe("%ab\\_c\\%%"); // LIKE wildcards escaped
    expect(b.where).not.toMatch(/2020|2024-01-01|tax/);
  });
  it("refuses unknown filter keys, bad dates, bad years, bad flags", () => {
    expect(() => parseSpec({ filters: { "kind; drop": ["x"] } })).toThrow(SpecError);
    expect(() => parseSpec({ filters: { signed_date: { from: "2024-13-45" } } })).toThrow(SpecError);
    expect(() => parseSpec({ filters: { fy_range: { from: "20x4" } } })).toThrow(SpecError);
    expect(() => parseSpec({ filters: { is_primary: "maybe" } })).toThrow(SpecError);
  });
  it("sorts only on DB columns (live-only columns are not sortable) and pages 10/25/100", () => {
    expect(() => orderBy({ filters: {}, sort: { col: "name", dir: "asc" } })).toThrow(SpecError);
    expect(() => orderBy({ filters: {}, sort: { col: "review_status", dir: "asc" } })).toThrow(SpecError);
    expect(orderBy({ filters: {}, sort: { col: "entities", dir: "asc" } })).toBe("ORDER BY entities ASC NULLS LAST, file_id ASC");
    expect(pageQuery({ filters: {}, pageSize: 10, page: 3 }).sql).toContain("LIMIT 10 OFFSET 30");
    expect(pageQuery({ filters: {}, pageSize: 5000 }).sql).toContain("LIMIT 25 OFFSET 0"); // not an allowed size -> default
    for (const c of COLUMN_DEFS) expect(isSortable(c.key)).toBe(c.source === "db");
  });
  it("layout (widths, order, visibility) is whitelisted and clamped before it is stored", () => {
    expect(parseLayout({ columns: ["kind", "evil", "kind", "name"], widths: { kind: 5, name: 99999, nope: 100 } }))
      .toEqual({ columns: ["kind", "name"], widths: { kind: 60, name: 900 } });
  });
});

describe("item 1 · top-bar search", () => {
  it("codes match by ILIKE, kinds by their plain-words meaning, names only through Drive IDs", () => {
    const b = buildWhere({ filters: {}, search: "k-1" }, { nameIds: ["1AbCdEfGhIjKlMnOpQ", "bad id with spaces"] });
    expect(b.where).toContain("kind ILIKE $1");
    expect(b.where).toContain("unnest(entities)");
    expect(b.params).toContainEqual(["k1"]);                  // "K-1" -> k1
    expect(b.params).toContainEqual(["1AbCdEfGhIjKlMnOpQ"]);  // malformed id dropped
    expect(b.where).not.toMatch(/\bname\b/);                  // no name column, ever
    expect(kindsMatching("schedule")).toEqual([]);
  });
  it("Drive query literal escapes quotes and backslashes", () => {
    expect(driveQueryLiteral(`a'b\\c`)).toBe(`'a\\'b\\\\c'`);
  });
  it("name search asks Drive for IDs only, and caps at 2,000", async () => {
    const urls: string[] = [];
    const f = async (u: string) => {
      urls.push(u);
      const page = urls.length;
      return new Response(JSON.stringify({ files: Array.from({ length: 1000 }, (_, i) => ({ id: `id${page}x${String(i).padStart(8, "0")}` })), nextPageToken: "more" }));
    };
    const r = await driveNameSearch("tok", "K-1 o'x", f);
    expect(r.capped).toBe(true);
    expect(r.ids.length).toBe(NAME_SEARCH_CAP);
    expect(urls.length).toBe(2);
    const q = new URL(urls[0]).searchParams;
    expect(q.get("fields")).toBe("nextPageToken,files(id)");
    expect(q.get("q")).toBe(`name contains 'K-1 o\\'x' and trashed = false`);
  });
  it("search text is validated", () => {
    expect(() => parseSpec({ filters: {}, search: "x".repeat(101) })).toThrow(SpecError);
  });
});

describe("item 1 · Download Excel", () => {
  it("writes a valid zip whose sheet keeps '=' values as inline text, never formulas", () => {
    const bytes = toXlsx(["file_id", "kind"], [["1abc", "=HYPERLINK(\"x\")"], ["2def", "k1 & <b>"]]);
    expect(String.fromCharCode(bytes[0], bytes[1])).toBe("PK");
    // walk the local headers: names + CRCs match
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const names: string[] = [];
    let p = 0;
    let sheet = "";
    while (dv.getUint32(p, true) === 0x04034b50) {
      const crc = dv.getUint32(p + 14, true), size = dv.getUint32(p + 18, true), nlen = dv.getUint16(p + 26, true);
      const name = new TextDecoder().decode(bytes.slice(p + 30, p + 30 + nlen));
      const data = bytes.slice(p + 30 + nlen, p + 30 + nlen + size);
      expect(crc32(data)).toBe(crc);
      names.push(name);
      if (name === "xl/worksheets/sheet1.xml") sheet = new TextDecoder().decode(data);
      p += 30 + nlen + size;
    }
    expect(names).toContain("[Content_Types].xml");
    expect(sheet).toContain('t="inlineStr"><is><t xml:space="preserve">=HYPERLINK(&quot;x&quot;)</t>');
    expect(sheet).not.toContain("<f>");
    expect(sheet).toContain("k1 &amp; &lt;b&gt;");
  });
  it("export has no name column", () => {
    expect(exportQuery({ filters: {} }).sql).not.toMatch(/\bname\b/);
  });
});

/** In-memory stand-in for the catalog_app DB: just enough of view_folder / saved_view for the folder rules. */
function fakeDb() {
  type F = { folder_id: number; owner: string; name: string; parent_id: number | null };
  type V = { view_id: number; owner: string; folder_id: number | null };
  const folders: F[] = [{ folder_id: 1, owner: "a@x", name: "Tax", parent_id: null }, { folder_id: 2, owner: "a@x", name: "Sub", parent_id: 1 }, { folder_id: 9, owner: "b@x", name: "Other", parent_id: null }];
  const views: V[] = [{ view_id: 1, owner: "a@x", folder_id: 2 }, { view_id: 7, owner: "b@x", folder_id: 9 }];
  const sql: string[] = [];
  const D: Db = {
    async rows<T>(text: string, params: unknown[] = []): Promise<T[]> {
      sql.push(text);
      if (/FROM app\.view_folder WHERE folder_id = \$1 AND owner_email = \$2/.test(text)) return folders.filter((f) => f.folder_id === params[0] && f.owner === params[1]) as T[];
      if (/AS views/.test(text)) return [{ views: views.filter((v) => v.folder_id === params[0]).length, subs: folders.filter((f) => f.parent_id === params[0]).length }] as T[];
      if (/INSERT INTO app\.view_folder/.test(text)) return [{ folder_id: 99 }] as T[];
      if (/INSERT INTO app\.saved_view/.test(text)) return [{ view_id: 98 }] as T[];
      return [] as T[];
    },
    async exec(text: string, params: unknown[] = []): Promise<number> {
      sql.push(text);
      if (/UPDATE app\.saved_view/.test(text)) return views.filter((v) => v.view_id === params[0] && v.owner === params[1]).length;
      return 1;
    },
  };
  return { D, sql };
}

describe("item 4 · saved-view folders", () => {
  it("folders nest two levels at most", async () => {
    const { D } = fakeDb();
    expect(await createFolder(D, "a@x", { name: "Third", parent_id: 2 })).toEqual({ ok: false, status: 400, error: "too_deep" });
    expect(await createFolder(D, "a@x", { name: "Second", parent_id: 1 })).toEqual({ ok: true, id: 99 });
    expect(await patchFolder(D, "a@x", { folder_id: 1, parent_id: 2 })).toMatchObject({ ok: false, error: "too_deep" });
  });
  it("a folder is deleted only when empty", async () => {
    const { D } = fakeDb();
    expect(await deleteFolder(D, "a@x", 1)).toMatchObject({ ok: false, status: 409, error: "folder_not_empty" }); // has sub-folder
    expect(await deleteFolder(D, "a@x", 2)).toMatchObject({ ok: false, status: 409, error: "folder_not_empty" }); // has a view
  });
  it("owners only: another user's folder or view is not found", async () => {
    const { D } = fakeDb();
    expect(await deleteFolder(D, "a@x", 9)).toMatchObject({ ok: false, status: 404 });
    expect(await createFolder(D, "a@x", { name: "x", parent_id: 9 })).toMatchObject({ ok: false, error: "bad_parent" });
    expect(await patchView(D, "a@x", { view_id: 1, folder_id: 9 })).toMatchObject({ ok: false, error: "bad_folder" });
    expect(await patchView(D, "a@x", { view_id: 7, pinned: true })).toMatchObject({ ok: false, status: 404 });
    expect(await saveView(D, "a@x", { name: "v", spec: { filters: {} }, folder_id: 9 })).toMatchObject({ ok: false, error: "bad_folder" });
  });
  it("move, pin and names are validated", async () => {
    const { D } = fakeDb();
    expect(await patchView(D, "a@x", { view_id: 1, folder_id: null, pinned: true })).toEqual({ ok: true, id: 1 });
    expect(await patchView(D, "a@x", { view_id: 1, pinned: "yes" })).toMatchObject({ ok: false, error: "bad_pinned" });
    expect(await createFolder(D, "a@x", { name: " ".repeat(3) })).toMatchObject({ ok: false, error: "bad_name" });
    expect(await createFolder(D, "a@x", { name: "x".repeat(61) })).toMatchObject({ ok: false, error: "bad_name" });
  });
  it("seed folders: Tax (K-1s TY2025), Agreements (ACCSO subscription docs, Unsigned side letters), Close (MTV-II FY2025 close)", () => {
    expect(SEED_FOLDERS.map((f) => f.name)).toEqual(["Tax", "Agreements", "Close"]);
    const by = Object.fromEntries(SEED_VIEWS.map((v) => [v.name, v.folder]));
    expect(by).toEqual({ "K-1s · tax year 2025": "Tax", "ACCSO · subscription docs": "Agreements", "Unsigned side letters": "Agreements", "MTV-II · FY2025 close": "Close" });
  });
});

describe("item 3 · Labels panel", () => {
  it("lists every label and field with code + meaning, and marks who can edit", () => {
    const L = buildLabelsPanel({ entity: new Map([["MTV-II", "Media Technology Equity Partners, LP"]]), portco: new Map() });
    // Part 2: Parties (L11) shows as planned until published; Execution notes its rename (R-022)
    expect(L.map((x) => x.key)).toEqual(["doc", "exec", "parties", "handling", "review"]);
    expect(L.find((x) => x.key === "parties")!.planned).toBe(true);
    const kind = L[0].fields.find((f) => f.key === "kind")!;
    expect(kind.choices).toContainEqual({ code: "k1", meaning: "K-1" });
    expect(L[0].fields.find((f) => f.key === "entity")!.choices).toContainEqual({ code: "MTV-II", meaning: "Media Technology Equity Partners, LP" });
    expect(L.find((x) => x.key === "handling")!.fields.every((f) => f.editable === "never")).toBe(true);   // Handling: never editable
    expect(L[1].fields.find((f) => f.key === "stage")!.editable).toBe("app");
    expect(L[1].fields.find((f) => f.key === "status")).toMatchObject({ planned: true, choices: expect.arrayContaining([{ code: "superseded", meaning: "Superseded" }]) });
    const recv = L.find((x) => x.key === "parties")!.fields.find((f) => f.key === "receiving_entities")!;
    expect(recv.choices.map((c) => c.code)).toEqual(expect.arrayContaining(["MTV-II", "LP", "EXTERNAL"]));
  });
});

describe("review fixes (Part 1 coder review)", () => {
  it("#5 a stored view never keeps search text, and nested objects are rebuilt to their known shape", async () => {
    const { storedSpec } = await import("@/lib/views");
    const s = storedSpec({ filters: { signed_date: { from: "2024-01-01", evil: "x" } }, search: "some name", sort: { col: "kind", dir: "asc", junk: 1 } });
    expect(s.search).toBeUndefined();
    expect(s.sort).toEqual({ col: "kind", dir: "asc" });
    expect((s.filters as Record<string, unknown>).signed_date).toEqual({ from: "2024-01-01", to: undefined });
  });
  it("#1 Excel export asks the DB for at most limit+1 rows (refused above 10,000)", async () => {
    const { XLSX_LIMIT } = await import("@/lib/find");
    expect(exportQuery({ filters: {} }, {}, XLSX_LIMIT + 1).sql).toContain("LIMIT 10001");
    expect(exportQuery({ filters: {} }, {}, 10 ** 9).sql).toContain("LIMIT 50000");
  });
  it("#11 a Drive network failure in name search returns status 0 (codes-only fallback), never throws", async () => {
    const r = await driveNameSearch("tok", "x", async () => { throw new Error("network down"); });
    expect(r).toEqual({ ids: [], capped: false, status: 0 });
  });
  it("#4 saving over an existing name also moves it to the chosen folder and drops the seed flag", async () => {
    const { D, sql } = fakeDb();
    await saveView(D, "a@x", { name: "v", spec: { filters: {} }, folder_id: 1 });
    expect(sql.find((q) => q.includes("ON CONFLICT (owner_email, name)"))).toContain("folder_id = EXCLUDED.folder_id, is_seed = false");
  });
});
