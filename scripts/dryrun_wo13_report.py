r"""CAT-WO-13 dry run on a THROWAWAY branch: PCAP-Q before (v1, every quarter) -> after (v2, cadence per entity).

  py scripts\dryrun_wo13_report.py --db-url-file <throwaway url file> --out docs\CAT-WO-13_DRYRUN.md

Steps: run migration 013 (re-runnable); BEFORE = the build with PCAP-Q v2 switched off, in a transaction that is rolled back; AFTER = the build applied; write
the counts per entity x quarter x result. Codes and counts only. Refuses main (dbguard)."""
import argparse, collections, datetime, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg
import requirements_wo03 as rq

SNAP = """SELECT entity_code, fiscal_year, fiscal_quarter, result, count(*) FROM app.v_requirement WHERE rule_id = 'PCAP-Q'
          GROUP BY 1, 2, 3, 4"""
RES = ("met", "on_file", "missing", "not_required", "no_roster")


def snap(conn):
    with conn.cursor() as cur:
        cur.execute(SNAP)
        out = {(e, fy, q, r): n for e, fy, q, r, n in cur.fetchall()}
    conn.commit()        # release the view's lock: migration 013 replaces app.v_requirement on another connection
    return out


def totals(s):
    t = collections.Counter()
    for (_, _, _, r), n in s.items():
        t[r] += n
    return t


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--out", required=True)
    ap.add_argument("--today", help="YYYY-MM-DD; default today")
    a = ap.parse_args()
    if a.release:
        sys.exit("REFUSED: the CAT-WO-13 dry run never runs on main")
    url = dbg.checked_url(a.db_url_file, False)
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    log = []
    with psycopg.connect(url) as conn:
        # migration 013 (re-runnable; the file carries its own BEGIN / COMMIT)
        with psycopg.connect(url, autocommit=True) as mc:
            mc.execute(open(os.path.join(HERE, "..", "db", "migrations", "013_wo13.sql"), encoding="utf-8").read())
        # BEFORE: the same build with PCAP-Q v2 switched off (v1 = every quarter), inside one transaction that is
        # rolled back - nothing of it stays on the branch
        with conn.cursor() as cur:
            cur.execute("UPDATE ops.requirement_rule SET active = false WHERE rule_id = 'PCAP-Q' AND version = 2")
            run, rows, mix = rq.build(cur, today)
            rq.write(cur, run, rows)
            cur.execute(SNAP)
            before = {(e, fy, q, r): n for e, fy, q, r, n in cur.fetchall()}
        conn.rollback()
        log.append("BEFORE (v1, rolled back): " + "  ".join(f"{k}={n:,}" for k, n in sorted(mix["PCAP-Q"].items())))
        # AFTER: v2 active, applied
        rq.run_build(conn, today, apply=True, log=log.append)
        after = snap(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT entity_code, cadence, first_period FROM ops.requirement_cadence WHERE rule_id = 'PCAP-Q' ORDER BY 2 DESC, 1")
            cad = cur.fetchall()
            cur.execute("SELECT DISTINCT entity_code, cadence FROM app.v_requirement WHERE rule_id = 'PCAP-Q'")
            view_cad = dict(cur.fetchall())
            cur.execute("SELECT version, active, entity_filter FROM ops.requirement_rule WHERE rule_id = 'PCAP-Q' ORDER BY 1")
            rules = cur.fetchall()
            cur.execute("SELECT DISTINCT rule_version FROM ops.requirement WHERE rule_id = 'PCAP-Q'")
            built_v = [r[0] for r in cur.fetchall()]
            cur.execute("""SELECT rule_id, count(*) FROM ops.requirement WHERE rule_id <> 'PCAP-Q' GROUP BY 1 ORDER BY 1""")
            others = cur.fetchall()
    tb, ta = totals(before), totals(after)
    L = [f"# CAT-WO-13 · PCAP cadence per fund · dry run (throwaway)", "",
         f"Run {datetime.datetime.now():%Y-%m-%d %H:%M} local, build date {today}. Throwaway branch `catwo13-throwaway`; main untouched. "
         "Codes and counts only.", "",
         "Before = the checklist build with PCAP-Q v1 (every quarter from FY2025). After = migration `013_wo13.sql` "
         "(ops.requirement_cadence seeded per R-058, PCAP-Q v2 with `entity_filter.cadence`) and the same build.", "",
         "## Totals (PCAP-Q)", "", "| | Expected rows | Met | On file | Missing | No roster |", "|---|---:|---:|---:|---:|---:|"]
    for lab, t in (("Before (v1)", tb), ("After (v2)", ta)):
        L.append(f"| {lab} | {sum(t.values()):,} | {t['met']:,} | {t['on_file']:,} | {t['missing']:,} | {t['no_roster']:,} |")
    L.append(f"| Change | {sum(ta.values()) - sum(tb.values()):+,} | {ta['met'] - tb['met']:+,} | {ta['on_file'] - tb['on_file']:+,} | "
             f"{ta['missing'] - tb['missing']:+,} | {ta['no_roster'] - tb['no_roster']:+,} |")
    L += ["", f"Met + On file: {tb['met'] + tb['on_file']:,} -> {ta['met'] + ta['on_file']:,}.", "",
          "## Rule versions", "", "| Version | Active | entity_filter |", "|---|---|---|"]
    L += [f"| {v} | {act} | `{ef}` |" for v, act, ef in rules]
    L += ["", f"Rows built after: rule_version {built_v}. Other rules' row counts after (CAT-WO-13 changes only PCAP-Q's subjects): "
          + ", ".join(f"{r} {n:,}" for r, n in others) + ".", "",
          "## Cadence (ops.requirement_cadence, R-058)", "", "| Entity | Cadence | First period |", "|---|---|---|"]
    L += [f"| {e} | {c} | {fp // 10} Q{fp % 10} |" if fp else f"| {e} | {c} | - |" for e, c, fp in cad]
    seeded = {e for e, _, _ in cad}
    fb = sorted(e for e in view_cad if e not in seeded)
    L += ["", f"No row -> annual fallback (Q4 only, FY2025+): {', '.join(fb) or 'none'}.", "",
          "## Per entity x quarter (before -> after)", "",
          "Cells: expected rows, then Met / On file / Missing / No roster. `-` = no rows.", "",
          "| Entity | Cadence | Period | Before: rows (M/OF/Mi/NR) | After: rows (M/OF/Mi/NR) |", "|---|---|---|---|---|"]
    keys = sorted({(e, fy, q) for (e, fy, q, _) in list(before) + list(after)}, key=lambda k: (k[0], k[1] or 0, k[2] or 0))

    def cell(s, k):
        c = {r: s.get(k + (r,), 0) for r in RES}
        n = sum(c.values())
        return "-" if not n else f"{n} ({c['met']}/{c['on_file']}/{c['missing']}/{c['no_roster']})"
    for k in keys:
        L.append(f"| {k[0]} | {view_cad.get(k[0], '-')} | {k[1]} Q{k[2]} | {cell(before, k)} | {cell(after, k)} |")
    L += ["", "## Per entity (before -> after)", "", "| Entity | Cadence | Rows | Met | On file | Missing |", "|---|---|---|---|---|---|"]
    for e in sorted({k[0] for k in keys}):
        b = collections.Counter(); f = collections.Counter()
        for (ee, _, _, r), n in before.items():
            if ee == e: b[r] += n
        for (ee, _, _, r), n in after.items():
            if ee == e: f[r] += n
        L.append(f"| {e} | {view_cad.get(e, '-')} | {sum(b.values())} -> {sum(f.values())} | {b['met']} -> {f['met']} | "
                 f"{b['on_file']} -> {f['on_file']} | {b['missing']} -> {f['missing']} |")
    L += ["", "## Build log", "", "```"] + log + ["```", ""]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print("\n".join(L[:16]))


if __name__ == "__main__":
    main()
