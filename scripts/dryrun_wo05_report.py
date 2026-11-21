r"""
CAT-WO-05 · dry-run report for Ryan's veto (read-only; counts and codes only). Run after derive + checklists on the
database the url file points at (main at release), next to the re-sync dry run (which gives the per-field file counts).

  py scripts\dryrun_wo05_report.py --db-url-file <url file> [--release]

Per Status rule (R-032) and portal rule (R-031): labelled documents it sets, the labelled FILES whose Status label it
would write, and the checklist rows whose best document carries that rule (Met / on file), so a veto's effect is visible.
"""
import argparse, collections, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import dbguard_wo03 as dbg


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    a = ap.parse_args()
    con = psycopg.connect(dbg.checked_url(a.db_url_file, a.release))
    con.read_only = True
    cur = con.cursor()
    cur.execute("""SELECT d.status_rule, coalesce(d.status_auto, '(blank)'), count(DISTINCT d.document_id), count(DISTINCT lf.file_id),
                          count(DISTINCT d.document_id) FILTER (WHERE d.status_confirmed IS NOT NULL)
                   FROM cat.document d JOIN cat.file_document fd ON fd.document_id = d.document_id
                   JOIN app.labelled_file lf ON lf.file_id = fd.file_id
                   WHERE d.status_rule LIKE 'ST5-%%' OR d.status_rule LIKE 'PORTAL-%%'
                   GROUP BY 1, 2 ORDER BY 1""")
    rows = cur.fetchall()
    cur.execute("""SELECT d.status_rule, r.rule_id, r.result, count(*) FROM ops.requirement r JOIN cat.document d ON d.document_id = r.best_document_id
                   WHERE d.status_rule LIKE 'ST5-%%' OR d.status_rule LIKE 'PORTAL-%%' GROUP BY 1, 2, 3""")
    ck = collections.defaultdict(list)
    for sr, rid, res, n in cur.fetchall():
        ck[sr].append(f"{rid} {res} {n}")
    cur.execute("SELECT rule_id, active, provisional FROM ops.decomposition_rule WHERE applies_to = 'status'")
    state = {r[0]: r[1:] for r in cur.fetchall()}
    print("rule                  sets       labelled docs  labelled files  (person Status kept on)  checklist rows (best document)")
    for sr, st, nd, nf, npers in rows:
        act = state.get(sr)
        tag = "" if act is None else ("" if act[0] else "  VETOED") + (" provisional" if act[1] else "")
        print(f"{sr:21} {st:10} {nd:>13,}  {nf:>14,}  {npers:>23,}  {'; '.join(sorted(ck.get(sr, []))) or '-'}{tag}")
    cur.execute("SELECT rule_id, result, count(*) FROM ops.requirement GROUP BY 1, 2 ORDER BY 1, 2")
    mix = collections.defaultdict(list)
    for rid, res, n in cur.fetchall():
        mix[rid].append(f"{res}={n}")
    print("\nchecklists now: " + " | ".join(f"{k}: {' '.join(v)}" for k, v in sorted(mix.items())))
    cur.execute("SELECT count(DISTINCT document_id) FROM ops.portal_kind_conflict")
    print(f"Portal kind conflict list: {cur.fetchone()[0]} documents")


if __name__ == "__main__":
    main()
