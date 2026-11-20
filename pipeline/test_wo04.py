"""CAT-WO-04 · version families: grouping, current-picking, R-028, person-set rows, names. Offline (no DB, no Drive).
Invented names only. The DB guards (person-set current survives two nightly runs, families never mix entities /
subjects in the catalog, no file name in a label) are in db/tests/test_wo04_guards.py; the modifiedTime pilot is
scripts/pilot_wo04_mtime.py."""
import collections, datetime, io, os, sys, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import versions_wo04 as vw
import families_wo04 as fw
import catalog_labels as cl
import requirements_wo03 as rq

R = []
def check(name, cond, detail=""):
    R.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + (f"  -- {detail}" if detail and not cond else ""))

D = datetime.date
T = lambda y, m, d: datetime.datetime(y, m, d, tzinfo=datetime.timezone.utc)
_n = iter(range(1000, 100000))
def doc(name, kind="lpa", ents=("FUND-A",), stage=None, status=None, eff=None, mod=T(2024, 1, 1), fy=None, period=None,
        subj=(), person=None, shared=True):
    return dict(document_id=next(_n), name=name, kind=kind, entities=list(ents), subject_codes=list(subj), subject_person=None,
                fy=fy, period=period, effective_date=eff, modified_time=mod, stage=stage, status=status, shared=shared,
                status_person=False, person=person)

def plan(ms, person=None):
    return fw.plan(ms, vw.Tokens(), person or {}, {})

def role_of(rows, m): return rows[m["document_id"]]["role"]

# ------------------------------------------------------------------ stems and tokens
t = vw.Tokens()
check("G-S1 version tokens strip to one stem (v3, draft, initials, a save date, executed, (1), copy of, extension)",
      len({t.stem(n)[0] for n in ["Side Letter v3 [JS comments] 2024-06-15.docx", "Side Letter - DRAFT.docx",
                                  "Side Letter (executed).pdf", "Copy of Side Letter (1).pdf", "Side Letter_FINAL.pdf"]}) == 1)
check("G-S2 a month-end date in a name is the PERIOD, not a version: two month ends never share a stem",
      t.stem("Bank Rec 01.31.2024.xlsx")[0] != t.stem("Bank Rec 02.29.2024.xlsx")[0]
      and t.stem("Memo 03.04.2024.docx")[0] == t.stem("Memo 03.11.2024.docx")[0])

# ------------------------------------------------------------------ item 6 guards
# 1. an executed document is never superseded by a draft
a = doc("Side Letter executed.pdf", kind="side_letter", stage="fully_executed", eff=D(2023, 1, 1), mod=T(2023, 1, 2))
b = doc("Side Letter v4 draft.docx", kind="side_letter", stage="draft", eff=D(2024, 6, 1), mod=T(2024, 6, 1))
c = doc("Side Letter v5.docx", kind="side_letter", stage="final_unexecuted", eff=D(2024, 7, 1), mod=T(2024, 7, 1))
fams, rows, _ = plan([a, b, c])
check("G-V1 an executed document is never superseded by a draft or unsigned version, whatever the dates say",
      role_of(rows, a) == "current" and role_of(rows, b) == "draft_of" and role_of(rows, c) == "superseded"
      and rows[b["document_id"]]["supersedes"] == a["document_id"])
# a person marked the draft current: still, the executed one is never superseded by it
pa = doc("Side Letter executed.pdf", kind="side_letter", stage="fully_executed")
pb = doc("Side Letter v4 draft.docx", kind="side_letter", stage="draft", person=dict(family=7, role="current", current=True, supersedes=None, amends=None))
cur, roles = vw.pick([pa, pb])
check("G-V1b even with a person's current on a draft, the executed member is never made Superseded",
      roles[pa["document_id"]][0] == "current" and cur is pb)

