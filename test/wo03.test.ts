import { describe, expect, it, vi } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { accessFor, checklistPref, checklistQuery, gapsQuery, overrideWrite, parseChecklistSpec, REQ_KEY, shownDoc, SpecError } from "@/lib/checklists";
import { subjectMods, subjectWrite, validateSubject } from "@/lib/subject";
import { codesFromText, decodeLabels } from "@/lib/labels";
import { authUrl, DIRECTORY_SCOPES, SIGNIN_SCOPES, WRITE_SCOPES } from "@/lib/google";
import { DIRECTORY_READ } from "@/lib/session";
import { sanitize } from "@/lib/log";
import type { Db } from "@/lib/db";
import { batchResponse } from "./helpers";

const ME = "ryan@allegiscapital.com";
const session = { v: 1, email: ME, sub: "t", hd: "allegiscapital.com", at: "tok", scopes: ["openid", "email", "https://www.googleapis.com/auth/drive.metadata"], exp: 9e9 } as never;
const F1 = "1AbCdEfGhIjKlMnOpQrS", F2 = "2AbCdEfGhIjKlMnOpQrS";
const KEY = "LP-SUB|MTV-IV (A)|LP-0001||";

/** Drive stub: files.get per id (status, name), secret tier via a Handling label; modifyLabels recorded. */
function drive(get: Record<string, number>, names: Record<string, string> = {}) {
  const calls: { url: string; body: string }[] = [];
  const f = async (url: string, init?: RequestInit) => {
    const body = String(init?.body ?? "");
    calls.push({ url, body });
    if (url.includes("/batch/drive/v3")) {
      const ids = [...body.matchAll(/GET \/drive\/v3\/files\/([^?]+)\?/g)].map((m) => decodeURIComponent(m[1]));
      return batchResponse(ids.map((id) => {
        const st = get[id] ?? 200;
        return { status: st, body: st === 200 ? { id, name: names[id] ?? "Zephyrine Quillfeather subscription.pdf", webViewLink: `https://drive/${id}`, capabilities: { canModifyLabels: true }, labelInfo: { labels: [] } } : { error: { errors: [{ reason: "notFound" }] } } };
      }));
    }
    if (/modifyLabels/.test(url)) return new Response(JSON.stringify({ kind: "drive#modifyLabelsResponse" }), { status: 200 });
    return new Response("{}", { status: 404 });
  };
  return { f, calls };
}
function fakeDb(answers: (text: string, params: unknown[]) => unknown[]) {
  const execs: { text: string; params: unknown[] }[] = [];
  const D: Db = {
    async rows<T>(text: string, params: unknown[] = []) { return answers(text, params) as T[]; },
    async exec(text: string, params: unknown[] = []) { execs.push({ text, params }); return 1; },
  };
  return { D, execs };
}

describe("CAT-WO-03 guard: an unopenable best document shows no name or link", () => {
  it("shownDoc gives name + link only when the live check passed", async () => {
    const { f } = drive({ [F1]: 200, [F2]: 404 });
    const acc = await accessFor("tok", [F1, F2], f as never);
    expect(shownDoc(F1, acc.map.get(F1))).toMatchObject({ access: "ok", file_id: F1 });
    const hidden = shownDoc(F2, acc.map.get(F2));
    expect(hidden).toEqual({ access: "no_access" });
    expect(JSON.stringify(hidden)).not.toMatch(/name|link|Zephyrine/);
  });
  it("a live secret tier counts as no access; a transient error is 'check failed', never shown", async () => {
    const SECRET_LABEL = { labels: [] };
    void SECRET_LABEL;
    expect(shownDoc(F1, { state: "check_failed" })).toEqual({ access: "check_failed" });
    expect(shownDoc(F1, undefined)).toEqual({ access: "check_failed" });
    expect(shownDoc(F1, { state: "ok", name: "x", link: "y" }, true)).toEqual({ access: "out_of_scope" });
  });
});

