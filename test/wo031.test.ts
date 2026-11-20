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

import { linkEdits } from "@/lib/checklists";
import { SCHEMA } from "@/lib/labels";
describe("checklist link labels the document to match the requirement (CAT-WO-03.1)", () => {
  const kinds = (SCHEMA.doc.fields as Record<string, { choices?: Record<string, string> }>).kind.choices ?? {};
  it("audited FS: kind (once published), + the row's entity kept with others, the row's FY, an annual period", () => {
    const e = linkEdits("AUDITED-FS|CIP-I||2025|", { entities: ["X"] });
    expect(e.entities).toEqual(["CIP-I", "X"]);
    expect(e.fiscal_year).toBe(2025);
    expect(e.period).toBe("fy");
    expect("kind" in e).toBe(Object.hasOwn(kinds, "audited_financial_statements"));   // never a kind the label can't hold
  });
  it("PCAP: the quarter; an entity already on the file is not rewritten", () => {
    const e = linkEdits("PCAP-Q|NL-I|LP-0001|2025|Q3", { entities: ["NL-I"] });
    expect(e.period).toBe("q3");
    expect(e.entities).toBeUndefined();
    expect(e.kind).toBe("capital_statement");
  });
});

import { buildReviewMods } from "@/lib/labels";
describe("label dates are RFC 3339 strings, as Drive files.modifyLabels requires (CAT-WO-03.2)", () => {
  const dates = (mods: unknown[]) => JSON.stringify(mods).match(/"setDateValues":\[[^\]]*\]/g) ?? [];
  it("Edit labels: effective / issued / executed dates", () => {
    const m = buildEditMods({ effective_date: "2025-12-31", stage: "fully_executed", executed_date: "2025-03-31" }, "ryan@allegiscapital.com");
    expect(dates(m.labelModifications)).toEqual(['"setDateValues":["2025-12-31"]', '"setDateValues":["2025-03-31"]']);
  });
  it("Review form: the executed date", () => {
    const m = buildReviewMods({ status: "confirmed", stage: "fully_executed", executedDate: "2025-03-31", note: null, reviewerEmail: "ryan@allegiscapital.com" } as never);
    expect(dates(m.labelModifications)).toEqual(['"setDateValues":["2025-03-31"]']);
  });
});
