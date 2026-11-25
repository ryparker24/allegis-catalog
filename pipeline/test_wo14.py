"""CAT-WO-14 · Partner Portal / LP Portal copies. Offline (no DB, no Drive). Invented names, codes and numbers only."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf as fitz
import pages_wo06 as pw
import portal_wo14 as pt
import label_sync_wo02 as ls

R = []
def check(name, cond, detail=""):
    R.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + (f"  -- {detail}" if detail and not cond else ""))

# ------------------------------------------------------------------ R-059 status plan
docs = [(1, "capital_statement", None, None), (2, "k1", "final", None), (3, "capital_statement", "superseded", None),
        (4, "k1", "draft", "draft"), (5, "subscription_agreement", None, None), (6, "capital_call_notice", "issued", None)]
check("W14-1 option A: Issued for portal documents (not a person's status, not superseded, not executable kinds, not already Issued)",
      pt.status_plan(docs, "A", {"subscription_agreement"}) == [1, 2])
check("W14-2 option B: nothing set Issued", pt.status_plan(docs, "B", {"subscription_agreement"}) == [])

# ------------------------------------------------------------------ label scope SQL
class FakeCur:
    def __init__(self, has): self.has = has
    def execute(self, *a): pass
    def fetchone(self): return (self.has,)
sql = "SELECT f.file_id FROM cat.file f WHERE f.drive_name = ANY(%s) AND f.removed_run IS NULL"
check("W14-3 label scope: with migration 014 the approved drives OR an ops.label_scope subtree",
      "ops.in_label_scope(f.drive_name, f.folder_path)" in ls.scope_sql(FakeCur(True), sql) and "%s" in ls.scope_sql(FakeCur(True), sql))
check("W14-4 label scope: before migration 014 the approved drives only (unchanged)", ls.scope_sql(FakeCur(False), sql) == sql)

# ------------------------------------------------------------------ capital call notice reading
ALIASES = [("LP-0101", "Quillon Harrowgate Family Trust"), ("LP-0102", "Ostrava Pemberly Holdings LLC"), ("LP-0202", "Zebulon Krateros Partners")]
PARTY = [("TESTF", "LP-0101", False), ("TESTF", "LP-0102", False), ("OTHERF", "LP-0202", False)]
NAMES = pw.NameIndex(ALIASES, PARTY)
EIDX = pw.EntityIndex([("Invented Ventures Fund IV LP", "TESTF")])
RULES = pw.load_rules(None)


def notice(lines):
    doc = fitz.open(); p = doc.new_page(width=612, height=792)
    y = 50
    for ln in lines:
        p.insert_text((40, y), ln, fontsize=10); y += 16
    b = doc.tobytes(); doc.close()
    return b


def read(lines, roster=("TESTF",)):
    return pw.read_document(notice(lines), "capital_call_notice", NAMES, EIDX, RULES, set(roster), None)


r = read(["Invented Ventures Fund IV LP", "Capital Call Notice", "Limited Partner: Quillon Harrowgate Family Trust", "Amount due 1,000"])
st, cl = r["statements"][0]
check("W14-5 notice label 'Limited Partner:' -> the roster partner, HIGH", cl == [("LP-0101", "TESTF", "high", None)], str(cl))
check("W14-6 notice: the fund's name -> entity code", st.entity == "TESTF")
r = read(["Invented Ventures Fund IV LP", "Dear Ostrava Pemberly Holdings LLC:", "Capital is called."])
check("W14-7 notice 'Dear ...' line -> partner, HIGH", r["statements"][0][1] == [("LP-0102", "TESTF", "high", None)], str(r["statements"][0][1]))
r = read(["Invented Ventures Fund IV LP", "Quillon Harrowgate Family Trust", "1 Invented Way", "Capital is called."])
check("W14-8 notice: a roster name in the address block only -> MEDIUM (lane)", r["statements"][0][1] == [("LP-0101", "TESTF", "medium", None)], str(r["statements"][0][1]))
r = read(["Invented Ventures Fund IV LP", "Investor: Zebulon Krateros Partners"])
check("W14-9 notice: a partner of another fund's roster -> LOW NOT_IN_FUND", r["statements"][0][1] == [("LP-0202", None, "low", "NOT_IN_FUND")], str(r["statements"][0][1]))
check("W14-10 capital call notices are a read kind", "capital_call_notice" in pw.KINDS and "capital_call_notice" in pw.EXTRACT)
print(f"\n{sum(R)}/{len(R)} passed")
