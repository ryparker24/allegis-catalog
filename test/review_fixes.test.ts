/** Tests for the fixes made after the coder + CISO review (follow-up order item 2). */
import { describe, expect, it } from "vitest";
import { checkSameOrigin } from "@/lib/guard";
import { sanitize } from "@/lib/log";
import { liveCheck } from "@/lib/live";
import { isTransient } from "@/lib/google";
import { buildWhere, SEED_VIEWS } from "@/lib/find";

const ENVO = { APP_ORIGIN: "https://catalog.allegis.app" } as never;
const req = (method: string, h: Record<string, string>) => new Request("https://catalog.allegis.app/api/review/confirm", { method, headers: h });

describe("CSRF: state-changing requests must be same-origin JSON", () => {
  it("allows GET without Origin", () => expect(checkSameOrigin(req("GET", {}), ENVO)).toBeNull());
  it("refuses POST with no Origin", () => expect(checkSameOrigin(req("POST", { "content-type": "application/json" }), ENVO)).toBe("bad_origin"));
  it("refuses POST from a sibling subdomain", () =>
    expect(checkSameOrigin(req("POST", { origin: "https://other.allegis.app", "content-type": "application/json" }), ENVO)).toBe("bad_origin"));
  it("refuses a text/plain form body from the right origin", () =>
    expect(checkSameOrigin(req("POST", { origin: "https://catalog.allegis.app", "content-type": "text/plain" }), ENVO)).toBe("bad_content_type"));
  it("refuses DELETE from another origin", () => expect(checkSameOrigin(req("DELETE", { origin: "https://x.example" }), ENVO)).toBe("bad_origin"));
  it("allows same-origin JSON POST and same-origin DELETE", () => {
    expect(checkSameOrigin(req("POST", { origin: "https://catalog.allegis.app", "content-type": "application/json; charset=utf-8" }), ENVO)).toBeNull();
    expect(checkSameOrigin(req("DELETE", { origin: "https://catalog.allegis.app" }), ENVO)).toBeNull();
  });
});

describe("log sanitizer: per-key shapes", () => {
  it("redacts file-name-shaped values even under allowed keys", () => {
    const out = sanitize({ event: "x", reason: "Smith_Family_Trust_K1_2025.pdf", status: "Investor_LLC", file_id: "Capital Statement.pdf", outcome: { a: 1 } });
    expect(out).toEqual({ event: "x", reason: "[redacted]", status: "[redacted]", file_id: "[redacted]", outcome: "[redacted]" });
  });
  it("keeps codes and Drive IDs", () => {
    const out = sanitize({ event: "review_write", reason: "token_exchange_failed_400", file_id: "1AbC-dEf_GhIjKlMnOpQrStUvWxYz012", labels: ["exec", "review"], document_id: 1234 });
    expect(out).toEqual({ event: "review_write", reason: "token_exchange_failed_400", file_id: "1AbC-dEf_GhIjKlMnOpQrStUvWxYz012", labels: ["exec", "review"], document_id: 1234 });
  });
});

describe("live check: batch-level failures are 'check failed', not 'no access'", () => {
  const rows = ["AAAAAAAAAAAAAAAAAAAAA1", "BBBBBBBBBBBBBBBBBBBBB2"].map((file_id) => ({ file_id, kind: null, tier: "normal" }));
  it("whole batch 400/403 -> all check failed", async () => {
    for (const st of [400, 403]) {
      const r = await liveCheck("ya29.t", rows, async () => new Response("{}", { status: st }));
      expect(r.notShown).toEqual({ noAccess: 0, checkFailed: 2, total: 2 });
      expect(r.sessionExpired).toBe(false);
    }
  });
  it("whole batch 401 -> session expired", async () => {
    const r = await liveCheck("ya29.t", rows, async () => new Response("{}", { status: 401 }));
    expect(r.sessionExpired).toBe(true);
  });
  it("per-item 403 dailyLimitExceeded / userRateLimitExceeded are transient", () => {
    for (const reason of ["dailyLimitExceeded", "userRateLimitExceeded", "rateLimitExceeded"])
      expect(isTransient({ status: 403, body: { error: { errors: [{ reason }] } } })).toBe(true);
    expect(isTransient({ status: 403, body: { error: { errors: [{ reason: "insufficientFilePermissions" }] } } })).toBe(false);
  });
});

describe("seed views (designs v0.1)", () => {
  it("are the four design views, all primary-copy-only, fiscal years stored as strings like facet values", () => {
    expect(SEED_VIEWS.map((v) => v.name)).toEqual(["ACCSO · subscription docs", "MTV-II · FY2025 close", "Unsigned side letters", "K-1s · tax year 2025"]);
    for (const v of SEED_VIEWS) {
      expect(v.spec.filters.primary_only).toBe(true);
      for (const y of v.spec.filters.fiscal_year ?? []) expect(typeof y).toBe("string");
      expect(() => buildWhere(v.spec)).not.toThrow();
    }
    expect(buildWhere(SEED_VIEWS[2].spec).params).toEqual([["side_letter"], ["draft", "final_unexecuted", "partially_executed"]]);
  });
});
