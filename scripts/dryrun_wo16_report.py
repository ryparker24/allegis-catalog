r"""CAT-WO-16 dry run on a THROWAWAY branch: BANK-L4 (bank statement entity from the account's last 4).

  py scripts\dryrun_wo16_report.py --db-url-file <throwaway url file> --map <csv> --out docs\CAT-WO-16_DRYRUN.md [--no-pages]

Before snapshot -> migration 016 -> ref.bank_account from the map -> page 1 of the documents no name / path matched (Drive
READ only) -> the rule -> after snapshot. Codes and counts only: never a name, a path or a digit."""
import argparse, collections, datetime, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import dbguard_wo03 as dbg

SCOPE_FILES = """SELECT x.file_id, coalesce(x.kind, '(no kind)'), x.entities FROM app.v_find_x x JOIN cat.file f ON f.file_id = x.file_id
                 WHERE x.kind IN ('bank_stmt', 'wire_confirmation') OR (x.kind IS NULL AND (f.folder_path ILIKE '%/03-Cash/%' OR f.folder_path ILIKE '%/03-Cash'))"""


def q(con, sql, params=None):
    with con.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchall() if cur.description else None
    con.commit()
    return r


def snap(con):
    return {f: (k, tuple(sorted(e or []))) for f, k, e in q(con, SCOPE_FILES)}


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-pages", action="store_true")
    ap.add_argument("--branch-name", default="catwo16-throwaway")
    a = ap.parse_args()
    if a.release:
        sys.exit("REFUSED: the CAT-WO-16 dry run never runs on main")
    url = dbg.checked_url(a.db_url_file, False)
    connect = lambda: psycopg.connect(url)
    log, T = [], {}
    lg = lambda m: (log.append(m), print(m, flush=True))
    import bank_wo16 as bw

    with connect() as con:
        if q(con, "SELECT to_regclass('ref.bank_account') IS NOT NULL")[0][0]:
            sys.exit("REFUSED: migration 016 is already on this branch")
        before = snap(con)
        cd_before = q(con, "SELECT content_disagrees FROM app.v_review_counts")[0][0]
    with psycopg.connect(url, autocommit=True) as mc:
        mc.execute(open(os.path.join(HERE, "..", "db", "migrations", "016_wo16.sql"), encoding="utf-8").read())
    with connect() as con:
        mp = bw.load_map_csv(con, a.map, log=lg)
    pages_c = None
    if not a.no_pages:
        import pages_wo06 as pw
        pw.net_guard()
        home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
        if home not in sys.path: sys.path.insert(0, home)
        cwd = os.getcwd(); os.chdir(home)              # the crawler's token file lives there (never read here)
        import drive_crawl as dc
        dc.InstalledAppFlow = pw._NoBrowser
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=dc.creds(), cache_discovery=False)
        os.chdir(cwd)
        with connect() as con:
            cur = con.cursor()
            l4 = bw.load_map(cur); rx = bw.cue_regex(l4)
            todo = bw.unmatched_by_name_path(bw.scope(cur), rx, l4)
            con.commit()
            t = time.time(); con, pages_c = bw.read_pages(con, svc, todo, rx, l4, log=lg, connect=connect); T["pages"] = time.time() - t
    with connect() as con:
        t = time.time(); res = bw.apply(con, apply=True, log=lg); T["rule"] = time.time() - t
        after = snap(con)
        cd_after = q(con, "SELECT content_disagrees FROM app.v_review_counts")[0][0]
        bank_cd = q(con, """SELECT count(DISTINCT q.document_id) FROM app.v_review_queue q JOIN cat.doc_content_check c ON c.document_id = q.document_id
                            WHERE q.queue_reason = 'content_disagrees' AND q.kind IN ('bank_stmt', 'wire_confirmation')""")[0][0]
        mapped = q(con, "SELECT entity_code, count(*) FROM ref.bank_account GROUP BY 1 ORDER BY 1")

    def noent(s, kind):
        return sum(1 for k, e in s.values() if k == kind and not e)
    lab_changes = collections.Counter()
    ent_added = collections.Counter()
    for f, (k, e) in after.items():
        b = before.get(f)
        if b and b[1] != e:
            lab_changes[k] += 1
            for x in set(e) - set(b[1]):
                ent_added[x] += 1
    oc = res.get("outcomes", {})
    kinds = sorted({k for k, _ in oc})
    L = ["# CAT-WO-16 · Bank statement entity from the account's last 4 · dry run (throwaway)", "",
         f"Run {datetime.datetime.now():%Y-%m-%d %H:%M} local on throwaway `{a.branch_name}` (from main; main untouched). No Drive or "
         "label writes: Drive was only READ (page 1 of statements no name / path matched). Codes and counts only: no names, paths "
         "or account digits (ref.bank_account is loaded from the map file outside the repo).", "",
         "## Map", "", f"Rows loaded: {mp['loaded']}; entities: {len(mapped)}; last-4s mapped to more than one entity: {mp['shared']}.", "",
         "Codes in the map that are not in ref.entity (skipped, not invented): "
         + (", ".join(f"`{c}` ({n} row{'s' if n > 1 else ''})" for c, n in sorted(mp["unknown"].items())) or "none") + ".", "",
         "| Entity | Accounts mapped |", "|---|---:|"]
    L += [f"| {e} | {n} |" for e, n in mapped]
    L += ["", "## Bank statements with no entity (labelled files)", "",
          "| Kind | Files | No entity before | No entity after |", "|---|---:|---:|---:|"]
    for k in sorted({k for k, _ in before.values()}):
        L.append(f"| {k} | {sum(1 for kk, _ in after.values() if kk == k):,} | {noent(before, k):,} | {noent(after, k):,} |")
    L += ["", "## Outcomes per document (scope: bank_stmt, wire_confirmation, no-kind under 03-Cash; all copies)", "",
          "| Kind | Entity set | Agrees with an existing entity | Conflict (-> Content disagrees) | Ambiguous (2 entities) | Person-set (skipped) | No match |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for k in kinds:
        g = lambda o: oc.get((k, o), 0)
        L.append(f"| {k} | {g('set'):,} | {g('agrees'):,} | {g('conflict'):,} | {g('ambiguous'):,} | {g('person'):,} | {g('none'):,} |")
    L += ["", "Where the last 4 was found: " + ", ".join(f"{s} {n:,}" for s, n in sorted(res.get('by_source', {}).items())) + " documents.", ""]
    if pages_c is not None:
        L += ["Page 1 reads (documents no name / path matched): " + ", ".join(f"{k} {v:,}" for k, v in sorted(pages_c.items())) + ".", ""]
    L += ["## Matches by entity (documents given or confirmed by BANK-L4)", "", "| Entity | Documents |", "|---|---:|"]
    L += [f"| {e} | {n:,} |" for e, n in sorted(res.get("by_entity", {}).items())]
    L += ["", "## Conflicts", "",
          f"Content disagrees lane: {cd_before:,} -> {cd_after:,} (bank statements / wire confirmations in the lane now: {bank_cd:,}). "
          "A conflict is never written as an entity; the lane shows it for a person.", "",
          "## Label writes it would make (nightly re-sync of labelled files; not written)", "",
          f"Labelled files whose Entity label would change: {sum(lab_changes.values()):,} ("
          + ", ".join(f"{k} {n:,}" for k, n in sorted(lab_changes.items())) + "). Entities added: "
          + ", ".join(f"{e} {n:,}" for e, n in sorted(ent_added.items())) + ".", "",
          "## Timings", "", ", ".join(f"{k} {v:.0f}s" for k, v in T.items()), "", "## Log", "", "```"] + log + ["```", ""]
    open(a.out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print("\n".join(L[:30]))


if __name__ == "__main__":
    main()
