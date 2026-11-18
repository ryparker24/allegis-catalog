import { describe, expect, it } from "vitest";
import { BULK_CAP, buildEditMods, bulkWrite, LABELS_THE_APP_MAY_WRITE, validateEdit } from "@/lib/edit";
import { editBulk, editOne } from "@/lib/editflow";
import { LABEL_IDS, SCHEMA } from "@/lib/labels";
import type { Db } from "@/lib/db";
import { batchResponse } from "./helpers";

const ME = "ryan@allegiscapital.com";
const session = { v: 1, email: ME, sub: "t", hd: "allegiscapital.com", at: "tok", scopes: ["openid", "email", "https://www.googleapis.com/auth/drive.metadata"], exp: 9e9 } as never;
const F1 = "1AbCdEfGhIjKlMnOpQrS", F2 = "2AbCdEfGhIjKlMnOpQrS", F3 = "3AbCdEfGhIjKlMnOpQrS";

/** Drive stub: batch files.get answers per id; modifyLabels answers per id (a queue of statuses); records requests. */
function drive(get: Record<string, number>, write: Record<string, number[]> = {}) {
  const calls: { url: string; body: string }[] = [];
  const f = async (url: string, init?: RequestInit) => {
    const body = String(init?.body ?? "");
    calls.push({ url, body });
    if (url.includes("/batch/drive/v3")) {
      const ids = [...body.matchAll(/GET \/drive\/v3\/files\/([^?]+)\?/g)].map((m) => decodeURIComponent(m[1]));
      return batchResponse(ids.map((id) => {
        const st = get[id] ?? 200;
        return { status: st, body: st === 200 ? { id, capabilities: { canModifyLabels: true }, labelInfo: { labels: [] } } : { error: { errors: [{ reason: "notFound" }] } } };
      }));
    }
    const m = /files\/([^/]+)\/modifyLabels/.exec(url);
    if (m) {
      const q = write[decodeURIComponent(m[1])];
      const st = q && q.length ? q.shift()! : 200;
      return new Response(JSON.stringify(st === 200 ? { kind: "drive#modifyLabelsResponse" } : { error: { errors: [{ reason: st === 403 ? "insufficientFilePermissions" : "backendError" }] } }), { status: st });
    }
    return new Response("{}", { status: 404 });
  };
  return { f, calls };
}
function fakeDb(inScope: string[]) {
  const execs: { text: string; params: unknown[] }[] = [];
  const D: Db = {
    async rows<T>(_text: string, params: unknown[] = []) {
      const want = Array.isArray(params[0]) ? (params[0] as string[]) : [String(params[0])];
      return want.filter((id) => inScope.includes(id)).map((id) => ({ file_id: id, document_id: "77" })) as T[];
    },
    async exec(text: string, params: unknown[] = []) { execs.push({ text, params }); return 1; },
  };
  return { D, execs };
}

describe("G-E1 test_edit_writes_only_allowed_labels", () => {
  it("an edit touches Allegis Document / Status & Execution / Catalog Review only - never Handling", () => {
    const v = validateEdit({ kind: "k1", entities: ["MTV-II"], fiscal_year: 2025, period: "fy", stage: "fully_executed", executed_date: "2025-03-31" });
    expect(v.ok).toBe(true);
    const m = buildEditMods((v as unknown as { value: never }).value, ME);
    const ids = (m.labelModifications as { labelId: string }[]).map((x) => x.labelId);
    expect(ids).not.toContain(LABEL_IDS.handling);
    expect(m.labels.every((l) => (LABELS_THE_APP_MAY_WRITE as readonly string[]).includes(l))).toBe(true);
    expect(m.labels).toEqual(["doc", "exec", "review"]);
    const review = (m.labelModifications as { labelId: string; fieldModifications: Record<string, unknown>[] }[]).find((x) => x.labelId === LABEL_IDS.review)!;
    expect(review.fieldModifications[0]).toEqual({ fieldId: SCHEMA.review.fields.status.field_id, setSelectionValues: [SCHEMA.review.fields.status.choices!.confirmed] });
    expect(review.fieldModifications[1]).toEqual({ fieldId: SCHEMA.review.fields.reviewed_by.field_id, setUserValues: [ME] });
  });
  it("a Handling field in the request is refused (any spelling), and so is any unknown field", () => {
    for (const k of ["tier", "Handling", "contains", "lp_pii", "pii_lp"]) expect(validateEdit({ kind: "k1", [k]: "normal" })).toEqual({ ok: false, reason: "handling_not_editable" });
    expect(validateEdit({ workstream: "tax" })).toMatchObject({ ok: false, reason: "field_not_editable:workstream" });
    expect(validateEdit({ kind: "not_a_kind" })).toMatchObject({ ok: false, reason: "bad_value:kind" });
    expect(validateEdit({ executed_date: "2025-01-01" })).toMatchObject({ ok: false, reason: "executed_date_needs_fully_executed" });
  });
  it("Parties / Status are refused until those labels are published (never written to a field that doesn't exist)", () => {
    if (!("status" in SCHEMA.exec.fields)) expect(validateEdit({ status: "final" })).toEqual({ ok: false, reason: "label_not_published:exec.status" });
    if (!SCHEMA.parties) expect(validateEdit({ issuing_entity: "MTV-II" })).toEqual({ ok: false, reason: "label_not_published:parties.issuing_entity" });
  });
  it("the single-edit route refuses a Handling field before touching Drive or the DB", async () => {
    const d = drive({}); const { D, execs } = fakeDb([F1]);
    const r = await editOne({ file_id: F1, set: { kind: "k1", tier: "secret" } }, { session, db: D, fetch: d.f });
    expect(r).toEqual({ status: 400, body: { error: "bad_input", reason: "handling_not_editable" } });
    expect(d.calls.length).toBe(0); expect(execs.length).toBe(0);
  });
  it("single edit: in scope + live check as the user -> one modifyLabels + one review_event (source find_single)", async () => {
    const d = drive({}); const { D, execs } = fakeDb([F1]);
    const r = await editOne({ file_id: F1, set: { kind: "invoice" } }, { session, db: D, fetch: d.f });
    expect(r.status).toBe(200);
    expect(d.calls.filter((c) => c.url.includes("modifyLabels")).length).toBe(1);
    expect(d.calls[0].body).toContain("capabilities%2FcanModifyLabels");
    expect(execs[0].text).toContain("INSERT INTO app.review_event");
    expect(execs[0].params).toContain("find_single");
    expect(execs[0].params).toContain(JSON.stringify({ kind: "invoice" }));
  });
  it("single edit: a file the user can't open is not written", async () => {
    const d = drive({ [F1]: 404 }); const { D, execs } = fakeDb([F1]);
    const r = await editOne({ file_id: F1, set: { kind: "invoice" } }, { session, db: D, fetch: d.f });
    expect(r).toEqual({ status: 403, body: { error: "no_access" } });
    expect(d.calls.some((c) => c.url.includes("modifyLabels"))).toBe(false); expect(execs.length).toBe(0);
  });
});

