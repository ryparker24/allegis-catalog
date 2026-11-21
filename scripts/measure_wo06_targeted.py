r"""
CAT-WO-06 · targeted measure on the THROWAWAY branch (coordinator's follow-up to item 0). Counts and codes only.

  py scripts\measure_wo06_targeted.py --db-url-file <branch url file> [--skip-read]

1. read ALL readable FY2025-onward K1-SET / PCAP-Q candidates (K-1s and PCAPs with FY >= 2025 or blank FY whose entity has
   a Datum roster) plus all subscription agreements and side letters; report the time
2. checklists before -> after, as designed and as if CNT-PCAP-TOP were promoted to apply (the promotion is simulated on
   the branch and reverted)
3. K1-SET / PCAP-Q rows still Missing (FY >= 2025), by reason, entity and FY
"""
import argparse, collections, datetime, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg
import pages_wo06 as pw

CAND_SQL = """
WITH roster AS (SELECT DISTINCT entity_code FROM ref.party WHERE entity_code IS NOT NULL),
d AS (
  SELECT d.document_id, coalesce(d.kind_confirmed, d.kind_auto) AS kind, coalesce(d.fiscal_year_confirmed, d.fiscal_year_auto) AS fy,
         coalesce(d.entities_confirmed, (SELECT array_agg(DISTINCT e.entity_code) FROM cat.file_document fd JOIN cat.v_file_entity e ON e.file_id = fd.file_id
                                         WHERE fd.document_id = d.document_id)) || ARRAY[coalesce(d.issuing_entity_confirmed, d.issuing_entity_auto)] AS ents
  FROM cat.document d WHERE coalesce(d.kind_confirmed, d.kind_auto) = ANY(%s))
SELECT document_id, kind FROM d
WHERE kind IN ('subscription_agreement', 'side_letter')
   OR ((fy IS NULL OR fy >= 2025) AND EXISTS (SELECT 1 FROM unnest(ents) e JOIN roster r ON r.entity_code = e))
"""


def counts(cur):
    cur.execute("""SELECT rule_id, result, count(*) FROM ops.requirement
                   WHERE rule_id IN ('K1-SET', 'PCAP-Q', 'LP-SUB') AND (fiscal_year IS NULL OR fiscal_year >= 2025 OR rule_id = 'LP-SUB')
                   GROUP BY 1, 2""")
    out = collections.defaultdict(collections.Counter)
    for r, res, n in cur.fetchall():
        out[r][res] += n
    return out


def line(r, b, a):
    f = lambda c, k: c.get(k, 0)
    return (f"  {r:7} Met {f(b,'met'):5} -> {f(a,'met'):5} ({f(a,'met')-f(b,'met'):+d})  On file {f(b,'on_file'):5} -> {f(a,'on_file'):5}  "
            f"Missing {f(b,'missing'):5} -> {f(a,'missing'):5}  No roster {f(b,'no_roster')} -> {f(a,'no_roster')}")


