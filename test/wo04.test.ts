import { describe, expect, it } from "vitest";
import { buildWhere, parseSpec, SpecError } from "@/lib/find";
import { validateAction, act, MERGE_CAP } from "@/lib/versions";
import { sanitize } from "@/lib/log";
import { buildLabelsPanel } from "@/lib/labelinfo";
import type { Db } from "@/lib/db";
import { batchResponse } from "./helpers";

describe("CAT-WO-04 · Find: Current versions only (R-029) and the Versions columns", () => {
  it("is off by default: a spec without the switch adds no version condition", () => {
    expect(buildWhere(parseSpec({ filters: {} })).where).not.toMatch(/version_role/);
  });
  it("when on, drops superseded / redline / draft-of members but keeps amendments and documents with no family", () => {
    const w = buildWhere(parseSpec({ filters: { current_only: true } })).where;
    expect(w).toContain("version_role IS NULL OR version_role IN ('current', 'amends')");
  });
  it("refuses anything but a boolean, and filters the Version role / member count with bound values only", () => {
    expect(() => parseSpec({ filters: { current_only: "yes; DROP TABLE x" } })).toThrow(SpecError);
    const b = buildWhere(parseSpec({ filters: { version_role: ["superseded"], versions: "3" } }));
    expect(b.where).toContain("version_role = ANY($1::text[])");
    expect(b.where).toContain("versions = $2::int");
    expect(b.params).toEqual([["superseded"], 3]);
    expect(() => parseSpec({ filters: { versions: "3 OR 1=1" } })).toThrow(SpecError);
  });
});

describe("CAT-WO-04 · version actions", () => {
  it("accepts codes and catalog numbers only", () => {
    expect(validateAction({ action: "mark_current", document: "123" }).ok).toBe(true);
    expect(validateAction({ action: "mark_current", document: "12a" })).toEqual({ ok: false, reason: "bad_document" });
    expect(validateAction({ action: "delete_all" })).toEqual({ ok: false, reason: "bad_action" });
    expect(validateAction({ action: "amends", document: "5", base: "5" })).toEqual({ ok: false, reason: "bad_base" });
    expect(validateAction({ action: "move", document: "5", target: "6" }).ok).toBe(true);
    expect(validateAction({ action: "merge", documents: ["1"] })).toEqual({ ok: false, reason: "merge_needs_two" });
    expect(validateAction({ action: "merge", documents: Array.from({ length: MERGE_CAP + 1 }, (_, i) => String(i + 1)) })).toEqual({ ok: false, reason: "bad_documents" });
    expect(validateAction({ action: "split", family: "9", documents: ["1", "x"] })).toEqual({ ok: false, reason: "bad_documents" });
  });

  const session = { email: "ryan@allegiscapital.com", at: "tok", hd: "allegiscapital.com" } as never;
  const fakeDb = (files: { document_id: string; file_id: string }[], inserted: unknown[][]): Db => ({
    rows: async (sql: string) => (sql.includes("FROM app.v_find_x") ? files : sql.includes("v_family_member") ? [{ document_id: "1", family_id: "9" }] : []) as never,
    exec: async (_sql: string, p: unknown[] = []) => { inserted.push(p); return 1; },
  });
  const drive = (ok: Set<string>) => (async (_url: string, init?: RequestInit) => {
    // a Drive batch, answered in request order: 200 (opens) or 404
    const ids = [...String(init?.body ?? "").matchAll(/files\/([A-Za-z0-9_-]+)\?/g)].map((m) => m[1]);
    return batchResponse(ids.map((id) => (ok.has(id) ? { status: 200, body: { id, name: "n", webViewLink: "l" } } : { status: 404, body: {} })));
  }) as never;

  it("refuses when any touched document does not open for the user, and writes nothing", async () => {
    const ins: unknown[][] = [];
    const files = [{ document_id: "1", file_id: "aaaaaaaaaaaa" }, { document_id: "2", file_id: "bbbbbbbbbbbb" }];
    const r = await act({ action: "merge", documents: ["1", "2"] }, { session, db: fakeDb(files, ins), fetch: drive(new Set(["aaaaaaaaaaaa"])) });
    expect(r.status).toBe(403);
    expect(ins).toHaveLength(0);
  });
  it("records one version_link event with codes / numbers only when every document opens", async () => {
    const ins: unknown[][] = [];
    const files = [{ document_id: "1", file_id: "aaaaaaaaaaaa" }, { document_id: "2", file_id: "bbbbbbbbbbbb" }];
    const r = await act({ action: "merge", documents: ["1", "2"] }, { session, db: fakeDb(files, ins), fetch: drive(new Set(["aaaaaaaaaaaa", "bbbbbbbbbbbb"])) });
    expect(r.status).toBe(200);
    expect(ins).toHaveLength(1);
    expect(JSON.parse(String(ins[0][3]))).toEqual({ version: { action: "merge", documents: ["1", "2"] } });
  });
  it("logs codes only (an action name is a code; a file name never passes)", () => {
    expect(sanitize({ action: "mark_current", document_id: "123", reason: "Zyxwv Trust Side Letter.pdf" })).toEqual({ action: "mark_current", document_id: "123", reason: "[redacted]" });
  });
});

describe("CAT-WO-04 · Labels panel", () => {
  it("shows L6 Version (planned until published) with its four fields and the five roles", () => {
    const L = buildLabelsPanel({ entity: new Map(), portco: new Map() }).find((x) => x.key === "version")!;
    expect(L.title).toBe("Version (L6)");
    expect(L.fields.map((f) => f.key)).toEqual(["family", "role", "supersedes", "amends"]);
    expect(L.fields.find((f) => f.key === "role")!.choices.map((c) => c.meaning)).toEqual(["Current", "Superseded", "Amends", "Redline / compare", "Draft of"]);
  });
});