describe("G-E3 test_bulk_respects_500_cap", () => {
  it(`more than ${BULK_CAP} files is refused before anything is read or written`, async () => {
    const d = drive({}); const { D, execs } = fakeDb([]);
    const ids = Array.from({ length: BULK_CAP + 1 }, (_, i) => `x${String(i).padStart(12, "0")}`);
    const r = await editBulk({ file_ids: ids, set: { kind: "k1" }, confirm: true }, { session, db: D, fetch: d.f });
    expect(r).toEqual({ status: 400, body: { error: "too_many_files", cap: 500, got: 501 } });
    expect(d.calls.length).toBe(0); expect(execs.length).toBe(0);
  });
  it("exactly 500 is allowed (preview, no writes)", async () => {
    const d = drive({}); const { D } = fakeDb([]);
    const ids = Array.from({ length: BULK_CAP }, (_, i) => `x${String(i).padStart(12, "0")}`);
    const r = await editBulk({ file_ids: ids, set: { kind: "k1" } }, { session, db: D, fetch: d.f });
    expect(r.status).toBe(200); expect(r.body.preview).toBe(true); expect(d.calls.length).toBe(0);
  });
  it("bulk only offers kind / entity / fiscal year / status", async () => {
    const { D } = fakeDb([F1]);
    const r = await editBulk({ file_ids: [F1], set: { period: "fy" }, confirm: true }, { session, db: D });
    expect(r.body).toEqual({ error: "bad_input", reason: "not_a_bulk_field:period" });
  });
  it("confirmed bulk: skips no-access and out-of-scope files, retries a 503, reports done / skipped / failed", async () => {
    const d = drive({ [F2]: 404 }, { [F1]: [503, 200] }); const { D, execs } = fakeDb([F1, F2]);
    const r = await editBulk({ file_ids: [F1, F2, F3], set: { fiscal_year: 2024 }, confirm: true }, { session, db: D, fetch: d.f, sleep: async () => {} });
    expect(r.body.report).toEqual({ done: 1, skipped_no_access: 1, skipped_check_failed: 0, skipped_not_in_scope: 1, failed: 0, events_failed: false });
    expect(d.calls.filter((c) => c.url.includes(`${F1}/modifyLabels`)).length).toBe(2); // one retry
    expect(d.calls.some((c) => c.url.includes(`${F2}/modifyLabels`))).toBe(false);     // never written
    expect(execs[0].params).toContain("find_bulk");
  });
  it("bulkWrite: a 403 permission error is 'no access' (not retried); 4 failed retries become 'failed'", async () => {
    const d = drive({}, { [F1]: [403], [F2]: [500, 500, 500, 500, 500] });
    const r = await bulkWrite("tok", [F1, F2], [], { fetch: d.f, sleep: async () => {} });
    expect(r.skippedNoAccess).toEqual([F1]);
    expect(r.failed).toEqual([{ file_id: F2, drive_status: 500 }]);
  });
});
