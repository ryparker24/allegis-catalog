import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { parseReviewSpec, reviewQuery } from "@/lib/reviewq";
import { SpecError } from "@/lib/find";
import { DEFAULT_LIST, ReviewView, isExecutable, type ReviewViewProps } from "@/components/ReviewClient";
import type { Row } from "@/components/client";
import { buildReviewMods, hasField, validateReview } from "@/lib/labels";
import { reviewWrite } from "@/lib/review";

describe("CAT-WO-02 item 2 · Review queue lists run in SQL", () => {
  it("no spec: CAT-WO-01's order and page size are unchanged", () => {
    const q = reviewQuery(parseReviewSpec(null, null), ["skip1234567"], 0);
    expect(q.sql).toContain("ORDER BY queue_rank, confidence_rank, file_id LIMIT 50 OFFSET 0");
    expect(q.params).toEqual([["skip1234567"]]);
  });
  it("lanes, filters and sort are whitelisted and bound", () => {
    const r = parseReviewSpec(JSON.stringify({ filters: { kind: ["k1"], fy_range: { from: 2020 } }, sort: { col: "confidence", dir: "asc" }, pageSize: 25 }), "no_kind,stage_unknown");
    const q = reviewQuery(r, [], 2);
    expect(q.sql).toContain("queue_reason = ANY(");
    expect(q.sql).toContain("ORDER BY confidence_rank ASC NULLS LAST, queue_rank, confidence_rank, file_id LIMIT 25 OFFSET 50");
    expect(q.sql).not.toMatch(/k1|no_kind|2020/);
    expect(q.countSql).toContain("FROM app.v_review_queue WHERE");
  });
  it("the queue order can be reversed (the Why header's arrow does something)", () => {
    const q = reviewQuery(parseReviewSpec(JSON.stringify({ sort: { col: "queue", dir: "desc" } }), null), [], 0);
    expect(q.sql).toContain("ORDER BY queue_rank DESC, confidence_rank DESC, file_id");
  });
  it("refuses unknown lanes, unknown sort columns and injection", () => {
    expect(() => parseReviewSpec(null, "no_kind;drop")).toThrow(SpecError);
    expect(() => parseReviewSpec(JSON.stringify({ sort: { col: "name" } }), null)).toThrow(SpecError);
    expect(() => parseReviewSpec(JSON.stringify({ filters: { kind: ["x'); drop table y;--"] } }), null)).toThrow(SpecError);
    expect(() => parseReviewSpec("{not json", null)).toThrow(SpecError);
  });
});

describe("Review page (Datum look)", () => {
  const base: ReviewViewProps = {
    data: { counts: { open_total: 19089, stage_unknown: 342, low_confidence_executed: 330, no_kind: 18417, reviewed_today: 0 }, page: 0, pageSize: 25, matched: 19089, nextPage: 1, pageRows: 0, rows: [], notShown: { noAccess: 0, checkFailed: 0, total: 0 }, canWrite: false },
    cur: null, skipped: [], form: { status: "confirmed", stage: "", executed_date: "", note: "" }, busy: false, msg: null,
    setCur: () => {}, setForm: () => {}, onConfirm: () => {}, onSkip: () => {}, onNextPage: () => {},
  };
  it("counter cards have caption, big number and a one-line explanation; lanes are filter buttons", () => {
    const out = renderToStaticMarkup(createElement(ReviewView, { ...base, list: { ...DEFAULT_LIST, lanes: ["no_kind"] }, setList: () => {} }));
    expect(out).toContain('class="k-cap">No kind<');
    expect(out).toContain('class="k-num">18,417<');
    expect(out).toContain("couldn&#x27;t tell what the document is");
    expect(out).toMatch(/aria-pressed="true"[^>]*>.{0,80}No kind|No kind[\s\S]{0,40}/);
    expect(out).toContain("Review queue");              // serif page title
    expect(out).toContain("None shown on this page · 19,089 files");   // Datum pager text (empty page)
  });

  // CAT-WO-02 item 6 / 8 on the Review screen
  const row = (o: Partial<Row>): Row => ({
    file_id: "AAAAAAAAAAAAAAAAAAAAA1", document_id: 1, name: "x", web_view_link: "", kind: "quarterly_report", entities: [], portcos: [],
    fiscal_year: 2023, period: null, stage: null, executed_date: null, workstream: null, issuer: null, tier: "normal", review_status: null,
    status: null, issued_date: null, issuing_entity: null, receiving_entities: [], signed_date: null, effective_date: null, is_primary: true,
    modified_time: null, file_type_family: "pdf", queue_reason: "status_unknown", signals: null, confidence: null, stage_suggested: null,
    changed: [], catalog: {}, requires_execution: false, ...o,
  });
  it("CAT-WO-15: the Status unknown card sits in the Backlog (rule rounds) group, after the review lanes", () => {
    const out = renderToStaticMarkup(createElement(ReviewView, { ...base, data: { ...base.data!, counts: { ...base.data!.counts, status_unknown: 26498 } }, list: DEFAULT_LIST, setList: () => {} }));
    expect(out).toContain('class="k-cap">Status unknown<');
    expect(out).toContain('class="k-num">26,498<');
    expect(out.indexOf("Stage unknown")).toBeLessThan(out.indexOf("Executed, low confidence"));
    expect(out.indexOf("Backlog (rule rounds)")).toBeLessThan(out.indexOf('class="k-cap">Status unknown<'));
    expect(out.indexOf('class="k-cap">Executed, low confidence<')).toBeLessThan(out.indexOf("Backlog (rule rounds)"));
  });
  it("the form shows Status for a non-executable kind (disabled until published) and Stage for an executable one", () => {
    const st = renderToStaticMarkup(createElement(ReviewView, { ...base, cur: row({}), statusPublished: false, editSlot: createElement("div", { id: "edit-slot" }) }));
    expect(st).toContain("Status &amp; Execution label");
    expect(st).not.toContain(">Execution label<");
    expect(st).toMatch(/<select[^>]*disabled/);
    expect(st).toContain("publishes with the Part 2 release");
    expect(st).toContain('id="edit-slot"');                       // item 8: Edit labels in the Review form
    const ex = renderToStaticMarkup(createElement(ReviewView, { ...base, cur: row({ kind: "lpa", requires_execution: true, queue_reason: "stage_unknown" }) }));
    expect(ex).toContain(">Execution label<");
    expect(ex).not.toContain("Status &amp; Execution label");
    expect(isExecutable(row({ requires_execution: null, queue_reason: "no_kind" }))).toBe(true);   // not known as non-executable: Stage, as before
    expect(isExecutable(row({ requires_execution: null, queue_reason: "status_unknown" }))).toBe(false); // the lane decides: Status
  });
});

