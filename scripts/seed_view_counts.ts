/**
 * Row count each seed view returns, through the app's own WHERE builder, as catalog_app (so grants and the
 * secret-tier exclusion in app.v_find both apply). Prints view names (design labels) and counts only.
 *   npx tsx scripts/seed_view_counts.ts --url-file <file holding a catalog_app URL for a THROWAWAY BRANCH>
 */
import { readFileSync } from "node:fs";
import { neon } from "@neondatabase/serverless";
import { buildWhere, SEED_VIEWS } from "../src/lib/find";

const i = process.argv.indexOf("--url-file");
const sql = neon(readFileSync(process.argv[i + 1], "utf8").trim());

(async () => {
  for (const v of SEED_VIEWS) {
    const { where, params } = buildWhere(v.spec);
    const r = (await sql.query(`SELECT count(*)::int AS n FROM app.v_find ${where}`, params)) as { n: number }[];
    console.log(`${v.name}\t${r[0].n}`);
  }
})();