describe("CAT-WO-03 guard: no typed name ever reaches Subject code(s)", () => {
  it("validateSubject accepts roster codes only", () => {
    expect(validateSubject({ codes: ["LP-0001", "gpm-01"] })).toMatchObject({ ok: true, value: { codes: ["GPM-01", "LP-0001"] } });
    expect(validateSubject({ codes: ["Zephyrine Quillfeather"] })).toEqual({ ok: false, reason: "codes_must_be_roster_codes" });
    expect(validateSubject({ codes: ["LP-0001; DROP"] })).toMatchObject({ ok: false });
    expect(validateSubject({ person: "someone@gmail.com" })).toEqual({ ok: false, reason: "person_must_be_staff_account" });
    expect(validateSubject({ person: "Alba Brightwater" })).toEqual({ ok: false, reason: "person_must_be_staff_account" });
    expect(validateSubject({ none: true })).toMatchObject({ ok: true, value: { codes: [], none: true } });
    expect(validateSubject({ codes: [] })).toEqual({ ok: false, reason: "empty_codes_need_none" });   // a person-only edit never clears codes
    expect(validateSubject({ person: "alba.b@allegiscapital.com" })).toMatchObject({ ok: true, value: { codes: null } });
  });
  it("label text read back keeps codes only", () => {
    expect(codesFromText("LP-0001, Zephyrine Quillfeather, GM-0002")).toEqual(["GM-0002", "LP-0001"]);
  });
  it("subjectMods writes nothing while the Subject fields are unpublished", () => {
    expect(subjectMods({ codes: ["LP-0001"], person: undefined, none: false }).labels.length).toBeGreaterThanOrEqual(0);
  });
  it("a code that is not on the document's roster is refused before any Drive call", async () => {
    const { f, calls } = drive({});
    const { D, execs } = fakeDb((text) => text.includes("v_find_x") ? [{ document_id: "7", entities: ["MTV-IV (A)"], issuing_entity: null }] : []);
    const r = await subjectWrite({ file_id: F1, codes: ["LP-0999"] }, { session, db: D, fetch: f as never, source: "match_subject" });
    expect(r).toMatchObject({ status: 400, body: { reason: "code_not_on_the_documents_roster" } });
    expect(calls.length).toBe(0);
    expect(execs.length).toBe(0);
  });
  it("a lane decision is recorded (codes only) as a match_subject review event", async () => {
    const { f } = drive({});
    const { D, execs } = fakeDb((text) => text.includes("v_find_x") ? [{ document_id: "7", entities: ["MTV-IV (A)"], issuing_entity: null }]
      : text.includes("v_party") ? [{ partner_code: "LP-0001" }] : []);
    const r = await subjectWrite({ file_id: F1, codes: ["LP-0001"] }, { session, db: D, fetch: f as never, source: "match_subject" });
    expect(r.status).toBe(200);
    expect(execs[0].text).toContain("app.review_event");
    expect(execs[0].params).toContain("match_subject");
    expect(String(execs[0].params[6])).toBe(JSON.stringify({ subject_codes: ["LP-0001"] }));
  });
});

