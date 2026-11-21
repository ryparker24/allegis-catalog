"""CAT-WO-05 · portal postings, Issued + Published To, R-032 status rules. Offline (no DB, no Drive, no portal).
Invented names and IDs only. DB guards (person Status survives, idempotent re-run, no name in the catalog, streamed
batches) are in db/tests/test_wo05_guards.py."""
import csv, datetime, inspect, io, json, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portals_wo05 as pw
import catalog_labels as cl
import label_sync_wo02 as ls

R = []
def check(name, cond, detail=""):
    R.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + (f"  -- {detail}" if detail and not cond else ""))

D = datetime.date

# ------------------------------------------------------------------ G-P1 nothing is ever written to either portal
src = inspect.getsource(pw)
export_sqls = [pw.LP_EXPORT_SQL, pw.GP_EXPORT_SQL, pw.GP_XW_SQL]
write_kw = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER|CREATE|GRANT|COPY)\b", re.I)
exp_src = inspect.getsource(pw.export_from_portals)
check("G-P1 nothing is ever written to either portal: the only portal queries are three SELECTs, run in a READ ONLY "
      "session, and the module opens no other portal connection",
      all(s.lstrip().upper().startswith("SELECT") and not write_kw.search(s) for s in export_sqls)
      and "con.read_only = True" in exp_src and exp_src.count("psycopg.connect(") == 1
      and src.count("LP_URL_FILE") + src.count("GP_URL_FILE") >= 2
      and "execute(" not in exp_src.replace("con.execute(sql)", ""))

# ------------------------------------------------------------------ G-P2 no partner name enters the catalog
check("G-P2a an export with a name-like column is REFUSED (investor_name, display_name, doc_title, email, title)",
      all(pw.forbidden_columns([c]) for c in ("investor_name", "display_name", "doc_title", "primary_email", "title", "member_name"))
      and not pw.forbidden_columns(pw.LP_COLS + pw.GP_COLS + pw.XW_COLS))
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "lp_postings_2026-01-01.csv")
    with open(p, "w", newline="") as fh:
        csv.writer(fh).writerows([pw.LP_COLS + ["investor_name"], ["1", "1AbCdEfGhIjKlMnOp", "LP-0001", "FUND-0001", "QR", "2026-Q1", "2026-04-01", "1", "Invented Person"]])
    try:
        pw.read_checked(p, pw.LP_COLS); refused = False
    except SystemExit as e:
        refused = "REFUSED" in str(e) and "Invented" not in str(e)
check("G-P2b reading such a file stops before any row is used, and the refusal names the column, never a value", refused)
# the GP crosswalk: names are hashed on both sides; the roster name never reaches a row
roster_name = "Invented Partner Smith"
hidx = {h: {"GM-0101"} for h in pw.name_hashes(roster_name)}
xw = {"77": {pw.hashlib.md5(pw.norm_name("Smith, Invented Partner").encode()).hexdigest(),
             pw.hashlib.md5(" ".join(sorted(pw.norm_name("Smith, Invented Partner").split())).encode()).hexdigest()}}
row = pw.map_partner("gp", "77", None, {"GM-0101"}, hidx, xw, {"GM-0101": {"FUND-A (GP)"}}, {"GM-0101"})
check("G-P2c a GP member maps through name HASHES (token order ignored) to its roster code; the row holds codes only",
      row == ("M77", "GM-0101", "crosswalk", None) and roster_name.lower() not in json.dumps(row).lower())
check("G-P2d the L10 Posting ID keeps portal IDs only: anything else read from Drive is dropped",
      cl.postids_from_text("LPD-12, GPD-345, Invented Person, LP-0001") == ["GPD-345", "LPD-12"])
e = cl.expected({"published_ids": ["LPD-1", "Invented Name"], "published_channels": ["lp_portal"], "published_date": D(2026, 8, 15)},
                cl.Schema({"published": {"label_id": "L10", "title": "Published To", "fields": {
                    "channel": {"field_id": "c", "type": "selectionOptions", "choices": {"lp_portal": "c1", "gp_portal": "c2", "datum": "c3", "email": "c4"}},
                    "posted_date": {"field_id": "d", "type": "dateOptions"}, "posting_id": {"field_id": "t", "type": "textOptions"}}}}))
check("G-P2e the machine writes posting IDs only to L10 (a non-ID value never reaches the label)", e["published_ids"] == ["LPD-1"])

