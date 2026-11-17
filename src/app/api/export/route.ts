import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { exportQuery, parseSpec, SpecError, toCsv } from "@/lib/find";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";
const COLS = ["file_id", "document_id", "kind", "entities", "portcos", "fiscal_year", "period", "stage", "signed_date", "tier", "is_primary", "web_view_link"];

/** POST /api/export  body: FindSpec  ->  CSV of codes and Drive links (no file names). */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "export" });
  if (!g.ok) return g.response;
  let spec;
  try {
    spec = parseSpec(await req.json());
  } catch (e) {
    return json({ error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid_json" }, 400);
  }
  const q = exportQuery(spec);
  const rows = await db(env).rows(q.sql, q.params);
  logEvent("export", { count: rows.length });
  return new Response(toCsv(rows, COLS), {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="catalog-export-${new Date().toISOString().slice(0, 10)}.csv"`,
      "cache-control": "no-store",
    },
  });
}
