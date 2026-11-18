"""
CAT-WO-03 item 1: load the newest dated Datum export pair into ref.party / ref.doc_subtype (crawl step `roster`).
PREP: runs against a branch endpoint only; refuses the main endpoint.

  py db/wo03_prep/roster_load.py --owner-url-file C:\\DriveCatalog\\catalog_db_url.txt --endpoint ep-xxxx [--dir C:\\DriveCatalog\\datum_exports]

Checks each file first: exactly the expected columns, and refuses any column that looks like a TIN, address, bank
or amount field. Datum company codes map to catalog entity codes by exact code, then ref.entity_alias (on the code
or the company's legal name); unmapped codes are reported and stored with entity_code NULL, never guessed.
Prints codes and counts only (never an LP name).
"""
import argparse, csv, glob, hashlib, os, re, sys
import psycopg

ROSTER_COLS = ["company_code", "company_kind", "company_name", "partner_code", "relationship_code", "display_name", "legal_name",
               "legal_name_status", "interest_kind", "commitment_date", "active_from", "active_to", "active_from_basis", "active_to_basis"]
SUBTYPE_COLS = ["category_code", "subtype_code", "name", "app_fund", "app_spv", "app_gp", "app_manco", "app_blocker",
                "periodicity", "multiplicity", "active", "document_kind"]
FORBID_TOK = {"tin", "ssn", "ein", "taxid", "tax", "address", "addr", "street", "city", "state", "zip", "postal", "country", "bank",
              "routing", "aba", "account", "acct", "iban", "swift", "amount", "amt", "balance", "usd", "value", "nav",
              "contribution", "distribution", "phone", "email", "dob", "birth"}

ap = argparse.ArgumentParser()
ap.add_argument("--owner-url-file", required=True)
ap.add_argument("--endpoint", required=True, help="branch endpoint id (ep-...); the main endpoint is refused")
ap.add_argument("--dir", default=r"C:\DriveCatalog\datum_exports")
a = ap.parse_args()


def main_url(path):
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        v = line.partition("=")[2].strip().strip("'\"") if not line.startswith("postgres") else line
        if v.startswith("postgres"):
            return v
    sys.exit("no URL in owner url file")


def newest(kind):
    files = sorted(glob.glob(os.path.join(a.dir, f"datum_{kind}_*.csv")))
    if not files:
        sys.exit(f"no datum_{kind}_<date>.csv in {a.dir}")
    f = files[-1]
    m = re.search(r"_(\d{4}-\d{2}-\d{2})\.csv$", f)
    if not m:
        sys.exit(f"undated export file name for {kind}")
    return f, m.group(1)


def read_checked(path, expected):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols = rd.fieldnames or []
        bad = [c for c in cols if set(c.lower().split("_")) & FORBID_TOK]
        if bad:
            sys.exit(f"REFUSED {os.path.basename(path)}: forbidden column(s) {bad}")
        if cols != expected:
            sys.exit(f"REFUSED {os.path.basename(path)}: columns differ from expected (extra={sorted(set(cols)-set(expected))}, missing={sorted(set(expected)-set(cols))})")
        rows = list(rd)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return rows, sha


url = main_url(a.owner_url_file)
m = re.search(r"@(ep-[a-z0-9-]+?)(-pooler)?\.", url)
if not m or m.group(1) == a.endpoint:
    sys.exit("REFUSED: --endpoint must be a branch endpoint, not main")
url = url[: m.start(1)] + a.endpoint + url[(m.end(2) if m.group(2) else m.end(1)):]

rf, rdate = newest("partner_roster")
sf, sdate = newest("doc_subtype")
roster, rsha = read_checked(rf, ROSTER_COLS)
subs, ssha = read_checked(sf, SUBTYPE_COLS)
print(f"checked: partner_roster {rdate} rows={len(roster)} cols OK; doc_subtype {sdate} rows={len(subs)} cols OK")

con = psycopg.connect(url)
with con.transaction():
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

    # The fund's own GP row: the partner's legal OR display name equals a Datum GP company's name or code
    # (NL-I's GP row matches only on display name).
    gp_names = ({r["company_name"].strip().lower() for r in roster if r["company_kind"] == "gp"}
                | {r["company_code"].strip().lower() for r in roster if r["company_kind"] == "gp"})
    is_gp = lambda r: r["legal_name"].strip().lower() in gp_names or r["display_name"].strip().lower() in gp_names
    comp = {}
    for r in roster:
        comp.setdefault(r["company_code"], (r["company_kind"], r["company_name"]))
    cmap = {k: map_company(k, v[1]) for k, v in comp.items()}

    cur.execute("DELETE FROM ref.party")
    # Subtypes are upserted below; one missing from the new export is marked inactive, never deleted
    # (rules, applicability and the subtype->kind mapping reference them).
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
    print(f"loaded ref.party rows={n_party} mapped={n_ent} unmapped={n_unm}; ref.doc_subtype rows={cur.execute('SELECT count(*) FROM ref.doc_subtype').fetchone()[0]}")
    for how in ("exact", "alias_code", "alias_name", "ambiguous_alias", "unmapped"):
        ks = sorted(k for k, v in cmap.items() if v[1] == how)
        if ks:
            print(f"  {how:16} {len(ks):2}  " + ", ".join(f"{k}->{cmap[k][0]}" if cmap[k][0] else k for k in ks))
