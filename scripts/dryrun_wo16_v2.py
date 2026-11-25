r"""CAT-WO-16 dry run of BANK-L4 v2 (R-068 widenings) next to v1, on the THROWAWAY that already holds the v1 dry run.

  py scripts\dryrun_wo16_v2.py --db-url-file <throwaway url file> --out docs\CAT-WO-16_DRYRUN_v2.md [--no-pages] [--seed 16]

1. migration 016 again (re-runnable: page-read v2 columns, BANK-L4 v2 inactive)
2. baseline = the labelled scope with no BANK-L4 signal (in a rolled-back transaction)
3. page 1 again (Drive READ, in memory) for every document v1's name / path did not match, plus a random 50 of the documents only
   v2's file-name form matches (the spot check), storing codes / a has-account-number flag only
4. apply v1, snapshot; apply v2, snapshot (the throwaway ends on v2)
Codes and counts only: never a name, a path or a digit."""
import argparse, collections, datetime, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg

SCOPE_FILES = """SELECT x.file_id, coalesce(x.kind, '(no kind)'), x.entities FROM app.v_find_x x JOIN cat.file f ON f.file_id = x.file_id
                 WHERE x.kind IN ('bank_stmt', 'wire_confirmation') OR (x.kind IS NULL AND (f.folder_path ILIKE '%/03-Cash/%' OR f.folder_path ILIKE '%/03-Cash'))"""
RISK = {"1121", "1533", "1541", "1543", "1558", "1507", "1725", "0285"}     # from the brief: date-like mapped numbers


