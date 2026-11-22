r"""CAT-WO-06 stop 2 · dry-run report on main (READ ONLY session). Counts and codes only.

  py scripts\dryrun_wo06_report.py --db-url-file <url file> --release
Needs proofs\catwo06\refs_before_main.csv and checklists_before_main.csv (taken before the read).
"""
import argparse, collections, csv, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg
import pages_wo06 as pw
PROOFS = r"C:\DriveCatalog\proofs\catwo06"


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    a = ap.parse_args()
    con = psycopg.connect(dbg.checked_url(a.db_url_file, a.release), options="-c default_transaction_read_only=on")
    q = lambda s, p=(): con.execute(s, p).fetchall()
    out = []
    log = lambda m: (print(m), out.append(m))
    log("DRY RUN REPORT · CAT-WO-06 · main (read-only)")
    log("\nREADS by kind and outcome:")
    for k, o, n, ocr in q("""SELECT coalesce(d.kind_confirmed, d.kind_auto), r.outcome, count(*), count(*) FILTER (WHERE r.ocr_used)
                             FROM cat.doc_page_read r JOIN cat.document d USING (document_id) GROUP BY 1, 2 ORDER BY 1, 3 DESC"""):
        log(f"  {k:24} {o:16} {n:6,}  (OCR {ocr:,})")
    log("\nCANDIDATES by CNT rule / confidence / reason (rows; documents):")
    for rid, conf, reason, n, nd in q("""SELECT coalesce(rule_id, '-'), confidence, coalesce(reason, '-'), count(*), count(DISTINCT document_id)
                                         FROM cat.doc_content_match GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"""):
        log(f"  {rid:18} {conf:6} {reason:16} {n:6,}  docs {nd:,}")
    ref = collections.defaultdict(set)
    with open(os.path.join(PROOFS, "refs_before_main.csv")) as fh:
        for r in csv.DictReader(fh):
            ref[int(r["document_id"])].add(r["partner_code"])
    log("\nPRECISION per CNT rule vs references taken before the read (portal / person / folder-name):")
    per = collections.defaultdict(lambda: collections.Counter())
    for d, rid, conf, p in q("SELECT document_id, rule_id, confidence, partner_code FROM cat.doc_content_match WHERE partner_code IS NOT NULL AND confidence IN ('high', 'medium')"):
        k = (rid, conf)
        per[k]["n"] += 1
        if ref.get(d):
            per[k]["agree" if p in ref[d] else "disagree"] += 1
    for (rid, conf), c in sorted(per.items()):
        m = c["agree"] + c["disagree"]
        log(f"  {rid:18} {conf:6} n {c['n']:5}  measured {m:5}  agree {c['agree']:5}  disagree {c['disagree']:3}  precision "
            + (f"{100 * c['agree'] / m:.1f}%" if m else "n/a") + ("   <97%: review-only" if m and conf == "high" and 100 * c["agree"] / m < 97 else ""))
    log("\nSUBJECT (labelled documents only; what the re-sync would write):")
    for rule, n in q("""SELECT coalesce(d.subject_rule, '-'), count(DISTINCT d.document_id) FROM cat.document d
                        WHERE EXISTS (SELECT 1 FROM cat.file_document fd JOIN app.labelled_file l ON l.file_id = fd.file_id WHERE fd.document_id = d.document_id)
                          AND d.subject_rule LIKE 'SUBJ-CONTENT%%' GROUP BY 1 ORDER BY 2 DESC"""):
        log(f"  {rule:28} {n:6,}")
    pk = q("""SELECT count(*) FILTER (WHERE n = 1), count(*) FILTER (WHERE n > 1) FROM (SELECT document_id, count(DISTINCT seq) n FROM cat.doc_content_match
              WHERE confidence = 'high' GROUP BY 1) x""")[0]
    log(f"  content-high documents: single statement {pk[0]:,} · packages / bundles {pk[1]:,}")
    log("\nHANDLING flags (R-037) on labelled documents (the re-sync adds the ones not already on the file):")
    for f, n in q("""SELECT f, count(DISTINCT d.document_id) FROM cat.document d, unnest(d.content_flags) f
                     WHERE EXISTS (SELECT 1 FROM cat.file_document fd JOIN app.labelled_file l ON l.file_id = fd.file_id WHERE fd.document_id = d.document_id)
                     GROUP BY 1"""):
        log(f"  {f:8} {n:6,} documents")
    log("\nREVIEW LANES:")
    rc = q("SELECT match_subject, content_disagrees FROM app.v_review_counts")[0]
    log(f"  Match subject {rc[0]:,} files · Content disagrees {rc[1]:,} files")
    for reason, n in q("SELECT coalesce(reason, 'MEDIUM'), count(DISTINCT document_id) FROM cat.doc_content_match WHERE lane GROUP BY 1 ORDER BY 2 DESC"):
        log(f"    content lane {reason:16} {n:5,} documents")
    for f, n in q("SELECT f, count(*) FROM cat.doc_content_check, unnest(content_disagrees) f GROUP BY 1"):
        log(f"    content disagrees on {f:12} {n:5,} documents")
    before = collections.defaultdict(dict)
    with open(os.path.join(PROOFS, "checklists_before_main.csv")) as fh:
        for r in csv.DictReader(fh):
            before[r["rule_id"]][r["result"]] = int(r["n"])
    after = collections.defaultdict(dict)
    for r, res, n in q("SELECT rule_id, result, count(*) FROM ops.requirement GROUP BY 1, 2"):
        after[r][res] = n
    log("\nCHECKLISTS before -> after (all years; Met / On file / Missing / No roster):")
    for r in ("K1-SET", "PCAP-Q", "LP-SUB", "LP-SIDE", "GP-COMMIT", "AUDITED-FS"):
        b, x = before.get(r, {}), after.get(r, {})
        if not b and not x: continue
        f = lambda c, k: c.get(k, 0)
        log(f"  {r:10} Met {f(b,'met'):5} -> {f(x,'met'):5}  On file {f(b,'on_file'):5} -> {f(x,'on_file'):5}  Missing {f(b,'missing'):5} -> {f(x,'missing'):5}  "
            f"No roster {f(b,'no_roster')} -> {f(x,'no_roster')}  None found {f(b,'none_found')} -> {f(x,'none_found')}")
    bp = q("SELECT count(*) FROM ops.requirement WHERE best_page IS NOT NULL")[0][0]
    log(f"  checklist rows showing p. N (package / bundle best document): {bp:,}")
    con.close()
    with open(os.path.join(r"C:\DriveCatalog\logs", "wo06_dryrun_report_main.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