# ------------------------------------------------------------------ partner mapping
check("LP partner: exact when the code is on the Datum roster, else unmapped (never guessed)",
      pw.map_partner("lp", "LP-0003", "X", {"LP-0003"}) == ("LP-0003", "LP-0003", "exact", None)
      and pw.map_partner("lp", "LP-0999", "X", {"LP-0003"}) == ("LP-0999", None, "unmapped", None)
      and pw.map_partner("lp", "", "X", {"LP-0003"})[2] == "fund_level")
amb = pw.map_partner("gp", "5", None, set(), {"h": {"GM-0001", "GPM-77", "LP-0009"}}, {"5": {"h"}},
                     {"GM-0001": {"A (GP)"}, "GPM-77": {"B (GP)"}, "LP-0009": {"FUND"}}, {"GM-0001", "GPM-77"})
check("GP member with a code per relationship: GP-roster codes preferred; still two -> ambiguous with candidates, no code",
      amb == ("M5", None, "ambiguous", ["GM-0001", "GPM-77"]))
check("an ambiguous posting resolves per document only when exactly one candidate's entity is on the document",
      pw.resolve_for_document(["GM-0001", "GPM-77"], {"B (GP)"}, {"GM-0001": {"A (GP)"}, "GPM-77": {"B (GP)"}}) == "GPM-77"
      and pw.resolve_for_document(["GM-0001", "GPM-77"], {"A (GP)", "B (GP)"}, {"GM-0001": {"A (GP)"}, "GPM-77": {"B (GP)"}}) is None
      and pw.resolve_for_document(["GM-0001"], set(), {"GM-0001": {"A (GP)"}}) is None)

# ------------------------------------------------------------------ R-031 values
check("periods: 2026-Q2 / 2025 / 2025-FY / year fallback",
      pw.parse_period("2026-Q2") == (2026, 2) and pw.parse_period("2025") == (2025, None) and pw.parse_period("2025-FY") == (2025, None)
      and pw.parse_period("", "2024") == (2024, None) and pw.parse_period("", "Unknown") == (None, None))
check("Issued date = first TIMELY posted date; a bulk back-load (2019 notice posted in 2026) keeps Issued but no date",
      pw.timely(D(2026, 8, 15), 2026, 2) and not pw.timely(D(2026, 8, 7), 2019, None) and pw.timely(D(2026, 9, 1), 2025, None)
      and not pw.timely(None, 2025, None))
ps = [{"posting_id": "GPD-9", "portal": "gp", "posted_date": D(2026, 8, 7), "fiscal_year": 2019, "fiscal_quarter": None},
      {"posting_id": "LPD-12", "portal": "lp", "posted_date": D(2026, 8, 15), "fiscal_year": 2026, "fiscal_quarter": 2},
      {"posting_id": "LPD-2", "portal": "lp", "posted_date": D(2026, 9, 11), "fiscal_year": 2026, "fiscal_quarter": 2}]
check("Published To = both channels, the first posted date, posting IDs in order; Issued date from the timely postings only",
      pw.issued_values(ps) == (["gp_portal", "lp_portal"], D(2026, 8, 7), ["GPD-9", "LPD-2", "LPD-12"], D(2026, 8, 15)))
check("Portal kind conflict: both kinds known and different; a blank catalog kind is not a conflict (the kind is never changed)",
      pw.kind_conflict("correspondence", "k1") and not pw.kind_conflict("k1", "k1") and not pw.kind_conflict(None, "k1")
      and not pw.kind_conflict("k1", None)
      and not pw.kind_conflict("audited_financial_statements", "quarterly_report") and pw.kind_conflict("k1", "capital_statement"))

# ------------------------------------------------------------------ G-P4 dates as "YYYY-MM-DD"
sch = cl.Schema({"published": {"label_id": "L10", "title": "Published To", "fields": {
    "channel": {"field_id": "c", "type": "selectionOptions", "choices": {"lp_portal": "c1", "gp_portal": "c2", "datum": "c3", "email": "c4"}},
    "posted_date": {"field_id": "d", "type": "dateOptions"}, "posting_id": {"field_id": "t", "type": "textOptions"}}}})
m = ls.mods_for(["published_date", "published_ids", "published_channels"],
                {"published_date": "2026-08-15", "published_ids": ["LPD-12", "GPD-9"], "published_channels": ["gp_portal", "lp_portal"]}, sch)
