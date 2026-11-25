import { describe, expect, it } from "vitest";
import { buildWhere, exportQuery, HIDE_COPIES_SQL, hidesCopies, pageQuery, parseSpec, SpecError } from "../src/lib/find";
import { chipsOf, EMPTY } from "../src/lib/findstate";

/** CAT-WO-17 (R-061): Find hides copies of a document unless asked. */
describe("CAT-WO-17 copies hidden in Find", () => {
  const HIDE = HIDE_COPIES_SQL;
  it("keeps a copy whose primary is outside Find", () => { expect(HIDE).toContain("document_id NOT IN (SELECT p.document_id FROM app.v_find_x p WHERE p.is_primary"); });
  it("hides copies by default in Find and its export", () => {
    const s = parseSpec({ filters: {} });
    expect(pageQuery(s, undefined, { hideCopies: true }).where).toContain(HIDE);
    expect(exportQuery(s, { hideCopies: true }).where).toContain(HIDE);
  });
  it("leaves callers that don't ask (the Review queue) unchanged", () => {
    expect(buildWhere(parseSpec({ filters: {} })).where).not.toContain(HIDE);
  });
  it("shows copies when asked, when Primary copy is set, or for a File ID / Catalog ID", () => {
    for (const filters of [{ show_copies: true }, { is_primary: "no" }, { is_primary: "yes" }, { primary_only: true }, { file_id: "abc" }, { document_id: "12" }]) {
      const f = parseSpec({ filters }).filters;
      expect(hidesCopies(f)).toBe(false);
      expect(buildWhere(parseSpec({ filters }), { hideCopies: true }).where).not.toContain(HIDE);
    }
  });
  it("refuses a non-boolean show_copies", () => {
    expect(() => buildWhere(parseSpec({ filters: { show_copies: "yes; drop" } }), { hideCopies: true })).toThrow(SpecError);
  });
  it("chip says copies are shown", () => {
    expect(chipsOf({ ...EMPTY, filters: { show_copies: true } })).toEqual([{ key: "show_copies", label: "Copies", text: "shown" }]);
  });
});
