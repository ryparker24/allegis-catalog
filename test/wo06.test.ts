import { describe, expect, it } from "vitest";
import { contentFor, pageRange } from "@/lib/content";
import { parseReviewSpec, reviewQuery, LANES } from "@/lib/reviewq";
import { checklistQuery } from "@/lib/checklists";
import type { Db } from "@/lib/db";
import { batchResponse } from "./helpers";

const FID = "1AbCdEfGhIjKlMnOpQrStUvWx";
const drive = (ok: Set<string>) => (async (_url: string, init?: RequestInit) => {
  const ids = [...String(init?.body ?? "").matchAll(/files\/([A-Za-z0-9_-]+)\?/g)].map((m) => m[1]);
  return batchResponse(ids.map((id) => (ok.has(id) ? { status: 200, body: { id, name: "n", webViewLink: "l" } } : { status: 404, body: {} })));
}) as never;
function fakeDb(handler: (sql: string, params: unknown[]) => unknown[]): Db {
  return { rows: async (sql: string, params: unknown[] = []) => handler(sql, params) } as unknown as Db;
}

describe("CAT-WO-06 · Matched from content (side panel)", () => {
  it("pages read as p. N or p. N–M", () => {
    expect(pageRange(3, 3)).toBe("p. 3");
    expect(pageRange(3, 5)).toBe("p. 3–5");
    expect(pageRange(null, null)).toBe("");
  });
  it("returns codes, pages, anchor and reason codes only - from app.v_doc_content, live-checked as the user first", async () => {
    const seen: string[] = [];
    const D = fakeDb((sql) => {
      seen.push(sql);
      if (sql.includes("v_find_x")) return [{ document_id: "42" }];
      return [{ seq: 1, page_from: 4, page_to: 5, partner_code: "LP-0101", confidence: "high", anchor: "PCAP-HDR-LBL", reason: null, lane: false,
                page_count: 60, outcome: "ok", ocr_used: false, read_at: "2026-11-21", content_fiscal_year: 2025, content_quarter: 3,
                content_entity: "MTV-V (A)", content_disagrees: null },
              { seq: 2, page_from: 6, page_to: 6, partner_code: "not a code", confidence: "low", anchor: null, reason: "NOT_IN_FUND", lane: true,
                page_count: 60, outcome: "ok", ocr_used: false, read_at: "2026-11-21", content_fiscal_year: 2025, content_quarter: 3,
                content_entity: "MTV-V (A)", content_disagrees: null }];
    });
    const r = await contentFor(D, "tok", FID, drive(new Set([FID])));
    expect(r.status).toBe(200);
    const m = r.body.matches as { partner_code: string }[];
    expect(m.map((x) => x.partner_code)).toEqual(["LP-0101"]);          // a value that is not a roster code is never passed on
    expect(seen.some((s) => s.includes("app.v_doc_content"))).toBe(true);
    expect(seen.join(" ")).not.toMatch(/\b(alias|display_name|legal_name|page_text)\b/);
  });
  it("refuses a malformed file ID, and a file the user cannot open right now - before any DB read", async () => {
    expect((await contentFor(fakeDb(() => []), "tok", "bad id!", drive(new Set()))).status).toBe(400);
    let dbRead = false;
    const r = await contentFor(fakeDb(() => { dbRead = true; return [{ document_id: "42" }]; }), "tok", FID, drive(new Set()));
    expect(r.status).toBe(403);
    expect(dbRead).toBe(false);
  });
});

describe("CAT-WO-06 · Review lanes and checklists", () => {
  it("content_disagrees is a whitelisted lane; the page query returns the content reason codes", () => {
    expect(LANES).toContain("content_disagrees");
    const q = reviewQuery(parseReviewSpec(null, "content_disagrees,match_subject"), [], 0);
    expect(q.params).toContainEqual(["content_disagrees", "match_subject"]);
    expect(q.sql).toContain("subject_reasons, content_disagrees");
  });
  it("the checklist rows carry best_page (p. N beside a package row's best document)", () => {
    const q = checklistQuery({ rule: "PCAP-Q", entity: null, fy: null, q: null, results: [], sort: "urgency", dir: "asc", page: 0, pageSize: 25 } as never);
    expect(q.sql).toContain("r.best_page");
  });
});
