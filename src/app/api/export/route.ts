import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { EXPORT_COLS, EXPORT_LIMIT, exportCell, exportQuery, parseSpec, SpecError, toCsv, XLSX_LIMIT } from "@/lib/find";
import { driveNameSearch } from "@/lib/google";
import { toXlsx } from "@/lib/xlsx";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/** POST /api/export?format=csv|xlsx  body: FindSpec  ->  codes and Drive links (no file names). */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "export" });
  if (!g.ok) return g.response;
  const format = new URL(req.url).searchParams.get("format") === "xlsx" ? "xlsx" : "csv";
  let spec;
  try {
    spec = parseSpec(await req.json());
  } catch (e) {
    return json({ error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid_json" }, 400);
  }
  let ids: string[] = [];
  if (spec.search) {
    const r = await driveNameSearch(g.session.at, spec.search);
    if (r.status === 401) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
    ids = r.ids;
  }
  // Excel: refuse (413) rather than build a sheet that could exhaust Worker memory; CSV streams fine up to 50k
  const q = exportQuery(spec, { nameIds: ids, hideCopies: true }, format === "xlsx" ? XLSX_LIMIT + 1 : EXPORT_LIMIT);
  const rows = await db(env).rows(q.sql, q.params);
  if (format === "xlsx" && rows.length > XLSX_LIMIT) {
    return json({ error: "too_many_rows_for_excel", limit: XLSX_LIMIT, hint: "Narrow the filters or use Download CSV." }, 413);
  }
  logEvent("export", { count: rows.length, format });
  const stamp = new Date().toISOString().slice(0, 10);
  if (format === "xlsx") {
    const body = toXlsx(EXPORT_COLS, rows.map((r) => EXPORT_COLS.map((c) => exportCell((r as Record<string, unknown>)[c]))));
    return new Response(body as unknown as BodyInit, {
      headers: {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content-disposition": `attachment; filename="catalog-export-${stamp}.xlsx"`,
        "cache-control": "no-store",
      },
    });
  }
  return new Response(toCsv(rows, EXPORT_COLS), {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="catalog-export-${stamp}.csv"`,
      "cache-control": "no-store",
    },
  });
}