# 2. an amendment is never treated as a supersession (R-028); an A&R supersedes the base before it
base = doc("Limited Partnership Agreement executed.pdf", stage="fully_executed", eff=D(2015, 1, 1))
am1 = doc("First Amendment to LPA executed.pdf", kind="lpa_amendment", stage="fully_executed", eff=D(2017, 1, 1))
am1d = doc("First Amendment to LPA draft.docx", kind="lpa_amendment", stage="draft", eff=D(2016, 12, 1))
fams, rows, st = plan([base, am1, am1d])
check("G-V2 an amendment is never a supersession (R-028): Role = Amends -> base; the base stays Current",
      role_of(rows, am1) == "amends" and rows[am1["document_id"]]["amends"] == base["document_id"]
      and role_of(rows, base) == "current" and rows[am1["document_id"]]["supersedes"] is None
      and role_of(rows, am1d) == "draft_of" and rows[am1d["document_id"]]["supersedes"] == am1["document_id"],
      str([rows.get(k["document_id"], {}).get("role") for k in (base, am1, am1d)]))
ar = doc("Amended and Restated Limited Partnership Agreement executed.pdf", stage="fully_executed", eff=D(2020, 1, 1))
fams, rows, st = plan([base, am1, ar])
check("G-V2b an A&R supersedes the prior base and carries its amendments (they are superseded by the A&R, Amends kept)",
      role_of(rows, base) == "superseded" and rows[base["document_id"]]["supersedes"] == ar["document_id"]
      and role_of(rows, ar) == "current" and role_of(rows, am1) == "superseded"
      and rows[am1["document_id"]]["supersedes"] == ar["document_id"] and rows[am1["document_id"]]["amends"] == base["document_id"],
      str([(rows[k["document_id"]]["role"], rows[k["document_id"]]["supersedes"]) for k in (base, am1, ar)]))

# 3. a person-set current survives the nightly (plan is the nightly's computation; twice, with a newer version arriving)
x1 = doc("Report v1.pdf", kind="quarterly_report", fy=2024, period="q2", status="final", mod=T(2024, 7, 1))
x2 = doc("Report v2.pdf", kind="quarterly_report", fy=2024, period="q2", status="final", mod=T(2024, 8, 1))
person = {x1["document_id"]: dict(family=42, role="current", current=True, supersedes=None, amends=None),
          x2["document_id"]: dict(family=42, role="superseded", current=False, supersedes=x1["document_id"], amends=None)}
x3 = doc("Report v3.pdf", kind="quarterly_report", fy=2024, period="q2", status="final", mod=T(2024, 9, 1))
ok = True
for night in (1, 2):
    for m in (x1, x2, x3): m["person"] = None
    fams, rows, _ = plan([x1, x2, x3], person)
    ok &= role_of(rows, x1) == "current" and role_of(rows, x2) == "superseded" and rows[x1["document_id"]]["method"] == "person"
    ok &= fams[rows[x3["document_id"]]["fam"]]["fid"] == 42 and role_of(rows, x3) == "superseded" and rows[x3["document_id"]]["method"] == "rule"
check("G-V3 a person-set current survives two nightly runs; a newer version joins the person's family, not as current", ok)
removed = {x1["document_id"]: dict(family=None, role=None, current=False, supersedes=None, amends=None)}
for m in (x1, x2, x3): m["person"] = None
fams, rows, _ = plan([x1, x2, x3], removed)
check("G-V3b a document a person took out of its family is never grouped again", x1["document_id"] not in rows)

# 4. families never mix entities or subjects unless a person merged them
ms = [doc("Capital Statement Q2.pdf", kind="capital_statement", ents=("FUND-A",), fy=2024, period="q2", subj=("LP-0001",)),
      doc("Capital Statement Q2 v2.pdf", kind="capital_statement", ents=("FUND-A",), fy=2024, period="q2", subj=("LP-0002",)),
      doc("Capital Statement Q2 final.pdf", kind="capital_statement", ents=("FUND-B",), fy=2024, period="q2", subj=("LP-0001",)),
      doc("Capital Statement Q2 draft.pdf", kind="capital_statement", ents=("FUND-A",), fy=2024, period="q2", subj=("LP-0001",))]
fams, rows, _ = plan(ms)
mixed = [f for f in fams if f["confidence"] != "person" and (len({tuple(sorted(m["entities"])) for m in f["members"]}) > 1
         or len({vw.subj(m) for m in f["members"] if vw.subj(m)}) > 1)]
