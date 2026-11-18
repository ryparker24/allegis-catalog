import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { parseLayout, parseSpec, SpecError } from "@/lib/find";
import { LANES, REVIEW_COLUMNS, REVIEW_SORTABLE } from "@/lib/reviewq";
import { checklistPref } from "@/lib/checklists";

export const dynamic = "force-dynamic";

/** Item 2: the last list state per user ("find"). Validated like a saved view; search text is never stored. */
const KEYS = new Set(["find", "review", "checklists"]);

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
  if (b.key === "checklists") {
    value = checklistPref(b.value);   // CAT-WO-03: rule / scope / result filter / sort / page size / widths, whitelisted
    if (!value) return json({ error: "bad_spec", reason: "checklists" }, 400);
  } else try {
    const { search: _search, ...rest } = parseSpec(b.key === "review" ? { ...b.value, sort: undefined } : b.value);
    void _search;
    const lanes = Array.isArray(b.value?.lanes) ? (b.value!.lanes as unknown[]).map(String).filter((l) => (LANES as readonly string[]).includes(l)) : undefined;   // CAT-WO-03: every lane (status_unknown was dropped)
    // the Review queue sorts on its own columns (queue / confidence / ...): kept as {col, dir} only, validated on use
    // the Review sort column must be one the Review list can sort on (coder review: a bad one would break every visit)
    const rcol = b.key === "review" && b.value?.sort && typeof b.value.sort === "object" ? String((b.value.sort as { col?: unknown }).col ?? "") : "";
    const rsort = b.key === "review" && REVIEW_SORTABLE.includes(rcol) ? { col: rcol, dir: (b.value!.sort as { dir?: unknown }).dir === "asc" ? "asc" : "desc" } : undefined;
    // Review's widths are keyed by its own columns (why / confidence aren't Find columns)
    const rwidths: Record<string, number> = {};
    if (b.key === "review" && b.value?.widths && typeof b.value.widths === "object") {
      for (const [k, v] of Object.entries(b.value.widths as Record<string, unknown>)) {
        const n = Math.round(Number(v));
        if (REVIEW_COLUMNS.includes(k) && Number.isFinite(n)) rwidths[k] = Math.max(60, Math.min(900, n));
      }
    }
    value = { ...rest, ...(rsort ? { sort: rsort } : {}), page: 0, ...(b.key === "review" ? { widths: rwidths } : parseLayout(b.value)), viewId: Number.isInteger(b.value?.viewId) ? b.value!.viewId : null, ...(lanes ? { lanes } : {}) };
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
