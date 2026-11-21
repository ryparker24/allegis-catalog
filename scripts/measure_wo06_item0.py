r"""
CAT-WO-06 item 0 · measure first-page reading on the THROWAWAY branch (counts and codes only).

  py scripts\measure_wo06_item0.py --db-url-file <branch url file> [--per-kind 200] [--seed 6]

1. scope: in-scope documents by kind, format and drive
2. a random sample of N documents per kind (PDF / Google Doc), read with pages_wo06 and written to the BRANCH
3. text-layer rate, OCR use, ocr_needed; anchor-found rate; match rate (high / medium / none)
4. precision of HIGH matches against references taken BEFORE the read: portal-derived codes (R-031), person-set
   Subject codes, existing folder / name high matches - overall and per CNT rule (< 97% -> review-only at the dry run)
5. packages / bundles: count, median / max pages, statements found vs the fund's roster size
6. checklists before / after the sample (Subject + requirements re-run on the branch), extrapolated to the full scope
7. read time per document; projected backfill and nightly run times
"""
import argparse, collections, datetime, os, random, statistics, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg
import pages_wo06 as pw


def checklist_counts(cur):
    cur.execute("""SELECT rule_id, CASE WHEN result = 'on_file' THEN 'on_file' ELSE result END, count(*) FROM ops.requirement
                   WHERE rule_id IN ('K1-SET', 'PCAP-Q', 'LP-SUB') AND (fiscal_year IS NULL OR fiscal_year >= 2025 OR rule_id = 'LP-SUB')
                   GROUP BY 1, 2""")
    out = collections.defaultdict(dict)
    for r, res, n in cur.fetchall():
        out[r][res] = n
    return out


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--per-kind", type=int, default=200)
    ap.add_argument("--seed", type=int, default=6)
    ap.add_argument("--skip-read", action="store_true", help="report on what the branch already holds")
    a = ap.parse_args()
    if a.release:
        sys.exit("REFUSED: item 0 runs on the throwaway branch only")
    url = dbg.checked_url(a.db_url_file)
    pw.net_guard()
    out = []
    log = lambda m: (print(m), out.append(m))
    con = psycopg.connect(url)
    cur = con.cursor()

    # 1. scope
    docs = pw.scope(cur)
    by = collections.Counter((d["kind"], pw.fmt_of(d["mime"])) for d in docs)
    import label_sync_wo02 as ls   # drive NAMES are never printed: the labelled-scope drives by name, others as D-1, D-2 ...
    approved = set(getattr(ls, "APPROVED_DRIVES", ()))
    others = sorted({d["drive"] for d in docs if d["drive"] and d["drive"] not in approved})
    code_of = {n: f"D-{i + 1}" for i, n in enumerate(others)}
    lab = lambda n: ("labelled scope" if n in approved else code_of.get(n)) if n else "(no shared drive)"
    drv = collections.Counter((d["kind"], lab(d["drive"])) for d in docs)
    log(f"ITEM 0 · CAT-WO-06 · {datetime.datetime.now():%Y-%m-%d %H:%M} · in scope {len(docs):,} documents")
    for k in pw.KINDS:
        log(f"  {k:24} " + "  ".join(f"{f}={by[(k, f)]:,}" for f in ("pdf", "gdoc", "word_excel", "image", "other", "no_file") if by[(k, f)]))
    log("  by drive (top 8 per kind):")
    for k in pw.KINDS:
        top = sorted(((n, dname) for (kk, dname), n in drv.items() if kk == k), reverse=True)[:8]
        log(f"    {k:22} " + " · ".join(f"{dname} {n:,}" for n, dname in top))

    # references taken BEFORE any read (R-031 portal, person, folder / name high)
    cur.execute("SELECT to_regclass('cat.doc_content_match') IS NOT NULL")
    if not cur.fetchone()[0]:
        sys.exit("migration 009 is not on this branch")
    ref = collections.defaultdict(set)
    cur.execute("SELECT document_id, partner_code, method FROM cat.doc_party WHERE confidence IN ('high', 'confirmed') AND method IN ('portal', 'folder', 'name', 'label', 'person')")
    ref_kind = collections.Counter()
    for d, p, m in cur.fetchall():
        ref[d].add(p); ref_kind[m] += 1
    cur.execute("SELECT document_id, unnest(subject_codes_confirmed) FROM cat.document WHERE subject_codes_confirmed IS NOT NULL")
    for d, p in cur.fetchall():
        ref[d].add(p)
    before = checklist_counts(cur)
    con.commit()

    # 2. sample and read
    rnd = random.Random(a.seed)
    readable = [d for d in docs if pw.fmt_of(d["mime"]) in ("pdf", "gdoc")]
    sample = []
    for k in pw.KINDS:
        pool = [d for d in readable if d["kind"] == k]
        sample += rnd.sample(pool, min(a.per_kind, len(pool)))
    ids = [d["document_id"] for d in sample]
    t0 = time.time()
    if not a.skip_read:
        home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
        sys.path.insert(0, home)
        os.chdir(home)
        import drive_crawl as dc
        dc.InstalledAppFlow = pw._NoBrowser
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
        cur.execute("DELETE FROM cat.doc_page_read WHERE document_id = ANY(%s)", (ids,)); con.commit()
        pw.run(con, svc, incremental=True, apply=True, log=log, only_ids=ids, connect=lambda: psycopg.connect(url))
        con = psycopg.connect(url); cur = con.cursor()
    secs = time.time() - t0

    # 3. read outcomes
    cur.execute("""SELECT r.document_id, r.outcome, r.text_layer, r.ocr_used, r.page_count, r.statements, r.read_ms, r.tin_present, r.lp_pii
                   FROM cat.doc_page_read r WHERE r.document_id = ANY(%s)""", (ids,))
    reads = {r[0]: r[1:] for r in cur.fetchall()}
    kind_of = {d["document_id"]: d["kind"] for d in sample}
    cur.execute("""SELECT document_id, seq, cand, page_from, page_to, anchor, rule_id, partner_code, roster_entity, confidence, reason
                   FROM cat.doc_content_match WHERE document_id = ANY(%s)""", (ids,))
    cm = collections.defaultdict(list)
    for r in cur.fetchall():
        cm[r[0]].append(r[1:])
    log(f"\nSAMPLE · {len(sample):,} documents ({a.per_kind} per kind where available) · read in {secs:.0f}s")
    for k in pw.KINDS:
        ks = [d for d in ids if kind_of[d] == k and d in reads]
        if not ks: continue
        n = len(ks)
        tl = sum(1 for d in ks if reads[d][1]); ocr = sum(1 for d in ks if reads[d][2])
        oc = collections.Counter(reads[d][0] for d in ks)
        anch = sum(1 for d in ks if any(r[4] for r in cm.get(d, [])))
        best = collections.Counter()
        for d in ks:
            confs = {r[8] for r in cm.get(d, [])}
            best["high" if "high" in confs else "medium" if "medium" in confs else "low" if "low" in confs else "none"] += 1
        log(f"  {k:24} n={n:4}  text layer {100*tl/n:5.1f}%  OCR used {ocr:3}  anchor found {100*anch/n:5.1f}%  "
            f"match high {best['high']:3} medium {best['medium']:3} low {best['low']:3} none {best['none']:3}  outcomes " +
            " ".join(f"{o}={c}" for o, c in sorted(oc.items())))
        reasons = collections.Counter(r[9] for d in ks for r in cm.get(d, []) if r[9])
        if reasons: log(f"  {'':24} reasons: " + ", ".join(f"{x} {c}" for x, c in sorted(reasons.items())))
    ocr_needed = collections.Counter(kind_of[d] for d in reads if reads[d][0] in ("ocr_needed", "ocr_partial"))
    log("  ocr_needed / ocr_partial in sample by kind: " + (", ".join(f"{k} {n}" for k, n in sorted(ocr_needed.items())) or "none"))

    # 4. precision of HIGH matches against references (overall and per rule)
    per_rule = collections.defaultdict(lambda: [0, 0, 0])      # agree, disagree, unmeasured
    for d, rows in cm.items():
        for seq, cand, pf, pt, anchor, rule, p, e, conf, reason in rows:
            if conf != "high" or not p: continue
            if ref.get(d):
                per_rule[rule][0 if p in ref[d] else 1] += 1
            else:
                per_rule[rule][2] += 1
    log(f"\nPRECISION of HIGH matches vs references (portal / person / folder-name high; reference rows by method {dict(ref_kind)})")
    tot = [0, 0, 0]
    review_only = []
    for rid in pw.RULE_IDS:
        ag, dis, un = per_rule.get(rid, [0, 0, 0])
        for i, v in enumerate((ag, dis, un)): tot[i] += v
        if ag + dis + un == 0: continue
        prec = 100 * ag / (ag + dis) if ag + dis else None
        flag = ""
        if prec is not None and prec < 97:
            flag = "  -> REVIEW-ONLY (< 97%)"; review_only.append(rid)
        log(f"  {rid:18} high {ag+dis+un:4}  measured {ag+dis:4}  agree {ag:4}  disagree {dis:3}  precision {('%.1f%%' % prec) if prec is not None else 'n/a':>7}{flag}")
    log(f"  ALL                high {sum(tot):4}  measured {tot[0]+tot[1]:4}  agree {tot[0]:4}  disagree {tot[1]:3}  precision "
        f"{(100*tot[0]/(tot[0]+tot[1])) if tot[0]+tot[1] else 0:.1f}%")
    log("  rules under 97%: " + (", ".join(review_only) or "none"))
    med = collections.defaultdict(lambda: [0, 0, 0])
    for d, rows in cm.items():
        for seq, cand, pf, pt, anchor, rule, p, e, conf, reason in rows:
            if conf != "medium" or not p: continue
            if ref.get(d): med[rule][0 if p in ref[d] else 1] += 1
            else: med[rule][2] += 1
    log("  MEDIUM candidates (lane) vs references, for the dry-run rulings:")
    for rid in pw.RULE_IDS:
        ag, dis, un = med.get(rid, [0, 0, 0])
        if ag + dis + un:
            log(f"  {rid:18} medium {ag+dis+un:4}  measured {ag+dis:4}  agree {ag:4}  disagree {dis:3}  precision "
                f"{('%.1f%%' % (100*ag/(ag+dis))) if ag+dis else 'n/a'}")

    # 5. packages / bundles
    cur.execute("SELECT document_id, entity_code FROM (SELECT DISTINCT document_id, roster_entity entity_code FROM cat.doc_content_match WHERE document_id = ANY(%s) AND roster_entity IS NOT NULL) x", (ids,))
    ent_of = collections.defaultdict(set)
    for d, e in cur.fetchall(): ent_of[d].add(e)
    cur.execute("SELECT entity_code, count(DISTINCT partner_code) FROM ref.party WHERE entity_code IS NOT NULL GROUP BY 1")
    roster_n = dict(cur.fetchall())
    pk = [d for d in reads if (reads[d][4] or 0) > 1]
    log(f"\nPACKAGES / BUNDLES (sample): {len(pk)} documents with more than one statement")
    for k in ("k1", "capital_statement"):
        kp = [d for d in pk if kind_of[d] == k]
        if not kp: continue
        pages = [reads[d][3] or 0 for d in kp]
        ratio = [reads[d][4] / max(1, max((roster_n.get(e, 0) for e in ent_of.get(d, ())), default=0)) for d in kp]
        n_kind = sum(1 for d in ids if kind_of[d] == k)
        log(f"  {k:22} {len(kp)} of {n_kind} sampled ({100*len(kp)/max(1,n_kind):.0f}%) · pages median {statistics.median(pages):.0f} max {max(pages)} · "
            f"statements found / roster size median {statistics.median(ratio):.2f}")

    # 6. checklists before / after (Subject + requirements on the branch)
    import subject_wo03 as sw, requirements_wo03 as rq
    sw.run(con, apply=True, staff=None, log=lambda m: None)
    rq.run_build(con, apply=True, log=lambda m: None)
    after = checklist_counts(cur)
    con.commit()
    scale = {k: (sum(1 for d in readable if d["kind"] == k) / max(1, sum(1 for d in ids if kind_of[d] == k))) for k in pw.KINDS}
    log("\nCHECKLISTS (K1-SET, PCAP-Q from FY2025; LP-SUB) before -> after the SAMPLE read (Met / On file / Missing / No roster)")
    for r in ("K1-SET", "PCAP-Q", "LP-SUB"):
        b, x = before.get(r, {}), after.get(r, {})
        kk = {"K1-SET": "k1", "PCAP-Q": "capital_statement", "LP-SUB": "subscription_agreement"}[r]
        gain = x.get("met", 0) - b.get("met", 0)
        log(f"  {r:7} met {b.get('met',0):5} -> {x.get('met',0):5}  on file {b.get('on_file',0):5} -> {x.get('on_file',0):5}  "
            f"missing {b.get('missing',0):5} -> {x.get('missing',0):5}  no roster {b.get('no_roster',0)} -> {x.get('no_roster',0)}  "
            f"· projected Met gain at full scope ~{round(gain * scale[kk]):,} (sample x{scale[kk]:.1f})")

    # 7. timing
    ms = [reads[d][5] for d in reads if reads[d][5] is not None]
    avg = statistics.mean(ms) / 1000 if ms else 0
    cur.execute("""SELECT count(*) FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id JOIN cat.document d ON d.document_id = fd.document_id
                   WHERE fd.file_role = 'primary' AND f.created_time > now() - interval '30 days'
                     AND coalesce(d.kind_confirmed, d.kind_auto) = ANY(%s)""", (list(pw.KINDS),))
    per_night = cur.fetchone()[0] / 30
    log(f"\nTIMING: read time per document mean {avg:.2f}s, median {statistics.median(ms)/1000 if ms else 0:.2f}s, max {max(ms)/1000 if ms else 0:.1f}s · "
        f"backfill of {len(readable):,} documents ~{avg*len(readable)/3600:.1f} h · nightly ~{per_night:.0f} new documents/night ~{avg*per_night/60:.1f} min "
        f"(cap {pw.NIGHTLY_CAP} -> at most ~{avg*pw.NIGHTLY_CAP/60:.0f} min) · memory peak {pw.mem_mb()[1]} MB")
    con.close()
    os.makedirs(r"C:\DriveCatalog\logs", exist_ok=True)
    with open(os.path.join(r"C:\DriveCatalog\logs", f"wo06_item0_{datetime.datetime.now():%Y%m%d_%H%M}.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
