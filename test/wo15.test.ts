import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DEFAULT_LIST, REVIEW_LANES, ReviewView, type ReviewViewProps } from "@/components/ReviewClient";
import { BACKLOG_LANES } from "@/lib/reviewq";
import { BULK_SUBJECT_BLOCKERS, subjectBulk, subjectBulkQuery } from "@/lib/subjectbulk";
import { SpecError } from "@/lib/find";
import type { Db } from "@/lib/db";
import { batchResponse } from "./helpers";

/** CAT-WO-15 · Review queue split + bulk Confirm on Match subject. Invented codes only. */
const ME = "ryan@allegiscapital.com";
const session = { v: 1, email: ME, sub: "t", hd: "allegiscapital.com", at: "tok", scopes: ["openid", "email"], exp: 9e9 } as never;
const id = (i: number) => `F${String(i).padStart(19, "0")}`;

function drive(get: Record<string, number> = {}) {
  const calls: { url: string; body: string }[] = [];
  const f = async (url: string, init?: RequestInit) => {
    const body = String(init?.body ?? "");
    calls.push({ url, body });
    if (url.includes("/batch/drive/v3")) {
      const ids = [...body.matchAll(/GET \/drive\/v3\/files\/([^?]+)\?/g)].map((m) => decodeURIComponent(m[1]));
      return batchResponse(ids.map((x) => ({ status: get[x] ?? 200, body: (get[x] ?? 200) === 200 ? { id: x, capabilities: { canModifyLabels: true }, labelInfo: { labels: [] } } : { error: { errors: [{ reason: "notFound" }] } } })));
    }
    if (/modifyLabels/.test(url)) return new Response("{}", { status: 200 });
    return new Response("{}", { status: 404 });
  };
  return { f, calls };
}
function fakeDb(eligible: number, rows: { file_id: string; document_id: string; code: string }[]) {
  const execs: { text: string; params: unknown[] }[] = [];
  const queries: string[] = [];
  const D: Db = {
    async rows<T>(text: string) { queries.push(text); return (text.includes("count(*)") ? [{ n: eligible }] : rows) as T[]; },
    async exec(text: string, params: unknown[] = []) { execs.push({ text, params }); return 1; },
  };
  return { D, execs, queries };
}

describe("CAT-WO-15 · review_total and the backlog group", () => {
  it("migration 015 adds review_total = the queue without no_kind and status_unknown; open_total stays", () => {
    const sql = readFileSync(join(__dirname, "..", "db", "migrations", "015_wo15.sql"), "utf8");
    expect(sql).toMatch(/queue_reason <> ALL \(ARRAY\['no_kind'::text, 'status_unknown'::text\]\)\) AS review_total/);
    expect(sql).toMatch(/SELECT count\(\*\)::integer FROM app\.v_review_queue\) AS open_total/);
    expect(sql).toContain("security_barrier = true");
  });
  it("backlog lanes and review lanes split the six lanes", () => {
    expect([...BACKLOG_LANES].sort()).toEqual(["no_kind", "status_unknown"]);
    expect(REVIEW_LANES.some((l) => (BACKLOG_LANES as readonly string[]).includes(l))).toBe(false);
    expect(DEFAULT_LIST.lanes).toEqual(REVIEW_LANES);
  });
  it("the headline shows review_total; No kind / Status unknown sit under 'Backlog (rule rounds)'", () => {
    const props: ReviewViewProps = {
      data: { counts: { open_total: 23869, review_total: 2118, no_kind: 12558, status_unknown: 9193, match_subject: 1445 }, page: 0, pageSize: 25, matched: 0, nextPage: null, pageRows: 0, rows: [], notShown: { noAccess: 0, checkFailed: 0, total: 0 }, canWrite: true },
      cur: null, skipped: [], form: { status: "confirmed", stage: "", executed_date: "", note: "" }, busy: false, msg: null,
      setCur: () => {}, setForm: () => {}, onConfirm: () => {}, onSkip: () => {}, onNextPage: () => {}, list: DEFAULT_LIST, setList: () => {},
    };
    const out = renderToStaticMarkup(createElement(ReviewView, props));
    expect(out).toContain('class="k-cap">To review</span><span class="k-num">2,118<');
    const backlog = out.indexOf("Backlog (rule rounds)");
    expect(backlog).toBeGreaterThan(0);
    expect(out.indexOf('class="k-cap">No kind<')).toBeGreaterThan(backlog);
    expect(out.indexOf('class="k-cap">Status unknown<')).toBeGreaterThan(backlog);
    expect(out).toContain('class="k-num">23,869<');             // "All lanes" keeps the open total, inside the backlog group
    expect(out).toContain("Confirm single matches");              // match_subject is in the default lanes and the user can write
  });
  it("the sidebar badge reads review_total (falls back to open_total before migration 015)", () => {
    const src = readFileSync(join(__dirname, "..", "src", "app", "api", "nav", "route.ts"), "utf8");
    expect(src).toContain("review_total ?? r[0]?.open_total");
  });
});