fm = {x["fieldId"]: x for x in m[0]["fieldModifications"]}
check("G-P4 dates are sent as 'YYYY-MM-DD' strings; Posting ID as one text value; Channel as choice IDs",
      fm["d"] == {"fieldId": "d", "setDateValues": ["2026-08-15"]} and fm["t"]["setTextValues"] == ["GPD-9, LPD-12"]
      and fm["c"]["setSelectionValues"] == ["c2", "c1"], json.dumps(m))
check("L10 is person-owned like every catalog field (never overwritten) and is not read back into the catalog",
      {"published_channels", "published_date", "published_ids"} <= set(cl.PERSON_FIELDS)
      and not ({"published_channels", "published_date", "published_ids"} & set(ls.CONFIRM_COL)))
live = {"published_ids": ["LPD-99"], "review_status": None, "reviewed_by_set": False}
mach = {"published_ids": ["LPD-12"]}
check("a person's L10 edit (differs from the last machine write) is skipped by the re-sync",
      "published_ids" in ls.person_owned(live, mach, ["published_ids"]))

# ------------------------------------------------------------------ R-032 status rules
class C:  # a minimal cursor over the seed
    def __init__(self): self.r = []
    def execute(self, q, p=None):
        self.r = [(rid, json.dumps(spec), val, pri, True, note) for rid, val, pri, spec, note in pw.STATUS_RULES]
    def fetchall(self): return self.r
rules = pw.load_status_rules(C())
fr = lambda name, segs, fam, kind, ents=(), fy=None, k1=frozenset(): pw.first_rule(rules, name, segs, fam, kind, ents, fy, k1)
check("R-032 seed: every pattern compiles; first match wins in priority order (Issued < Final < Draft < Working)",
      len(rules) == len(pw.STATUS_RULES) and [r["priority"] for r in rules] == sorted(r["priority"] for r in rules))
check("Issued: a PDF in an 'Issued' / 'As Filed' folder; K-1 PDF in a K-1 folder for a year with portal K-1 postings",
      fr("Return 2024.pdf", ["Tax", "2024", "As Filed"], "pdf", "tax_return") == ("issued", "ST5-ISS-FOLDER")
      and fr("K-1 0001.pdf", ["Fund A", "2025 K-1s"], "pdf", "k1", ["FUND-A"], 2025, {("FUND-A", 2025)}) == ("issued", "ST5-ISS-K1PORTAL"))
check("Final rules never fire on a draft name or inside a drafts / working folder",
      fr("Q3 Report DRAFT.pdf", ["Reports", "Final"], "pdf", "quarterly_report")[0] == "draft"
      and fr("K-1.pdf", ["2025", "Drafts"], "pdf", "k1")[0] is None
      and fr("K-1.pdf", ["2025", "K-1s"], "pdf", "k1") == ("final", "ST5-FIN-K1PDF"))
check("Draft: vN without final, redline; Word report files; 'working' spreadsheets stay blank (rule recorded, no Status)",
      fr("Model v3.xlsx", [], "sheet", None) == ("draft", "ST5-DRF-NAME")
      and fr("Q2 Letter.docx", [], "doc", "quarterly_report") == ("draft", "ST5-DRF-WORDREPORT")
      and fr("Rec.xlsx", ["Workpapers"], "sheet", "workpaper") == (None, "ST5-WORKING"))
class CV(C):
    def execute(self, q, p=None):
        self.r = [(rid, json.dumps(spec), val, pri, rid != "ST5-FIN-BANKPDF", note) for rid, val, pri, spec, note in pw.STATUS_RULES]
vr = pw.load_status_rules(CV())
check("a vetoed rule (active = false) is not loaded, so it never applies; the measure still sees it (include_vetoed)",
      "ST5-FIN-BANKPDF" not in {r["rule_id"] for r in vr} and pw.first_rule(vr, "Stmt.pdf", [], "pdf", "bank_stmt") == (None, None)
      and "ST5-FIN-BANKPDF" in {r["rule_id"] for r in pw.load_status_rules(CV(), include_vetoed=True)})

# ------------------------------------------------------------------ G-M1 memory: streamed batches of 2,000
check("G-M1 memory stays streamed: document reads and writes go in batches of 2,000", pw.BATCH == 2000
      and "ids[i:i + BATCH]" in inspect.getsource(pw.apply_issued) and "upd[i:i + BATCH]" in inspect.getsource(pw.apply_issued))

print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
