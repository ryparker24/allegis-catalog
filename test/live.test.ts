import { describe, expect, it } from "vitest";
import { liveCheck, applyLiveCheck } from "@/lib/live";
import { LABEL_IDS } from "@/lib/labels";
import schema from "@/lib/labels_schema.json";
import { batchResponse } from "./helpers";

const ids = ["AAAAAAAAAAAAAAAAAAAAA1", "BBBBBBBBBBBBBBBBBBBBB2", "CCCCCCCCCCCCCCCCCCCCC3"];
const S = schema as any;
const docLabel = (kind: string) => ({ id: LABEL_IDS.doc, fields: { [S.doc.fields.kind.field_id]: { selection: [S.doc.fields.kind.choices[kind]] } } });
const tierLabel = (t: string) => ({ id: LABEL_IDS.handling, fields: { [S.handling.fields.tier.field_id]: { selection: [S.handling.fields.tier.choices[t]] } } });
const ok = (id: string, kind = "k1", tier = "normal") => ({ status: 200, body: { id, name: `name-${id}`, webViewLink: `https://drive.google.com/file/d/${id}/view`, labelInfo: { labels: [docLabel(kind), tierLabel(tier)] } } });
const notFound = { status: 404, body: { error: { code: 404, message: "File not found", errors: [{ reason: "notFound" }] } } };

describe("G3 test_no_access_file_is_dropped_and_counted", () => {
  it("stubbed Drive batch: 404 for one id -> that row is dropped, counted as 'not shown (no access)', others shown", async () => {
    let sentBody = "";
    const fetchStub = async (_u: string, init?: RequestInit) => { sentBody = String(init?.body); return batchResponse([ok(ids[0]), notFound, ok(ids[2])]); };
    const rows = ids.map((file_id) => ({ file_id, kind: "k1", tier: "normal" }));
    const r = await liveCheck("ya29.test", rows, fetchStub);
    expect(r.rows.map((x) => x.db.file_id)).toEqual([ids[0], ids[2]]);
    expect(r.rows.some((x) => x.db.file_id === ids[1])).toBe(false);
    expect(r.notShown).toEqual({ noAccess: 1, checkFailed: 0, total: 1 });
    // ONE batch request carrying all three files.get calls, with labelInfo requested
    expect(sentBody.match(/GET \/drive\/v3\/files\//g)?.length).toBe(3);
    expect(sentBody).toContain("labelInfo");
  });

  it("403 insufficientFilePermissions counts as no access; 429/5xx count as check failed - none are shown", () => {
    const m = new Map([
      [ids[0], { status: 403, body: { error: { errors: [{ reason: "insufficientFilePermissions" }] } } }],
      [ids[1], { status: 429, body: null }],
      [ids[2], { status: 503, body: null }],
    ]);
    const r = applyLiveCheck(ids.map((file_id) => ({ file_id })), m);
    expect(r.rows).toHaveLength(0);
    expect(r.notShown).toEqual({ noAccess: 1, checkFailed: 2, total: 3 });
  });

  it("a file whose LIVE Handling tier is secret is never shown", () => {
    const m = new Map([[ids[0], ok(ids[0], "k1", "secret")]]);
    const r = applyLiveCheck([{ file_id: ids[0], tier: "normal" }], m);
    expect(r.rows).toHaveLength(0);
    expect(r.notShown.noAccess).toBe(1);
  });

  it("live label values are displayed; a DB/live difference is marked 'changed in Drive'", () => {
    const m = new Map([[ids[0], ok(ids[0], "tax_return")]]);
    const r = applyLiveCheck([{ file_id: ids[0], kind: "k1", tier: "normal" }], m);
    expect(r.rows[0].live.kind).toBe("tax_return");
    expect(r.rows[0].changed).toContain("kind");
  });

  it("an expired token (401 for every item) is reported as session expired, not as no access", () => {
    const m = new Map(ids.map((id) => [id, { status: 401, body: null }]));
    const r = applyLiveCheck(ids.map((file_id) => ({ file_id })), m);
    expect(r.sessionExpired).toBe(true);
    expect(r.rows).toHaveLength(0);
  });
});