def rebuild(con):
    import subject_wo03 as sw, requirements_wo03 as rq
    sw.run(con, apply=True, staff=None, log=lambda m: None)
    rq.run_build(con, apply=True, log=lambda m: None)


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--skip-read", action="store_true")
    a = ap.parse_args()
    if a.release:
        sys.exit("REFUSED: throwaway branch only")
    url = dbg.checked_url(a.db_url_file)
    pw.net_guard()
    out = []
    log = lambda m: (print(m), out.append(m))
    con = psycopg.connect(url); cur = con.cursor()
    cur.execute(CAND_SQL, (list(pw.KINDS),))
    cand = dict(cur.fetchall())
    docs = {d["document_id"]: d for d in pw.scope(cur)}
    readable = [d for d in cand if d in docs and pw.fmt_of(docs[d]["mime"]) in ("pdf", "gdoc")]
    log(f"TARGETED · CAT-WO-06 · {datetime.datetime.now():%Y-%m-%d %H:%M} · candidates {len(cand):,} · readable {len(readable):,} · by kind "
        + ", ".join(f"{k} {n:,}" for k, n in sorted(collections.Counter(cand[d] for d in readable).items())))
    # baseline: no content at all (subject + requirements without content), then read
    cur.execute("SELECT count(*) FROM cat.doc_content_match"); had = cur.fetchone()[0]
    saved = None
    if not a.skip_read:
        cur.execute("DELETE FROM cat.doc_content_match"); cur.execute("DELETE FROM cat.doc_page_read"); con.commit()
    else:
        cur.execute("CREATE TEMP TABLE _keep AS SELECT * FROM cat.doc_content_match"); cur.execute("DELETE FROM cat.doc_content_match"); con.commit()
    rebuild(con)
    before = counts(cur); con.commit()
    if a.skip_read:
        cur.execute("INSERT INTO cat.doc_content_match SELECT * FROM _keep"); con.commit()
        secs = 0
    else:
        home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
        sys.path.insert(0, home); os.chdir(home)
        import drive_crawl as dc
        dc.InstalledAppFlow = pw._NoBrowser
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
        t0 = time.time()
        pw.run(con, svc, incremental=True, apply=True, log=lambda m: None, only_ids=readable, connect=lambda: psycopg.connect(url))
        secs = time.time() - t0
        con = psycopg.connect(url); cur = con.cursor()
    pw.apply_content(con, apply=True, log=log)
    cur.execute("SELECT outcome, count(*) FROM cat.doc_page_read GROUP BY 1 ORDER BY 2 DESC")
    log(f"read {len(readable):,} documents in {secs/60:.0f} min ({secs/max(1,len(readable)):.2f} s each) · outcomes " + ", ".join(f"{o} {n:,}" for o, n in cur.fetchall()))

    rebuild(con)
    designed = counts(cur); con.commit()
    log("\nCHECKLISTS before -> after, AS DESIGNED (medium rules review-only); K1-SET / PCAP-Q from FY2025")
    for r in ("K1-SET", "PCAP-Q", "LP-SUB"):
        log(line(r, before[r], designed[r]))
    # simulate CNT-PCAP-TOP promoted to apply, then revert
    cur.execute("UPDATE cat.doc_content_match SET confidence = 'high' WHERE rule_id = 'CNT-PCAP-TOP' AND confidence = 'medium' AND reason IS NULL")
    promoted_rows = cur.rowcount; con.commit()
    rebuild(con)
    promo = counts(cur); con.commit()
    log(f"\nCHECKLISTS before -> after, IF CNT-PCAP-TOP WERE PROMOTED ({promoted_rows:,} medium rows treated as high; simulated, then reverted)")
    for r in ("K1-SET", "PCAP-Q", "LP-SUB"):
        log(line(r, before[r], promo[r]))
    cur.execute("UPDATE cat.doc_content_match SET confidence = 'medium' WHERE rule_id = 'CNT-PCAP-TOP' AND confidence = 'high' AND reason IS NULL"); con.commit()
    rebuild(con)

    # 3. Missing breakdown (as designed)
    cur.execute("""SELECT rule_id, entity_code, partner_code, fiscal_year, fiscal_quarter FROM ops.requirement
                   WHERE rule_id IN ('K1-SET', 'PCAP-Q') AND result = 'missing' AND fiscal_year >= 2025""")
    missing = cur.fetchall()
    cur.execute("""SELECT x.document_id, x.kind, x.entities, x.issuing_entity, x.fiscal_year, x.period FROM app.v_find_x x
                   WHERE x.kind IN ('k1', 'capital_statement') AND x.document_id IS NOT NULL""")
    by_ep = collections.defaultdict(set)
    seen = set()
    for did, kind, ents, iss, fy, per in cur.fetchall():
        if (did, kind) in seen: continue
        seen.add((did, kind))
        for e in set(ents or []) | ({iss} if iss else set()):
            by_ep[(kind, e, fy)].add((did, per))
    cur.execute("SELECT document_id, outcome FROM cat.doc_page_read")
    outcome = dict(cur.fetchall())
    cur.execute("SELECT document_id, array_agg(DISTINCT coalesce(reason, confidence)) FROM cat.doc_content_match GROUP BY 1")
    creasons = {d: set(r) for d, r in cur.fetchall()}
    cur.execute("SELECT document_id, partner_code FROM cat.doc_party")
    dparty = collections.defaultdict(set)
    for d, p in cur.fetchall(): dparty[d].add(p)
    reason_n = collections.Counter(); by_ent = collections.defaultdict(collections.Counter)
    for rule, e, p, fy, q in missing:
        kind = "k1" if rule == "K1-SET" else "capital_statement"
        ds = [d for d, per in by_ep.get((kind, e, fy), ()) if q is None or (per or "") in (f"q{q}",) + (("fy",) if q == 4 else ())]
        if not ds:
            r = "a_no_document_for_entity_period"
        else:
            unread = [d for d in ds if outcome.get(d) not in ("ok", "no_anchor", "ocr_partial")]
            if any("NOT_IN_FUND" in creasons.get(d, set()) for d in ds):
                r = "b3_name_of_partner_not_in_fund"
            elif any(outcome.get(d) in ("ok", "ocr_partial") for d in ds):
                r = "b2_anchor_but_no_roster_name_for_this_partner"
            elif len(unread) == len(ds):
                r = "b1_no_anchor_unreadable_or_not_read"
            else:
                r = "b1_no_anchor"
        reason_n[(rule, r)] += 1
        by_ent[(rule, r)][(e, fy)] += 1
    log(f"\nMISSING K1-SET / PCAP-Q rows from FY2025 (as designed): {len(missing):,}")
    for (rule, r), n in sorted(reason_n.items()):
        top = sorted(by_ent[(rule, r)].items(), key=lambda kv: -kv[1])[:8]
        log(f"  {rule:7} {r:46} {n:5}   top entity/FY: " + ", ".join(f"{e} {fy}: {c}" for (e, fy), c in top))
    cur.execute("""SELECT rule_id, coalesce(sub_status, '-'), count(*) FROM ops.requirement WHERE rule_id IN ('K1-SET', 'PCAP-Q')
                   AND result = 'on_file' AND fiscal_year >= 2025 GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    log("  (c) matched / on file but not final or issued (On file rows by sub-status): " + ", ".join(f"{r} {s} {n}" for r, s, n in cur.fetchall()))
    con.close()
    with open(os.path.join(r"C:\DriveCatalog\logs", f"wo06_targeted_{datetime.datetime.now():%Y%m%d_%H%M}.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