def snap(con):
    with con.cursor() as cur:
        cur.execute(SCOPE_FILES)
        return {f: (k, tuple(sorted(e or []))) for f, k, e in cur.fetchall()}


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-pages", action="store_true")
    ap.add_argument("--seed", type=int, default=16)
    ap.add_argument("--branch-name", default="catwo16-throwaway")
    ap.add_argument("--map", help="load ref.bank_account from this csv first (a fresh throwaway)")
    ap.add_argument("--full-derive", action="store_true", help="run the nightly's derive after migration 016 (a fresh throwaway)")
    a = ap.parse_args()
    if a.release:
        sys.exit("REFUSED: the CAT-WO-16 dry run never runs on main")
    url = dbg.checked_url(a.db_url_file, False)
    connect = lambda: psycopg.connect(url)
    log, T = [], {}
    lg = lambda m: (log.append(m), print(m, flush=True))
    import bank_wo16 as bw

    with psycopg.connect(url, autocommit=True) as mc:
        mc.execute(open(os.path.join(HERE, "..", "db", "migrations", "016_wo16.sql"), encoding="utf-8").read())
    if a.map:
        with connect() as con:
            bw.load_map_csv(con, a.map, log=lg)
    if a.full_derive:
        # the nightly's derive (CAT-WO-17 changed ops.build_documents step 1: primaries from preferred folders), pages off;
        # apply_derive's hook runs BANK-L4 (v1, the active version) as the nightly would
        os.environ["CATWO06_PAGES"] = "0"; os.environ["CATWO16_PAGES"] = "0"
        with connect() as con:
            for fn in ("ops.rebuild_folder_ancestors()", "ops.apply_rules()", "ops.build_documents()", "ops.apply_content_checks()"):
                t = time.time()
                with con.cursor() as cur:
                    cur.execute(f"SELECT * FROM {fn}")
                    rows = cur.fetchall() if cur.description else []
                con.commit()
                lg(f"  {fn}: " + (", ".join(f"{r[0]} {r[1]}" for r in rows if len(r) > 1) or "done") + f" ({time.time() - t:.0f}s)")
            import apply_derive_wo02
            t = time.time(); apply_derive_wo02.run(con, apply=True, log=lambda m: None); T["full derive"] = time.time() - t
            lg("  apply_derive done (incl. BANK-L4 v1 hook)")
    with connect() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM cat.file_signal WHERE rule_id = %s", (bw.RULE_ID,))
        base = snap(con)
        con.rollback()
        l4 = bw.load_map(cur); rx = bw.cue_regex(l4)
        docs = bw.scope(cur)
        _, spec2 = bw.rule_spec(cur, 2)
        con.commit()
    v1_unmatched = bw.unmatched_by_name_path(docs, rx, l4, {})
    by_id = {d["document_id"]: d for d in docs}
    # documents only v2's file-name form matches (not v1's cue in a name or a path)
    v2_only = [d for d in docs if not d["person"]
               and not any(bw.find_codes(t, rx, l4) for t in (d["names"] or []) + (d["paths"] or []))
               and any(bw.delimited_codes(t, l4) for t in (d["names"] or []))]
    random.seed(a.seed)
    sample = random.sample(v2_only, min(50, len(v2_only)))
    pages_c = None
    if not a.no_pages:
        import pages_wo06 as pw
        pw.net_guard()
        home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
        if home not in sys.path: sys.path.insert(0, home)
        cwd = os.getcwd(); os.chdir(home)                 # the crawler's token file lives there (never read here)
        import drive_crawl as dc
        dc.InstalledAppFlow = pw._NoBrowser
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
        os.chdir(cwd)
        todo = {d["document_id"]: d for d in v1_unmatched + sample}
        with connect() as con:
            t = time.time()
            con, pages_c = bw.read_pages(con, svc, list(todo.values()), rx, l4, log=lg, connect=connect, force=True)
            T["pages"] = time.time() - t
    res, snaps, lanes = {}, {}, {}
    for v in (1, 2):
        with connect() as con:
            t = time.time(); res[v] = bw.apply(con, apply=True, log=lg, version=v); T[f"v{v}"] = time.time() - t
            snaps[v] = snap(con)
            with con.cursor() as cur:
                cur.execute("""SELECT count(DISTINCT q.document_id) FROM app.v_review_queue q
                               WHERE q.queue_reason = 'content_disagrees' AND q.kind IN ('bank_stmt', 'wire_confirmation')""")
                lanes[v] = cur.fetchone()[0]
            con.commit()
    # spot check: the sample's file-name code vs page 1 (where page 1 shows an account number)
    with connect() as con, con.cursor() as cur:
        cur.execute("SELECT document_id, codes_v2, has_account_number, outcome FROM ops.bank_page_read WHERE document_id = ANY(%s)",
                    ([d["document_id"] for d in sample],))
        pr = {d: (set(c or ()), h, o) for d, c, h, o in cur.fetchall()}
    sc = collections.Counter()
    for d in sample:
        name_code = set().union(*[bw.delimited_codes(t, l4) for t in d["names"]])
        page_codes, has_acct, oc = pr.get(d["document_id"], (set(), None, "not_read"))
        if not has_acct:
            sc["page 1 shows no account number" if oc not in ("skipped_format", "download_error", "open_error", "too_large", "not_read") else "page 1 not readable"] += 1
        elif page_codes == name_code:
            sc["agree"] += 1
        elif page_codes:
            sc["disagree (another mapped account)"] += 1
        else:
            sc["disagree (account number not in the map)"] += 1
    # date-risk numbers among v2's file-name matches, and the date-guard skips
    risk_by_ent, skipped = collections.Counter(), collections.Counter()
    for d in v2_only:
        for t in d["names"] or []:
            stem = t.rsplit(".", 1)[0] if "." in t[-6:] else t
            bw.delimited_codes(t, l4, skipped)
            for m in bw._DELIM_TOKEN.finditer(stem):
                if m.group(1) in RISK and m.group(1) in l4 and not bw.date_shaped(stem, m.start(1), m.end(1)):
                    for e in l4[m.group(1)]:
                        risk_by_ent[e] += 1

    def noent(s, kind):
        return sum(1 for k, e in s.values() if k == kind and not e)

    def labels(s):
        return sum(1 for f, (k, e) in s.items() if base.get(f) and base[f][1] != e)

    def oc(v, o):
        return sum(n for (k, x), n in res[v]["outcomes"].items() if x == o)

    L = ["# CAT-WO-16 · BANK-L4 v2 (R-068 widenings) next to v1 · dry run (throwaway)", "",
         f"Run {datetime.datetime.now():%Y-%m-%d %H:%M} local on throwaway `{a.branch_name}`; main untouched. No Drive or label writes: "
         "Drive was only READ (page 1). Codes and counts only: no names, paths or account digits. v2 is stored INACTIVE (BANK-L4 v2) "
         "until Ryan rules; the nightly would keep using v1.", "",
         "v2 = v1 plus (a) a mapped 4-digit token set off by - _ . or spaces in the file name, skipped inside a date-shaped run "
         "(MMDD-YYYY, YYYY-MMDD, MMDD-YY, MM-DD-YY pieces) and ambiguous when a name holds two different mapped accounts, and (b) on page 1 "
         "the last 4 of a longer account number after Account / Acct / Account Number / A/C.", "",
         "## Per version (documents in scope: bank_stmt, wire_confirmation, no-kind under 03-Cash)", "",
         "| | v1 | v2 |", "|---|---:|---:|"]
    for lab, o in (("Newly given an entity", "set"), ("Confirmations (entity already there)", "agrees"),
                   ("Conflicts (-> Content disagrees, not written)", "conflict"), ("Ambiguous (2 mapped accounts)", "ambiguous"),
                   ("Person-set (skipped)", "person"), ("No match", "none")):
        L.append(f"| {lab} | {oc(1, o):,} | {oc(2, o):,} |")
    L.append(f"| Bank statements / wire confirmations in the Content disagrees lane | {lanes[1]:,} | {lanes[2]:,} |")
    L.append(f"| Labelled bank statements with no entity ({noent(base, 'bank_stmt'):,} before) | {noent(snaps[1], 'bank_stmt'):,} | {noent(snaps[2], 'bank_stmt'):,} |")
    L.append(f"| Labelled wire confirmations with no entity ({noent(base, 'wire_confirmation')} before) | {noent(snaps[1], 'wire_confirmation'):,} | {noent(snaps[2], 'wire_confirmation'):,} |")
    L.append(f"| Label writes (labelled files whose Entity would change) | {labels(snaps[1]):,} | {labels(snaps[2]):,} |")
    L += ["", "Where the last 4 was found: v1 " + ", ".join(f"{k} {n:,}" for k, n in sorted(res[1]["by_source"].items()))
          + " · v2 " + ", ".join(f"{k} {n:,}" for k, n in sorted(res[2]["by_source"].items())) + " documents.", ""]
    if pages_c is not None:
        L += ["Page 1 (re-read, " + f"{sum(v for k, v in pages_c.items() if not k.startswith('v2:')):,} documents): v1 pattern "
              + ", ".join(f"{k} {v:,}" for k, v in sorted(pages_c.items()) if not k.startswith("v2:"))
              + " · v2 pattern " + ", ".join(f"{k[3:]} {v:,}" for k, v in sorted(pages_c.items()) if k.startswith("v2:")) + ".", ""]
    L += ["## Matches by entity (documents given or confirmed)", "", "| Entity | v1 | v2 |", "|---|---:|---:|"]
    for e in sorted(set(res[1]["by_entity"]) | set(res[2]["by_entity"])):
        L.append(f"| {e} | {res[1]['by_entity'].get(e, 0):,} | {res[2]['by_entity'].get(e, 0):,} |")
    n_acct = sum(n for k, n in sc.items() if k.startswith("agree") or k.startswith("disagree"))
    L += ["", f"## Spot check: {len(sample)} random documents matched ONLY by v2's file-name form, against page 1", "",
          f"Documents only v2's file-name form matches: {len(v2_only):,}.", "",
          "| Page 1 | Documents |", "|---|---:|"] + [f"| {k} | {n} |" for k, n in sorted(sc.items())]
    L += ["", f"**Agreement where page 1 shows an account number: {sc['agree']} of {n_acct}"
          + (f" ({100 * sc['agree'] / n_acct:.0f}%)" if n_acct else "") + ".**", "",
          "## Date-risk numbers (the brief's list of mapped numbers that read like dates)", "",
          f"v2 file-name matches on a date-risk number (after the date guard): {sum(risk_by_ent.values()):,} tokens"
          + (" (" + ", ".join(f"{e} {n:,}" for e, n in sorted(risk_by_ent.items())) + ")" if risk_by_ent else "")
          + f". Tokens the date guard skipped (all mapped numbers): {sum(skipped.values()):,}.", "",
          "## Timings", "", ", ".join(f"{k} {v:.0f}s" for k, v in T.items()), "", "## Log", "", "```"] + log[-30:] + ["```", ""]
    open(a.out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
