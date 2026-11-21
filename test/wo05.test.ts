import { describe, expect, it } from "vitest";
import { buildWhere, parseSpec, SpecError, EXPORT_COLS } from "@/lib/find";
import { postingsFor } from "@/lib/postings";
import { buildLabelsPanel } from "@/lib/labelinfo";
import { sanitize } from "@/lib/log";
import type { Db } from "@/lib/db";

function fakeDb(handler: (sql: string, params: unknown[]) => unknown[]): Db {
  return { rows: async (sql: string, params: unknown[] = []) => handler(sql, params) } as unknown as Db;
}

describe("CAT-WO-05 · Find: Published To columns and filters", () => {
  it("filters channels with bound values only and refuses bad codes", () => {
    const b = buildWhere(parseSpec({ filters: { published_channel: ["lp_portal"] } }));
    expect(b.where).toContain("published_channels");
    expect(b.params).toEqual([["lp_portal"]]);
    expect(() => parseSpec({ filters: { published_channel: ["x'; DROP TABLE y; --"] } })).toThrow(SpecError);
  });
  it("Posted date is a date range like Issued date", () => {
    const b = buildWhere(parseSpec({ filters: { published_date: { from: "2026-01-01", to: "2026-06-30" } } }));
    expect(b.where).toMatch(/published_date >= \$1::date/);
    expect(b.params).toEqual(["2026-01-01", "2026-06-30"]);
  });
  it("Portal kind conflict is a boolean switch onto the conflict view", () => {
    expect(buildWhere(parseSpec({ filters: { portal_kind_conflict: true } })).where).toContain("app.v_portal_kind_conflict");
    expect(() => parseSpec({ filters: { portal_kind_conflict: "1 OR 1=1" } })).toThrow(SpecError);
  });
  it("exports codes and dates only", () => {
    expect(EXPORT_COLS).toEqual(expect.arrayContaining(["published_channels", "published_date", "published_ids"]));
    expect(EXPORT_COLS.some((c) => /name|partner/.test(c))).toBe(false);
  });
});

describe("CAT-WO-05 · side panel postings (no partner, no name)", () => {
  it("returns channel, date, posting ID and type; never a partner column", async () => {
    const seen: string[] = [];
    const D = fakeDb((sql) => {
      seen.push(sql);
      if (sql.includes("app.v_find_x")) return [{ document_id: "42", published_channels: ["lp_portal"], published_date: "2026-08-15", published_ids: ["LPD-12"] }];
      return [{ posting_id: "LPD-12", channel: "lp_portal", posted_date: "2026-08-15", doc_type: "CRR", fiscal_year: 2026, fiscal_quarter: 2, match: "file_id" }];
    });
    const r = await postingsFor(D, "1AbCdEfGhIjKlMnOpQrStUvWx");
    expect(r.status).toBe(200);
    expect((r.body.postings as unknown[]).length).toBe(1);
    expect(seen.join(" ")).not.toMatch(/partner|name/i);
    expect(JSON.stringify(r.body)).not.toMatch(/partner/i);
  });
  it("refuses a malformed file ID and a file Find does not show", async () => {
    expect((await postingsFor(fakeDb(() => []), "bad id!")).status).toBe(400);
    expect((await postingsFor(fakeDb(() => []), "1AbCdEfGhIjKlMnOpQrStUvWx")).status).toBe(403);
  });
  it("logs codes only", () => {
    const s = sanitize({ event: "postings_read", file_id: "1AbCdEfGhIjKlMnOpQrStUvWx", document_id: "42", count: 1 });
    expect(JSON.stringify(s)).not.toMatch(/name/);
  });
});

describe("CAT-WO-05 · Labels panel: L10 Published To", () => {
  it("shows L10 (planned until published) with its three fields, machine-set", () => {
    const L = buildLabelsPanel({ entity: new Map(), portco: new Map() });
    const p = L.find((x) => x.key === "published")!;
    expect(p.title).toBe("Published To (L10)");
    expect(p.fields.map((f) => f.key)).toEqual(["channel", "posted_date", "posting_id"]);
    expect(p.fields.every((f) => f.editable === "machine")).toBe(true);
    expect(p.fields[0].choices.map((c) => c.code)).toEqual(["lp_portal", "gp_portal", "datum", "email"]);
  });
});