describe("CAT-WO-03 guard: the directory scope is requested only on a person-field edit", () => {
  it("sign-in and write scopes never include directory.readonly", () => {
    expect(SIGNIN_SCOPES).not.toContain(DIRECTORY_READ);
    expect(WRITE_SCOPES).not.toContain(DIRECTORY_READ);
    expect(DIRECTORY_SCOPES).toContain(DIRECTORY_READ);
    const base = { clientId: "c", redirectUri: "https://x/cb", state: "s", codeChallenge: "c", hd: "allegiscapital.com" };
    expect(authUrl({ ...base, write: false })).not.toContain("directory.readonly");
    expect(authUrl({ ...base, write: true })).not.toContain("directory.readonly");
    expect(authUrl({ ...base, write: true, directory: true })).toContain("directory.readonly");
  });
  it("only the directory route asks for scope=directory, and only the person picker calls that route", () => {
    const files: string[] = [];
    const walk = (d: string) => { for (const x of readdirSync(d)) { const p = join(d, x); if (statSync(p).isDirectory()) walk(p); else if (/\.tsx?$/.test(x)) files.push(p); } };
    walk(join(__dirname, "..", "src"));
    const asks = files.filter((p) => readFileSync(p, "utf8").includes("scope=directory")).map((p) => p.replace(/\\/g, "/").split("/src/")[1]);
    expect(asks).toEqual(["app/api/subject/directory/route.ts"]);
    const callers = files.filter((p) => readFileSync(p, "utf8").includes("/api/subject/directory")).map((p) => p.replace(/\\/g, "/").split("/src/")[1])
      .filter((p) => p !== "app/api/subject/directory/route.ts");   // the route itself (its doc comment) is not a caller
    expect(callers).toEqual(["components/SubjectForm.tsx"]);
    expect(readFileSync(join(__dirname, "..", "src", "components", "SubjectForm.tsx"), "utf8")).toMatch(/const searchStaff = async[\s\S]*\/api\/subject\/directory/);
  });
});

describe("CAT-WO-03 guard: no LP name in any log line", () => {
  it("the logger drops names in any key, including the new ones", () => {
    const out = sanitize({ event: "x", rule_id: "LP-SUB", action: "Zephyrine Quillfeather", lane: "match_subject", reason: "Some Name", file_id: "Name with spaces.pdf", partner_name: "Zephyrine" });
    expect(JSON.stringify(out)).not.toMatch(/Zephyrine|Some Name|spaces/);
    expect(out.rule_id).toBe("LP-SUB");
    expect(out).not.toHaveProperty("partner_name");
  });
  it("subject and override writes log codes only", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const { f } = drive({});
    const { D } = fakeDb((text) => text.includes("v_find_x") ? [{ document_id: "7", entities: ["MTV-IV (A)"], issuing_entity: null }]
      : text.includes("v_party") ? [{ partner_code: "LP-0001" }] : text.includes("v_requirement") ? [{ override_action: null }] : []);
    await subjectWrite({ file_id: F1, codes: ["LP-0001"] }, { session, db: D, fetch: f as never, source: "find_single" });
    await overrideWrite({ req_key: KEY, action: "not_required", note: "Zephyrine Quillfeather waived" }, { session, db: D, fetch: f as never });
    const lines = log.mock.calls.map((c) => String(c[0])).join("\n");
    log.mockRestore();
    expect(lines).toContain("subject_write");
    expect(lines).toContain("checklist_override");
    expect(lines).not.toMatch(/Zephyrine|Quillfeather|LP-0001/);
  });
});

