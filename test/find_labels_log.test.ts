import { describe, expect, it } from "vitest";
import { buildWhere, exportQuery, groupQuery, pageQuery, parseSpec, SpecError, toCsv } from "@/lib/find";
import { buildReviewMods, LABEL_IDS, validateReview } from "@/lib/labels";
import { reviewWrite } from "@/lib/review";
import { sanitize } from "@/lib/log";
import { nowS, type Session } from "@/lib/session";

describe("Find SQL builder", () => {
  it("filters become bind parameters, never SQL text", () => {
    const q = pageQuery({ filters: { kind: ["k1", "(none)"], entity: ["NL-I"], fiscal_year: [2024], primary_only: true }, sort: { col: "fiscal_year", dir: "desc" }, page: 2, pageSize: 100 });
    expect(q.sql).toContain("FROM app.v_find");
    expect(q.sql).toContain("LIMIT 100 OFFSET 200");
    expect(q.sql).not.toContain("k1");
    expect(q.params).toEqual([["k1"], ["NL-I"], [2024]]);
  });
  it("rejects injection attempts and unknown columns", () => {
    expect(() => buildWhere({ filters: { kind: ["k1'; drop table x;--"] } })).toThrow(SpecError);
    expect(() => pageQuery({ filters: {}, sort: { col: "name; select 1", dir: "asc" } })).toThrow(SpecError);
    expect(() => groupQuery({ filters: {}, groupBy: "pg_sleep(10)" })).toThrow(SpecError);
    expect(() => parseSpec({ filters: { fiscal_year: ["1800"] } })).toThrow(SpecError);
  });
  it("export carries codes and Drive links only (no name column) and defuses spreadsheet formulas", () => {
    expect(exportQuery({ filters: {} }).sql).not.toMatch(/\bname\b/);
    expect(toCsv([{ a: "=HYPERLINK(1)", b: ["x", "y"] }], ["a", "b"])).toBe("a,b\r\n'=HYPERLINK(1),x|y\r\n");
  });
});

describe("Review write touches ONLY Execution + Catalog Review", () => {
  it("label modifications name only the exec and review label IDs", () => {
    const m = buildReviewMods({ status: "confirmed", stage: "fully_executed", executedDate: "2024-03-31", note: null, reviewerEmail: "ryan@allegiscapital.com" });
    const ids = (m.labelModifications as { labelId: string }[]).map((x) => x.labelId);
    expect(ids).toEqual([LABEL_IDS.exec, LABEL_IDS.review]);
    expect(ids).not.toContain(LABEL_IDS.doc);
    expect(ids).not.toContain(LABEL_IDS.handling);
  });
  it("no stage chosen -> only the Catalog Review label is written", () => {
    const m = buildReviewMods({ status: "wrong", stage: null, executedDate: null, note: "kind is wrong", reviewerEmail: "ryan@allegiscapital.com" });
    expect((m.labelModifications as { labelId: string }[]).map((x) => x.labelId)).toEqual([LABEL_IDS.review]);
  });
  it("validation", () => {
    expect(validateReview({ status: "maybe" }).ok).toBe(false);
    expect(validateReview({ status: "confirmed", stage: "draft", executed_date: "2024-01-01" }).ok).toBe(false);
    expect(validateReview({ status: "confirmed", stage: "fully_executed", executed_date: "2024-01-01" }).ok).toBe(true);
  });
  it("Drive refuses -> no review_event row is inserted; Drive ok -> exactly one INSERT", async () => {
    const session: Session = { v: 1, email: "ryan@allegiscapital.com", sub: "1", hd: "allegiscapital.com", at: "ya29.x", scopes: [], exp: nowS() + 600 };
    const execs: string[] = [];
    const db = { rows: async () => [{ document_id: "9", queue_reason: "stage_unknown" }], exec: async (t: string) => { execs.push(t); return 1; } } as never;
    const refused = await reviewWrite({ file_id: "AAAAAAAAAAAAAAAAAAAAA1", status: "confirmed" }, { session, db, fetch: async () => new Response("{}", { status: 403 }) });
    expect(refused.status).toBe(403);
    expect(execs).toHaveLength(0);
    let sent = "";
    const ok = await reviewWrite({ file_id: "AAAAAAAAAAAAAAAAAAAAA1", status: "confirmed", stage: "fully_executed" }, { session, db, fetch: async (u, i) => { sent = `${u} ${i?.body}`; return new Response("{}", { status: 200 }); } });
    expect(ok.status).toBe(200);
    expect(execs).toHaveLength(1);
    expect(execs[0]).toMatch(/^\s*INSERT INTO app\.review_event/);
    expect(sent).toContain("/modifyLabels");
  });
  it("a file not in the queue view (e.g. secret tier, unlabelled, already reviewed) is refused before any Drive call", async () => {
    let called = false;
    const db = { rows: async () => [], exec: async () => 1 } as never;
    const session = { v: 1, email: "ryan@allegiscapital.com", sub: "1", hd: "allegiscapital.com", at: "x", scopes: [], exp: nowS() + 600 } as Session;
    const r = await reviewWrite({ file_id: "AAAAAAAAAAAAAAAAAAAAA1", status: "confirmed" }, { session, db, fetch: async () => { called = true; return new Response("{}"); } });
    expect(r.status).toBe(404);
    expect(called).toBe(false);
  });
});

describe("Worker logs carry IDs and codes, never names", () => {
  it("drops non-allow-listed keys (name, title, ...) and redacts non-code strings", () => {
    const out = sanitize({ event: "find", file_id: "AAAAAAAAAAAAAAAAAAAAA1", name: "Some LP Capital Statement.pdf", title: "x", status: "Investor Name LLC K-1" });
    expect(out).toEqual({ event: "find", file_id: "AAAAAAAAAAAAAAAAAAAAA1", status: "[redacted]" });
  });
});
