/**
 * CAT-WO-03.1 · the "changed in Drive" marker now covers Status, Issued date, Parties and Subject (Ryan: it never
 * showed on Status), without false markers: dates compared as YYYY-MM-DD, unlabelled files and views that don't
 * select a column are skipped.
 */
import { describe, expect, it } from "vitest";
import { changedFields, decodeLabels, type LiveValues } from "@/lib/labels";
import { buildEditMods } from "@/lib/edit";

const live = (o: Partial<LiveValues>): LiveValues => ({ ...decodeLabels({ labels: [] }), has_doc_label: true, ...o });

describe("changed in Drive marker (CAT-WO-03.1)", () => {
  it("marks Status when Drive says Issued and the catalog still says Final", () => {
    expect(changedFields({ status: "final" }, live({ status: "issued" }))).toContain("status");
  });
  it("no marker once the catalog holds the same value (the edit's DB update landed)", () => {
    expect(changedFields({ status: "issued" }, live({ status: "issued" }))).not.toContain("status");
  });
  it("dates: a Date from the DB driver equals the label's YYYY-MM-DD", () => {
    expect(changedFields({ issued_date: new Date("2025-04-30T00:00:00Z") }, live({ issued_date: "2025-04-30" }))).not.toContain("issued_date");
    expect(changedFields({ issued_date: "2025-04-30" }, live({ issued_date: "2025-05-01" }))).toContain("issued_date");
  });
  it("Parties / Subject: order-insensitive, and marked when they differ", () => {
    expect(changedFields({ receiving_entities: ["X", "LP"] }, live({ receiving_entities: ["LP", "X"] }))).not.toContain("receiving_entities");
    expect(changedFields({ subject_codes: ["LP-0001"] }, live({ subject_codes: ["LP-0002"] }))).toContain("subject_codes");
    expect(changedFields({ issuing_entity: "NL-I" }, live({ issuing_entity: null }))).toContain("issuing_entity");
  });
  it("no false marker on an unlabelled file or on a view that doesn't select the column (Review rows)", () => {
    expect(changedFields({ status: "final" }, live({ has_doc_label: false, status: null }))).not.toContain("status");
    expect(changedFields({ kind: "k1" }, live({ kind: "k1", status: "issued", issuing_entity: "X" }))).toEqual([]);
  });
});

describe("bulk edit stays a field-level confirmation (proposal 3, CAT-WO-03.1)", () => {
  it("a bulk edit writes the field but does NOT stamp Catalog Review = Confirmed", () => {
    const m = buildEditMods({ status: "issued" }, "ryan@allegiscapital.com", { confirm: false });
    expect(m.labels).toEqual(["exec"]);
  });
  it("a single edit still confirms the file", () => {
    expect(buildEditMods({ status: "issued" }, "ryan@allegiscapital.com").labels).toEqual(["exec", "review"]);
  });
});
