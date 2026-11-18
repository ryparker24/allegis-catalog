import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { parseLayout, parseSpec, SpecError } from "@/lib/find";

export const dynamic = "force-dynamic";

/** Item 2: the last list state per user ("find"). Validated like a saved view; search text is never stored. */
const KEYS = new Set(["find", "review"]);

export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "prefs" });
  if (!g.ok) return g.response;
  const key = new URL(req.url).searchParams.get("key") ?? "";
  if (!KEYS.has(key)) return json({ error: "bad_key" }, 400);
  const r = await db(env).rows<{ value: unknown }>("SELECT value FROM app.user_pref WHERE owner_email = $1 AND pref_key = $2", [g.session.email.toLowerCase(), key]);
  return json({ value: r[0]?.value ?? null });
}

export async function PUT(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "prefs" });
  if (!g.ok) return g.response;
  const b = (await req.json().catch(() => ({}))) as { key?: string; value?: Record<string, unknown> };
  if (!KEYS.has(String(b.key))) return json({ error: "bad_key" }, 400);
  let value;
  try {
    const { search: _search, ...rest } = parseSpec(b.key === "review" ? { ...b.value, sort: undefined } : b.value);
    void _search;
    const lanes = Array.isArray(b.value?.lanes) ? (b.value!.lanes as unknown[]).map(String).filter((l) => ["stage_unknown", "low_confidence_executed", "no_kind"].includes(l)) : undefined;
    // the Review queue sorts on its own columns (queue / confidence / ...): kept as {col, dir} only, validated on use
    const rsort = b.key === "review" && b.value?.sort && typeof b.value.sort === "object" ? { col: String((b.value.sort as { col?: unknown }).col ?? "queue").slice(0, 20), dir: (b.value.sort as { dir?: unknown }).dir === "asc" ? "asc" : "desc" } : undefined;
    value = { ...rest, ...(rsort ? { sort: rsort } : {}), page: 0, ...parseLayout(b.value), viewId: Number.isInteger(b.value?.viewId) ? b.value!.viewId : null, ...(lanes ? { lanes } : {}) };
  } catch (e) {
    return json({ error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid" }, 400);
  }
  if (JSON.stringify(value).length > 30_000) return json({ error: "too_large" }, 400);
  await db(env).exec(
    `INSERT INTO app.user_pref (owner_email, pref_key, value) VALUES ($1, $2, $3::jsonb)
     ON CONFLICT (owner_email, pref_key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()`,
    [g.session.email.toLowerCase(), b.key, JSON.stringify(value)]);
  return json({ ok: true });
}
