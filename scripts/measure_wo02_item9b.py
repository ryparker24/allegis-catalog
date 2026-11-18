r"""
CAT-WO-02 item 9 · additional proposals from Ryan's look at the live Review queue (READ-ONLY; counts only).

  py scripts/measure_wo02_item9b.py --db-url-file <catalog url file>

For each proposal: the rule, how many labelled files it would change, and kind (or status) before -> after.
For P1 it also shows which existing kind rule(s) set loc_agreement on those files and why (rule id, pattern,
value, priority) - the rule text is ours; no file name or matched text is printed.
"""
import sys, os, argparse, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import psycopg
from derive_wo02 import W

ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
a = ap.parse_args()

P1 = W(r"(‹fin(ancial)? ?(report|rpt)s?›|‹qtr›|‹qtrly›)")
P1_Q = W(r"(‹qtr›|‹qtrly›|‹quarter(ly)?›|‹q[1-4]›)")
P2 = W(r"‹operating agreement›")
P3_BOOKLET = W(r"‹subscription (booklet|book|package|docs?)›")
P3_BLANK = W(r"(‹blank›|‹form›|‹template›)")
P4 = W(r"(‹certificate of amendment›|‹name change›|‹de amendment›|‹delaware amendment›|‹amendment to (the )?certificate›)")

with psycopg.connect(open(a.db_url_file).read().strip(), options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
    cur.execute("""SELECT v.file_id, f.name, v.kind, v.issuer, v.document_id, v.stage
                   FROM app.v_find v JOIN cat.file f USING (file_id)""")
    rows = cur.fetchall()
    print(f"labelled files: {len(rows):,}")

    def report(title, rule, hits, after_fn):
        before = collections.Counter(k or "(none)" for _, _, k, *_ in hits)
        after = collections.Counter(after_fn(r) for r in hits)
        changed = sum(1 for r in hits if (r[2] or "(none)") != after_fn(r))
        print(f"\n== {title}\n  rule: {rule}\n  matching labelled files: {len(hits):,} · would change: {changed:,}")
        print("  kind before: " + ", ".join(f"{k} {n:,}" for k, n in before.most_common(10)))
        print("  after:       " + ", ".join(f"{k} {n:,}" for k, n in after.most_common(10)))
        tr = collections.Counter(f"{r[2] or '(none)'} -> {after_fn(r)}" for r in hits if (r[2] or "(none)") != after_fn(r))
        print("  changes:     " + ", ".join(f"{k} {n:,}" for k, n in tr.most_common(10)))
        return [r for r in hits if (r[2] or "(none)") != after_fn(r)]

    # ---- P1
    h1 = [r for r in rows if P1.search(r[1] or "")]
    report("P1 · 'Fin Report' / 'Financial Report' / 'Qtr' on no-kind or loc_agreement files -> quarterly_report (Qtr/quarter/Qn) else financial_statements",
           "name contains 'fin report' / 'financial report' / 'fin rpt' / 'qtr' / 'qtrly' (letter boundaries)",
           h1, lambda r: (r[2] or "(none)") if r[2] not in (None, "loc_agreement") else ("quarterly_report" if P1_Q.search(r[1] or "") else "financial_statements"))
    loc = [r[0] for r in h1 if r[2] == "loc_agreement"]
    print(f"  of these, kind loc_agreement now: {len(loc):,}  - which kind rule set it:")
    if loc:
        cur.execute("""SELECT s.rule_id, s.value, s.priority, s.source, count(*)
                       FROM cat.file_signal s WHERE s.field = 'kind' AND s.file_id = ANY(%s)
                       GROUP BY 1,2,3,4 ORDER BY 5 DESC LIMIT 12""", (loc,))
        sig = cur.fetchall()
        for rid, val, pri, src, n in sig:
            print(f"    signal {rid or '-':<12} -> {val:<22} priority {pri}  source {src:<6} on {n:,} of these files")
        ids = sorted({s[0] for s in sig if s[0]})
        if ids:
            cur.execute("""SELECT DISTINCT ON (rule_id) rule_id, version, applies_to, pattern, value, priority, notes
                           FROM ops.decomposition_rule WHERE rule_id = ANY(%s) ORDER BY rule_id, version DESC""", (ids,))
            for rid, ver, ap_, pat, val, pri, notes in cur.fetchall():
                print(f"    RULE {rid} v{ver} ({ap_}): pattern {pat!r} -> {val} (priority {pri}){' · ' + notes if notes else ''}")
        # rules that set loc_agreement at all, and how many labelled files they touch overall
        cur.execute("""SELECT DISTINCT ON (rule_id) rule_id, version, applies_to, pattern, priority FROM ops.decomposition_rule
                       WHERE field = 'kind' AND value = 'loc_agreement' AND active ORDER BY rule_id, version DESC""")
        for rid, ver, ap_, pat, pri in cur.fetchall():
            cur.execute("""SELECT count(DISTINCT s.file_id) FROM cat.file_signal s JOIN app.labelled_file l USING (file_id)
                           WHERE s.field='kind' AND s.rule_id=%s""", (rid,))
            print(f"    all loc_agreement rules: {rid} v{ver} ({ap_}) {pat!r} priority {pri} -> fires on {cur.fetchone()[0]:,} labelled files")

    # ---- P2
    h2 = [r for r in rows if P2.search(r[1] or "")]
    report("P2 · 'Operating Agreement' -> operating_agreement (NEW kind; Datum FORM-04)",
           "name contains 'operating agreement' (needs a new Kind choice on the Allegis Document label + ref.vocab)",
           h2, lambda r: "operating_agreement")

    # ---- P3
    h3 = [r for r in rows if P3_BOOKLET.search(r[1] or "") or (P3_BLANK.search(r[1] or "") and r[3] == "counsel" and r[2] in ("subscription_agreement", None))]
    ch = report("P3 · 'Subscription Booklet', or 'blank'/'form'/'template' from counsel -> template (not when fully executed)",
                "name contains 'subscription booklet/book/package/docs', OR (issuer = counsel AND name has 'blank'/'form'/'template' AND kind is subscription_agreement or none)",
                h3, lambda r: (r[2] or "(none)") if r[5] == "fully_executed" else "template")
    st = collections.Counter(r[5] or "(none)" for r in h3)
    print("  signing stage before: " + ", ".join(f"{k} {n:,}" for k, n in st.most_common(6)))
    by_part = collections.Counter("booklet" if P3_BOOKLET.search(r[1] or "") else "counsel blank/form" for r in h3)
    print("  matched by: " + ", ".join(f"{k} {n:,}" for k, n in by_part.items()))

    # ---- P4
    h4 = [r for r in rows if P4.search(r[1] or "")]
    report("P4 · 'Certificate of Amendment' / 'Name Change' / 'DE Amendment' -> formation_filing (not tax returns / forms)",
           "name contains 'certificate of amendment' / 'name change' / 'DE amendment' / 'Delaware amendment' / 'amendment to (the) certificate'",
           h4, lambda r: (r[2] or "(none)") if r[2] in ("tax_return", "tax_form") else "formation_filing")

    overlap = len({r[0] for r in h1} & {r[0] for r in h2 + h3 + h4}) + len({r[0] for r in h2} & {r[0] for r in h3 + h4}) + len({r[0] for r in h3} & {r[0] for r in h4})
    print(f"\nfiles matched by more than one of P1-P4: {overlap:,}")