check("G-V4 families never mix entities or subjects unless a person merged them",
      not mixed and rows.get(ms[0]["document_id"], {}).get("fam") == rows.get(ms[3]["document_id"], {}).get("fam") is not None
      and ms[1]["document_id"] not in rows and ms[2]["document_id"] not in rows)
check("G-V4b excluded kinds never form families (bank statements, invoices, notices, wires, receipts)",
      not plan([doc("Invoice 123.pdf", kind="invoice"), doc("Invoice 123 v2.pdf", kind="invoice")])[0])
k1a = doc("K-1 2023.pdf", kind="k1", fy=2023, subj=("LP-0001",)); k1b = doc("K-1 2023 copy.pdf", kind="k1", fy=2023, subj=("LP-0001",))
k1c = doc("K-1 2023 corrected.pdf", kind="k1", fy=2023, subj=("LP-0002",)); k1d = doc("K-1 2023.pdf", kind="k1", fy=2023, subj=("LP-0002",))
f4 = plan([k1a, k1b, k1c, k1d])[1]
check("G-V4c K-1s join a family only through an amended / corrected K-1 for the same partner and year",
      k1a["document_id"] not in f4 and k1c["document_id"] in f4 and f4[k1c["document_id"]]["fam"] == f4[k1d["document_id"]]["fam"])

# 5. no file name in any log or label
secret = "Zyxwv Pension Trust"
ms = [doc(f"{secret} Side Letter v1.docx", kind="side_letter", stage="draft"), doc(f"{secret} Side Letter executed.pdf", kind="side_letter", stage="fully_executed")]
buf = io.StringIO()
class FakeConn:
    def cursor(self, name=None): raise RuntimeError("no db")
fams, rows, stats = plan(ms)
with contextlib.redirect_stdout(buf):
    live = [f for f in fams if not f.get("drop")]
    print(f"families {len(live)}"); [print(k, v) for k, v in stats.items()]
e = cl.expected({"version_family": 12, "version_role": "superseded", "version_supersedes": ms[1]["document_id"], "version_amends": None},
                cl.Schema({"version": {"label_id": "L6", "title": "Version", "fields": {"family": {"field_id": "f1", "type": "textOptions"},
                          "role": {"field_id": "f2", "type": "selectionOptions", "choices": {r: f"c{i}" for i, r in enumerate(vw.ROLES)}},
                          "supersedes": {"field_id": "f3", "type": "textOptions"}, "amends": {"field_id": "f4", "type": "textOptions"}}}}))
l6 = [e[k] for k in ("version_family", "version_role", "version_supersedes", "version_amends")]
dec = cl.Schema({"version": {"label_id": "L6", "title": "Version", "fields": {"family": {"field_id": "f1", "type": "textOptions"}}}}).decode(
    {"labels": [{"id": "L6", "fields": {"f1": {"text": [secret]}}}]})
check("G-V5 no file name in any log or label: the build logs counts only; L6 holds catalog numbers and role codes; "
      "text that is not a catalog number is never read back",
      secret.lower() not in buf.getvalue().lower() and all(v is None or cl.CATALOG_ID.match(v) or v in vw.ROLES for v in l6)
      and dec["version_family"] is None)

# ------------------------------------------------------------------ checklists (item 4)
sw = {"stage": ["fully_executed"]}
cur_c = {"document_id": 1, "file_id": "f1", "kind": "side_letter", "stage": "final_unexecuted", "status": None, "partner_conf": "high",
         "is_primary": True, "date_ord": 1, "kind_satisfying": True, "version_role": "current"}
old_c = {"document_id": 2, "file_id": "f2", "kind": "side_letter", "stage": "fully_executed", "status": None, "partner_conf": "high",
         "is_primary": True, "date_ord": 2, "kind_satisfying": True, "version_role": "superseded", "supersedes": 1}
res = rq.evaluate([dict(cur_c), dict(old_c)], sw)
only = rq.evaluate([dict(old_c)], sw)
check("G-C1 checklists take the best document from current members first; a superseded member only when it is the only "
      "candidate, read 'On file, not final: superseded by ...'",
      res[2]["document_id"] == 1 and len(res[3]) == 1 and only[0] == "on_file" and only[1] == "superseded"
      and "superseded by catalog ID 1" in rq.reason(only[2], only[0], only[1]))

print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