describe("CAT-WO-02 item 6 · Review lanes and the Status write", () => {
  it("status_unknown is a whitelisted lane, status a sortable column; the page query returns requires_execution and status", () => {
    const q = reviewQuery(parseReviewSpec(JSON.stringify({ sort: { col: "status", dir: "asc" } }), "status_unknown"), [], 0);
    expect(q.params).toContainEqual(["status_unknown"]);
    expect(q.sql).toContain("ORDER BY status ASC NULLS LAST");
    expect(q.sql).toMatch(/requires_execution, status, subject_candidates, location, location_folder_id, other_locations,\s+subject_reasons, content_disagrees\s+FROM app.v_review_queue/);   // + CAT-WO-03 Match subject, CAT-WO-03.1 Location, CAT-WO-06 content lanes
  });
  it("doc_status: accepted once Status is published (refused before), never together with a stage, unknown values refused", () => {
    if (hasField("exec", "status")) expect(validateReview({ status: "confirmed", doc_status: "final" })).toMatchObject({ ok: true, value: { docStatus: "final" } });
    else expect(validateReview({ status: "confirmed", doc_status: "final" })).toEqual({ ok: false, reason: "label_not_published:exec.status" });
    if (hasField("exec", "status")) expect(validateReview({ status: "confirmed", doc_status: "final", stage: "draft" })).toEqual({ ok: false, reason: "stage_or_status" });
    expect(validateReview({ status: "confirmed", doc_status: "nonsense" })).toEqual({ ok: false, reason: "doc_status" });
    expect(validateReview({ status: "confirmed" })).toMatchObject({ ok: true, value: { docStatus: null } });
    const m = buildReviewMods({ status: "confirmed", stage: null, executedDate: null, note: null, docStatus: null, reviewerEmail: "a@b.c" });
    expect(m.labels).toEqual(["review"]);                         // no Status, no Stage: only Catalog Review is written
  });
});

describe("CAT-WO-02 · Status is only for non-executable documents (server, CISO review)", () => {
  const session = { v: 1, email: "ryan@allegiscapital.com", sub: "1", hd: "allegiscapital.com", at: "x", scopes: [], exp: Math.floor(Date.now() / 1000) + 600 } as never;
  const dbWith = (row: Record<string, unknown>) => ({ rows: async () => [row], exec: async () => 1 }) as never;
  it("refuses doc_status on an executable document before any Drive call; allows it in the Status-unknown lane", async () => {
    if (!hasField("exec", "status")) return;            // before publish the earlier label_not_published refusal applies
    let called = false;
    const f = async () => { called = true; return new Response("{}", { status: 200 }); };
    const r = await reviewWrite({ file_id: "AAAAAAAAAAAAAAAAAAAAA1", status: "confirmed", doc_status: "final" },
      { session, db: dbWith({ document_id: "1", queue_reason: "stage_unknown", requires_execution: true }), fetch: f });
    expect(r).toMatchObject({ status: 400, body: { reason: "status_not_for_executable" } });
    expect(called).toBe(false);
    const ok = await reviewWrite({ file_id: "AAAAAAAAAAAAAAAAAAAAA1", status: "confirmed", doc_status: "final" },
      { session, db: dbWith({ document_id: "1", queue_reason: "status_unknown", requires_execution: null }), fetch: f });
    expect(ok.status).toBe(200);
    expect(called).toBe(true);
  });
});
