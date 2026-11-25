import { describe, expect, it } from "vitest";
import { checklistPref, checklistQuery, gapsQuery, parseChecklistSpec, SpecError } from "../src/lib/checklists";

/** CAT-WO-13 (R-058): PCAP cadence per fund on the Checklists screen. Codes only. */
describe("CAT-WO-13 cadence filter", () => {
  it("parses a whitelisted cadence and refuses anything else", () => {
    expect(parseChecklistSpec(new URLSearchParams("rule=PCAP-Q&cadence=quarterly")).cadence).toBe("quarterly");
    expect(parseChecklistSpec(new URLSearchParams("rule=PCAP-Q")).cadence).toBeNull();
    expect(() => parseChecklistSpec(new URLSearchParams("rule=PCAP-Q&cadence=monthly"))).toThrow(SpecError);
  });
  it("binds the cadence in the rows and counts scope, and returns the row's cadence", () => {
    const q = checklistQuery(parseChecklistSpec(new URLSearchParams("rule=PCAP-Q&cadence=annual")));
    expect(q.sql).toContain("r.cadence = $2");
    expect(q.countsSql).toContain("r.cadence = $2");
    expect(q.scopeParams).toEqual(["PCAP-Q", "annual"]);
    expect(q.sql).toContain("r.cadence,");
    expect(q.sql).not.toContain("'annual'");
  });
  it("gaps: cadence per entity, optional bound filter", () => {
    const g = gapsQuery("PCAP-Q", null, "quarterly");
    expect(g.sql).toContain("entity_code, cadence,");
    expect(g.params).toEqual(["PCAP-Q", "quarterly"]);
    expect(gapsQuery("PCAP-Q", null).params).toEqual(["PCAP-Q"]);
    expect(() => gapsQuery("PCAP-Q", null, "x; drop")).toThrow(SpecError);
  });
  it("the remembered state keeps a valid cadence and drops an invalid one", () => {
    expect(checklistPref({ rule: "PCAP-Q", cadence: "annual" })?.cadence).toBe("annual");
    expect(checklistPref({ rule: "PCAP-Q", cadence: "weekly" })).toBeNull();
  });
});
