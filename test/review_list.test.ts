import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { parseReviewSpec, reviewQuery } from "@/lib/reviewq";
import { SpecError } from "@/lib/find";
import { DEFAULT_LIST, ReviewView, type ReviewViewProps } from "@/components/ReviewClient";

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
});
