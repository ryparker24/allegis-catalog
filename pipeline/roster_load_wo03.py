r"""
CAT-WO-03 item 1 · crawl step `roster`: load the newest dated Datum export pair into ref.party / ref.doc_subtype,
and seed ref.party_alias (display + legal name) for name matching. Runs before `derive`.

  py pipeline\roster_load_wo03.py --db-url-file <branch url file> [--dir C:\DriveCatalog\datum_exports] [--apply] [--release]

Checks each file first: exactly the expected columns, and refuses any column that looks like a TIN, address, bank or
amount field. Datum company codes map to catalog entity codes by exact code, then ref.entity_alias (on the code or the
company's legal name); unmapped codes are reported and stored with entity_code NULL, never guessed.
Without --apply the load runs inside a transaction that is rolled back (a dry run). Prints codes and counts only.
Later: when Datum's views exist this step reads them instead, and the CSV path is retired.
"""
import argparse, csv, glob, hashlib, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbguard_wo03 as dbg

ROSTER_COLS = ["company_code", "company_kind", "company_name", "partner_code", "relationship_code", "display_name", "legal_name",
               "legal_name_status", "interest_kind", "commitment_date", "active_from", "active_to", "active_from_basis", "active_to_basis"]
SUBTYPE_COLS = ["category_code", "subtype_code", "name", "app_fund", "app_spv", "app_gp", "app_manco", "app_blocker",
                "periodicity", "multiplicity", "active", "document_kind"]
FORBID_TOK = {"tin", "ssn", "ein", "taxid", "tax", "address", "addr", "street", "city", "state", "zip", "postal", "country", "bank",
              "routing", "aba", "account", "acct", "iban", "swift", "amount", "amt", "balance", "usd", "value", "nav",
              "contribution", "distribution", "phone", "email", "dob", "birth", "commitment_amount"}


def forbidden_columns(cols):
    """Column names that look like a TIN / address / bank / amount / contact field (split on _ and spaces)."""
    return [c for c in cols if set(re.split(r"[_\s]+", c.lower())) & FORBID_TOK]


def newest(dirpath, kind):
    files = sorted(glob.glob(os.path.join(dirpath, f"datum_{kind}_*.csv")))
    if not files:
        sys.exit(f"no datum_{kind}_<date>.csv in the export folder")
    f = files[-1]
    m = re.search(r"_(\d{4}-\d{2}-\d{2})\.csv$", f)
    if not m:
        sys.exit(f"undated export file name for {kind}")
    return f, m.group(1)


def read_checked(path, expected):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols = rd.fieldnames or []
        bad = forbidden_columns(cols)
        if bad:
            sys.exit(f"REFUSED {os.path.basename(path)}: forbidden column(s) {bad}")
        if cols != expected:
            sys.exit(f"REFUSED {os.path.basename(path)}: columns differ from expected (extra={sorted(set(cols)-set(expected))}, missing={sorted(set(expected)-set(cols))})")
        rows = list(rd)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return rows, sha


CODE_RE = re.compile(r"^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$")


DEFAULT_DIR = r"C:\DriveCatalog\datum_exports"