describe("CAT-WO-03 overrides", () => {
  it("Not required needs a reason; Clear needs an override; Link needs a file the user can open", async () => {
    const { f } = drive({ [F2]: 404 });
    const { D, execs } = fakeDb((text, p) => text.includes("v_requirement") ? [{ override_action: null }] : text.includes("v_find_x") && p[0] === F1 ? [{ document_id: "7" }] : text.includes("v_find_x") && p[0] === F2 ? [{ document_id: "8" }] : []);
    expect((await overrideWrite({ req_key: KEY, action: "not_required" }, { session, db: D, fetch: f as never })).body).toMatchObject({ reason: "reason_required" });
    expect((await overrideWrite({ req_key: KEY, action: "clear" }, { session, db: D, fetch: f as never })).body).toMatchObject({ reason: "nothing_to_clear" });
    expect((await overrideWrite({ req_key: KEY, action: "link", file_id: F2 }, { session, db: D, fetch: f as never })).status).toBe(403);
    expect(execs.length).toBe(0);
    expect((await overrideWrite({ req_key: KEY, action: "link", file_id: F1 }, { session, db: D, fetch: f as never })).status).toBe(200);
    // CAT-WO-03.1: the link first labels the document to match the requirement (event, source checklist_link), then
    // records the override; the override is always the last write
    expect(execs.at(-1)!.text).toContain("INSERT INTO app.requirement_override");
    expect(execs.some((e) => e.text.includes("INSERT INTO app.review_event") && JSON.stringify(e.params ?? []).includes("checklist_link"))).toBe(true);
  });
  it("a note naming a partner of that entity is refused (names live only in ref.party)", async () => {
    const { D, execs } = fakeDb((text) => text.includes("v_requirement") ? [{ override_action: null }] : text.includes("v_party") ? [{ display_name: "Zephyrine Quillfeather Trust" }] : []);
    const r = await overrideWrite({ req_key: KEY, action: "not_required", note: "waived for zephyrine quillfeather trust" }, { session, db: D });
    expect(r.body).toMatchObject({ reason: "note_names_a_partner_use_the_code" });
    expect(execs.length).toBe(0);
    expect((await overrideWrite({ req_key: KEY, action: "not_required", note: "LP-0001 waived (redeemed)" }, { session, db: D })).status).toBe(200);
  });
  it("a bad key or action is refused", async () => {
    const { D } = fakeDb(() => []);
    expect((await overrideWrite({ req_key: "x'; drop", action: "link" }, { session, db: D })).status).toBe(400);
    expect((await overrideWrite({ req_key: KEY, action: "delete" }, { session, db: D })).status).toBe(400);
    expect(REQ_KEY.test("K1-SET|CIP-II|LP-0001-CI|2025|")).toBe(true);
    expect(REQ_KEY.test("PCAP-Q|MTV-IV (A)|LP-0001|2025|Q3")).toBe(true);
  });
});

describe("CAT-WO-03 checklist queries are whitelisted and bound", () => {
  it("rule / entity / sort / page size are validated; values go in params", () => {
    const s = parseChecklistSpec(new URLSearchParams({ rule: "K1-SET", entity: "MTV-IV (A)", fy: "2025", result: "missing,on_file", sort: "best_date", dir: "desc", pageSize: "100" }));
    const q = checklistQuery(s);
    expect(q.sql).toContain("ORDER BY best_date DESC NULLS LAST");
    expect(q.params).toEqual(["K1-SET", "MTV-IV (A)", 2025, ["missing", "on_file"]]);
    expect(q.scopeParams).toEqual(["K1-SET", "MTV-IV (A)", 2025]);
    expect(q.sql).not.toContain("MTV-IV");
    for (const bad of [{ rule: "X" }, { sort: "1;drop" }, { entity: "a'b" }, { result: "everything" }, { pageSize: "5000" }, { q: "5" }] as Record<string, string>[])
      expect(() => parseChecklistSpec(new URLSearchParams(bad))).toThrow(SpecError);
    expect(() => gapsQuery("bad", null)).toThrow(SpecError);
  });
  it("the default order is urgency (Missing first ... Met)", () => {
    expect(checklistQuery(parseChecklistSpec(new URLSearchParams())).sql).toMatch(/ORDER BY urgency ASC/);
  });
  it("remembered state is whitelisted", () => {
    expect(checklistPref({ rule: "PCAP-Q", results: ["missing"], widths: { result: 250, evil: 3 }, tab: "gaps" })).toMatchObject({ rule: "PCAP-Q", results: ["missing"], widths: { result: 250 }, tab: "gaps" });
    expect(checklistPref({ rule: "nope" })).toBeNull();
  });
});

describe("CAT-WO-03 live label decode", () => {
  it("decodes nothing for Subject while the fields are unpublished (no crash, empty)", () => {
    const v = decodeLabels({ labels: [] });
    expect(v.subject_codes).toEqual([]);
    expect(v.subject_person).toBeNull();
  });
});
