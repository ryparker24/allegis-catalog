import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { COLUMNS, parseSpec, SEED_VIEWS, SpecError } from "@/lib/find";

export const dynamic = "force-dynamic";

const DISPLAY_ONLY = ["name", "executed_date", "review_status"]; // shown in the grid, not filter/sort columns

/** GET: the user's saved views (the four design seeds are inserted on first use). */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "views" });
  if (!g.ok) return g.response;
  const D = db(env);
  const owner = g.session.email.toLowerCase();
  let rows = await D.rows("SELECT view_id, name, spec, is_seed FROM app.saved_view WHERE owner_email = $1 ORDER BY sort, name", [owner]);
  if (!rows.length) {
    for (const s of SEED_VIEWS) {
      await D.exec("INSERT INTO app.saved_view (owner_email, name, spec, is_seed, sort) VALUES ($1, $2, $3::jsonb, true, $4) ON CONFLICT (owner_email, name) DO NOTHING", [owner, s.name, JSON.stringify(s.spec), s.sort]);
    }
    rows = await D.rows("SELECT view_id, name, spec, is_seed FROM app.saved_view WHERE owner_email = $1 ORDER BY sort, name", [owner]);
  }
  return json({ views: rows });
}

/** POST {name, spec}: create or overwrite one of the user's views. */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "views" });
  if (!g.ok) return g.response;
  const body = (await req.json().catch(() => ({}))) as { name?: unknown; spec?: Record<string, unknown> };
  const name = String(body.name ?? "").trim();
  if (!name || name.length > 80) return json({ error: "bad_name" }, 400);
  let spec;
  try {
    spec = parseSpec(body.spec);
  } catch (e) {
    return json({ error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid" }, 400);
  }
  const columns = Array.isArray(body.spec?.columns) ? (body.spec!.columns as unknown[]).map(String).filter((c) => c in COLUMNS || DISPLAY_ONLY.includes(c)) : undefined;
  const stored = { ...spec, page: 0, columns };
  await db(env).exec(
    `INSERT INTO app.saved_view (owner_email, name, spec, sort) VALUES ($1, $2, $3::jsonb, 100)
     ON CONFLICT (owner_email, name) DO UPDATE SET spec = EXCLUDED.spec, updated_at = now()`,
    [g.session.email.toLowerCase(), name, JSON.stringify(stored)],
  );
  return json({ ok: true });
}

/** DELETE ?id=: delete one of the user's own views. */
export async function DELETE(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "views" });
  if (!g.ok) return g.response;
  const id = Number(new URL(req.url).searchParams.get("id"));
  if (!Number.isInteger(id) || id <= 0) return json({ error: "bad_id" }, 400);
  const n = await db(env).exec("DELETE FROM app.saved_view WHERE view_id = $1 AND owner_email = $2", [id, g.session.email.toLowerCase()]);
  return json({ ok: n === 1 });
}