def run(con, dirpath=DEFAULT_DIR, apply=False, log=print):
    """The load on an open connection (nightly hook in drive_crawl.py, or main). Commits only when apply."""
    import psycopg
    rf, rdate = newest(dirpath, "partner_roster")
    sf, sdate = newest(dirpath, "doc_subtype")
    roster, rsha = read_checked(rf, ROSTER_COLS)
    subs, ssha = read_checked(sf, SUBTYPE_COLS)
    bad_codes = sum(1 for r in roster if not CODE_RE.match(r["partner_code"]))
    if bad_codes:
        raise SystemExit(f"REFUSED: {bad_codes} partner code(s) not in the LP- / GM- / GPM- shape")
    log(f"checked: partner_roster {rdate} rows={len(roster)} cols OK; doc_subtype {sdate} rows={len(subs)} cols OK")

    with con.transaction() as tx:
        cur = con.cursor()
        codes = {r[0] for r in cur.execute("SELECT entity_code FROM ref.entity")}
        alias = {}
        for al, e in cur.execute("SELECT lower(alias), entity_code FROM ref.entity_alias WHERE NOT coalesce(generic, false)"):
            alias.setdefault(al, set()).add(e)

        def map_company(code, name):
            if code in codes:
                return code, "exact"
            for key, how in ((code.strip().lower(), "alias_code"), (name.strip().lower(), "alias_name")):
                hit = alias.get(key)
                if hit and len(hit) == 1:
                    return next(iter(hit)), how
                if hit and len(hit) > 1:
                    return None, "ambiguous_alias"
            return None, "unmapped"

        # the fund's own GP row: the partner's legal OR display name equals a Datum GP company's name or code
        gp_names = ({r["company_name"].strip().lower() for r in roster if r["company_kind"] == "gp"}
                    | {r["company_code"].strip().lower() for r in roster if r["company_kind"] == "gp"})
        is_gp = lambda r: r["legal_name"].strip().lower() in gp_names or r["display_name"].strip().lower() in gp_names
        comp = {}
        for r in roster:
            comp.setdefault(r["company_code"], (r["company_kind"], r["company_name"]))
        cmap = {k: map_company(k, v[1]) for k, v in comp.items()}

        cur.execute("DELETE FROM ref.party")
        cur.execute("UPDATE ref.doc_subtype SET active = false WHERE NOT (subtype_code = ANY(%s))", ([s["subtype_code"] for s in subs],))
        d = lambda s: s or None
        cur.executemany(
            """INSERT INTO ref.party (datum_company_code, datum_company_kind, datum_company_name, entity_code, partner_code, relationship_code,
                 display_name, legal_name, legal_name_status, interest_kind, is_company_gp, commitment_date, active_from, active_to,
                 active_from_basis, active_to_basis, export_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(r["company_code"], r["company_kind"], r["company_name"], cmap[r["company_code"]][0], r["partner_code"], r["relationship_code"],
              r["display_name"], r["legal_name"], d(r["legal_name_status"]), r["interest_kind"], is_gp(r),
              d(r["commitment_date"]), d(r["active_from"]), d(r["active_to"]), d(r["active_from_basis"]), d(r["active_to_basis"]), rdate)
             for r in roster])
        # aliases: Datum-sourced rows are replaced on every load; Ryan's rows are never touched
        cur.execute("DELETE FROM ref.party_alias WHERE source = 'datum'")
        al_rows = sorted({(r["partner_code"], n.strip()) for r in roster for n in (r["display_name"], r["legal_name"]) if n and n.strip()})
        cur.executemany("INSERT INTO ref.party_alias (partner_code, alias, source) VALUES (%s, %s, 'datum') ON CONFLICT DO NOTHING", al_rows)
        cur.executemany(
            """INSERT INTO ref.doc_subtype (subtype_code, category_code, name, app_fund, app_spv, app_gp, app_manco, app_blocker, periodicity,
                 multiplicity, active, datum_document_kind, export_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (subtype_code) DO UPDATE SET category_code=EXCLUDED.category_code, name=EXCLUDED.name, app_fund=EXCLUDED.app_fund,
                 app_spv=EXCLUDED.app_spv, app_gp=EXCLUDED.app_gp, app_manco=EXCLUDED.app_manco, app_blocker=EXCLUDED.app_blocker,
                 periodicity=EXCLUDED.periodicity, multiplicity=EXCLUDED.multiplicity, active=EXCLUDED.active,
                 datum_document_kind=EXCLUDED.datum_document_kind, export_date=EXCLUDED.export_date""",
            [(s["subtype_code"], s["category_code"], s["name"].replace("\ufffd", "-"), s["app_fund"], s["app_spv"], s["app_gp"], s["app_manco"],
              s["app_blocker"], s["periodicity"], s["multiplicity"], s["active"].strip().lower() == "true", d(s["document_kind"]), sdate) for s in subs])
        for kind, f, dt, sha, n in (("partner_roster", rf, rdate, rsha, len(roster)), ("doc_subtype", sf, sdate, ssha, len(subs))):
            cur.execute("""INSERT INTO ref.datum_export (file_kind, export_date, file_name, sha256, row_count) VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT (file_kind, export_date) DO UPDATE SET sha256=EXCLUDED.sha256, row_count=EXCLUDED.row_count, loaded_at=now()""",
                        (kind, dt, os.path.basename(f), sha, n))

        n_party, n_ent, n_unm = cur.execute("SELECT count(*), count(entity_code), count(*) - count(entity_code) FROM ref.party").fetchone()
        n_alias = cur.execute("SELECT count(*) FROM ref.party_alias").fetchone()[0]
        n_sub = cur.execute("SELECT count(*) FROM ref.doc_subtype").fetchone()[0]
        log(f"{'loaded' if apply else 'DRY RUN (rolled back)'}: ref.party rows={n_party} mapped={n_ent} unmapped={n_unm}; "
              f"ref.party_alias rows={n_alias}; ref.doc_subtype rows={n_sub}")
        for how in ("exact", "alias_code", "alias_name", "ambiguous_alias", "unmapped"):
            ks = sorted(k for k, v in cmap.items() if v[1] == how)
            if ks:
                log(f"  {how:16} {len(ks):2}  " + ", ".join(f"{k}->{cmap[k][0]}" if cmap[k][0] else k for k in ks))
        if not apply:
            raise psycopg.Rollback(tx)


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    con = psycopg.connect(url)
    try:
        run(con, a.dir, apply=a.apply)
    finally:
        con.close()


if __name__ == "__main__":
    main()