describe("CAT-WO-15 · bulk Confirm on Match subject (R-023)", () => {
  it("takes only single-candidate rows with no blocking reason and a roster check; filters bound; capped at 500", () => {
    const q = subjectBulkQuery(JSON.stringify({ filters: { entity: ["MTV-IV (A)"] } }));
    expect(q.sql).toContain("queue_reason = 'match_subject'");
    expect(q.sql).toContain("cardinality(subject_candidates) = 1");
    expect(q.sql).toContain("app.v_party");
    expect(q.sql).toContain("LIMIT 500");
    expect(q.sql).not.toContain("MTV-IV (A)");
    expect(q.params).toContainEqual([...BULK_SUBJECT_BLOCKERS]);
    expect(() => subjectBulkQuery(JSON.stringify({ filters: { kind: ["x'); drop"] } }))).toThrow(SpecError);
  });
  it("without confirm: a preview, no Drive call, no write", async () => {
    const d = drive(); const { D, execs } = fakeDb(1445, []);
    const r = await subjectBulk({}, { session, db: D, fetch: d.f as never });
    expect(r).toEqual({ status: 200, body: { preview: true, eligible: 1445, this_action: 500, cap: 500 } });
    expect(d.calls.length).toBe(0); expect(execs.length).toBe(0);
  });
  it("with confirm: live check as the user, no-access skipped, each file's own code, match_subject events (codes only)", async () => {
    const rows = [{ file_id: id(1), document_id: "11", code: "LP-0001" }, { file_id: id(2), document_id: "12", code: "LP-0002" }, { file_id: id(3), document_id: "13", code: "LP-0003" }];
    const d = drive({ [id(2)]: 404 }); const { D, execs } = fakeDb(3, rows);
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const r = await subjectBulk({ confirm: true }, { session, db: D, fetch: d.f as never, sleep: async () => {} });
    const lines = log.mock.calls.map((c) => String(c[0])).join("\n"); log.mockRestore();
    expect(r.status).toBe(200);
    expect(r.body.report).toMatchObject({ skipped_no_access: 1, failed: 0, events_failed: false, eligible_before: 3 });
    expect(d.calls.some((c) => c.url.includes(`${id(2)}/modifyLabels`))).toBe(false);
    const done = (r.body.report as { done: number }).done;
    const evParams = execs.flatMap((e) => e.params);
    expect(execs[0].text).toContain("'match_subject', $");          // queue_reason and source are the lane's, as a single save
    if ((r.body.report as { label_published: boolean }).label_published) {
      expect(d.calls.find((c) => c.url.includes(`${id(1)}/modifyLabels`))!.body).toContain("LP-0001");
      expect(d.calls.find((c) => c.url.includes(`${id(3)}/modifyLabels`))!.body).toContain("LP-0003");
    }
    expect(done).toBe(2);
    expect(evParams).toContain(JSON.stringify({ subject_codes: ["LP-0001"], bulk: true }));
    expect(evParams).not.toContain(JSON.stringify({ subject_codes: ["LP-0002"], bulk: true }));
    expect(lines).toContain("subject_bulk");
  });
  it("never more than 500 files per action, even if the query returned more", async () => {
    const rows = Array.from({ length: 501 }, (_, i) => ({ file_id: id(i + 1), document_id: String(i), code: "LP-0001" }));
    const d = drive(); const { D } = fakeDb(501, rows);
    const r = await subjectBulk({ confirm: true }, { session, db: D, fetch: d.f as never, sleep: async () => {} });
    expect((r.body.report as { done: number }).done).toBeLessThanOrEqual(500);
  });
});
