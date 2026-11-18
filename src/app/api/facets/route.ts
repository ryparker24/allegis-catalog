import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Filter choices with counts over the v1 scope (labelled, non-secret files). */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "facets" });
  if (!g.ok) return g.response;
  const D = db(env);
  const V = "app.v_find_x";
  const [kind, entity, portco, fy, stage, tier, period, workstream, issuer, ftf, issuing, receiving, status] = await Promise.all([
    D.rows(`SELECT coalesce(kind,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 2 DESC`),
    D.rows(`SELECT e AS value, count(*)::int AS n FROM ${V}, unnest(entities) e GROUP BY 1 ORDER BY 1`),
    D.rows(`SELECT p AS value, coalesce(max(vp.display_name), p) AS label, count(*)::int AS n
            FROM ${V}, unnest(portcos) p LEFT JOIN app.v_portco vp ON vp.portco_code = p GROUP BY 1 ORDER BY 2`),
    D.rows(`SELECT coalesce(fiscal_year::text,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 1 DESC`),
    D.rows(`SELECT coalesce(stage,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 2 DESC`),
    D.rows(`SELECT tier AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 1`),
    D.rows(`SELECT coalesce(period,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 2 DESC`),
    D.rows(`SELECT coalesce(workstream,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 2 DESC`),
    D.rows(`SELECT coalesce(issuer,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 2 DESC`),
    D.rows(`SELECT coalesce(file_type_family,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 2 DESC`),
    D.rows(`SELECT coalesce(issuing_entity,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 2 DESC`),
    D.rows(`SELECT r AS value, count(*)::int AS n FROM ${V}, unnest(CASE WHEN cardinality(receiving_entities)=0 THEN ARRAY['(none)'] ELSE receiving_entities END) r GROUP BY 1 ORDER BY 2 DESC`),
    D.rows(`SELECT coalesce(status,'(none)') AS value, count(*)::int AS n FROM ${V} GROUP BY 1 ORDER BY 2 DESC`),
  ]);
  return json({ kind, entity, portco, fiscal_year: fy, stage, tier, period, workstream, issuer, file_type_family: ftf, issuing_entity: issuing, receiving_entity: receiving, status }, 200, { "cache-control": "private, max-age=120" });
}
