/**
 * CAT-WO-01.1: a failed Review load must be visible on the page itself. Before the fix the error text was rendered
 * only inside the side panel, which is closed when no row is selected (always the case after a failed first load),
 * so the page looked like an empty queue with every counter at 0.
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewView, type ReviewViewProps } from "@/components/ReviewClient";

const base: ReviewViewProps = {
  data: null, cur: null, skipped: [], form: { status: "confirmed", stage: "", executed_date: "", note: "" }, busy: false, msg: null,
  setCur: () => {}, setForm: () => {}, onConfirm: () => {}, onSkip: () => {}, onNextPage: () => {},
};
const html = (p: Partial<ReviewViewProps>) => renderToStaticMarkup(createElement(ReviewView, { ...base, ...p }));

describe("Review page: load errors are shown on the page, not only inside the side panel", () => {
  it("first load failed (no data, nothing selected): the error is visible as an alert", () => {
    const out = html({ loadError: "forbidden" });
    expect(out).toMatch(/role="alert"/);
    expect(out).toContain("Could not load the review queue");
    expect(out).toContain("forbidden");
  });
  it("a later page load failed while a queue is shown: the error is visible outside the panel", () => {
    const data = { counts: {}, page: 0, nextPage: 1, pageRows: 50, rows: [], notShown: { noAccess: 0, checkFailed: 0, total: 0 }, canWrite: false };
    const out = html({ data, loadError: "HTTP 503" });
    expect(out.indexOf("Could not load the review queue")).toBeGreaterThanOrEqual(0);
    expect(out).not.toMatch(/<aside[^>]*>[\s\S]*Could not load the review queue/);
  });
  it("no error: no alert", () => expect(html({})).not.toMatch(/role="alert"/));
});
