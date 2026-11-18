r"""
CAT-WO-02 item 7 / 8 guard tests for the read-back + re-sync rules (pure functions; no Drive, no DB).
  py pipeline\test_label_sync_wo02.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_labels as cl
import label_sync_wo02 as ls
import derive_wo02 as dw

schema = cl.Schema(cl.load_schema())
FIELDS = schema.active_fields()
results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def row(**k):
    base = dict(kind="invoice", entities=["MTV-II"], portcos=[], fiscal_year=2024, fq=None, fye=True, eff=None, workstream="vendors_ap",
                issuer=None, req_exec=False, stage=None, signed=None, handling="normal", pii_lp=False, document_id=1)
    base.update(k)
    return base


def live_from(expected, **over):
    d = {f: expected.get(f) for f in cl.FIELDS}
    d.update(review_status="needs_review", reviewed_by_set=False, has_doc_label=True)
    d.update(over)
    return d


# ---- the catalog changed (kind invoice -> receipt); nobody touched the file -> the re-sync writes it
machine = cl.expected(row(), schema)
now = cl.expected(row(kind="receipt"), schema)
w, s = ls.plan_resync(now, live_from(machine), machine, [], FIELDS)
check("G-S0 control: a machine value the catalog changed IS re-synced", w == ["kind"] and s == [], f"write={w} skip={s}")

# ---- test_edited_value_not_overwritten_by_resync: a person changed fiscal_year in Drive (or in the app)
live = live_from(machine, fiscal_year=2023)
w, s = ls.plan_resync(cl.expected(row(fiscal_year=2025), schema), live, machine, [], FIELDS)
check("G-E4 test_edited_value_not_overwritten_by_resync: a value edited in Drive/app is skipped and counted", "fiscal_year" not in w and s == ["fiscal_year"], f"write={w} skip={s}")

# ---- the same file, but the catalog ALSO changed kind: kind is re-synced, fiscal_year still skipped
w, s = ls.plan_resync(cl.expected(row(kind="receipt", fiscal_year=2025), schema), live, machine, [], FIELDS)
check("G-E4b only the person's field is protected; other changed fields still re-sync", w == ["kind"] and s == ["fiscal_year"], f"write={w} skip={s}")

# ---- Catalog Review = Confirmed (the app's edit sets it): every field with a value is the person's
live = live_from(machine, review_status="confirmed", reviewed_by_set=True)
w, s = ls.plan_resync(cl.expected(row(kind="receipt", entities=["MTV-I"]), schema), live, machine, [], FIELDS)
check("G-E4c a Confirmed file is never overwritten (all its valued fields are person-owned)", w == [] and sorted(s) == ["entities", "kind"], f"write={w} skip={s}")

# ---- ownership is sticky: once person-owned (stored), it stays protected even if live now equals machine again
w, s = ls.plan_resync(cl.expected(row(kind="receipt"), schema), live_from(machine), machine, ["kind"], FIELDS)
check("G-E4d stored person ownership persists across runs", w == [] and s == ["kind"], f"write={w} skip={s}")

# ---- a person CLEARED a value (app 'blank' / Drive): owned, so the re-sync doesn't put the machine value back
live = live_from(machine, entities=[], review_status="confirmed", reviewed_by_set=True)
w, s = ls.plan_resync(machine, live, machine, [], FIELDS)
check("G-E4e a value a person cleared is not re-filled by the re-sync", "entities" not in w and "entities" in s, f"write={w} skip={s}")
live = live_from(machine, entities=[])          # cleared in Drive, no review mark
w, s = ls.plan_resync(machine, live, machine, [], FIELDS)
check("G-E4f ... also when cleared directly in Drive (no review mark)", w == [] and s == ["entities"], f"write={w} skip={s}")

# ---- Catalog Review = Wrong protects the file's values too (the person said the catalog is wrong)
live = live_from(machine, review_status="wrong", reviewed_by_set=True)
w, s = ls.plan_resync(cl.expected(row(kind="receipt"), schema), live, machine, [], FIELDS)
check("G-E4g a file marked Wrong is not re-synced over", w == [] and s == ["kind"], f"write={w} skip={s}")

# ---- first sight: machine seeded from the LIVE labels, so a catalog value that changed since the bulk write is
#      NOT taken as a person's edit (it is simply re-synced)
seed = {f: live_from(machine)[f] for f in FIELDS}
check("G-R5 first read-back: a stale catalog value is not 'person-owned'", ls.person_owned(live_from(machine), seed, FIELDS) == [])
w, s = ls.plan_resync(cl.expected(row(kind="receipt"), schema), live_from(machine), seed, [], FIELDS)
check("G-R6 ... and the re-sync updates it", w == ["kind"] and s == [], f"write={w} skip={s}")

# ---- Handling is never in a re-sync write
mods = ls.mods_for(["kind", "tier", "contains"], now, schema)
ids = {m["labelId"] for m in mods}
check("G-S1 re-sync modifications never touch Handling or Catalog Review", schema.label_ids["handling"] not in ids and schema.label_ids["review"] not in ids and len(mods) == 1, str(sorted(ids)))

# ---- read-back: person_owned()
check("G-R1 read-back: unchanged file has no person fields", ls.person_owned(live_from(machine), machine, FIELDS) == [])
check("G-R2 read-back: a differing value is the person's", ls.person_owned(live_from(machine, kind="receipt"), machine, FIELDS) == ["kind"])
check("G-R3 read-back: Handling is never 'person-owned' (never stored as confirmed)", "tier" not in ls.person_owned(live_from(machine, tier="restricted"), machine, FIELDS))
u = ls.confirm_updates(42, ["kind", "period", "entities"], live_from(machine, kind="receipt", period="q3", entities=["MTV-I"]))
check("G-R4 read-back: person values go to *_confirmed columns (period -> quarter / FYE)",
      [x[0].split(" SET ")[1].split("=")[0] for x in u] == ["kind_confirmed", "fiscal_quarter_confirmed", "entities_confirmed"] and u[1][1] == (3, 42), str(u))

# ---- derivation rules (letter boundaries)
check("G-D1 status: 'Report_FINAL' -> final; 'draft final' -> conflict (blank)",
      dw.status_for("quarterly_report", False, "Q3 Report_FINAL", []) == ("final", "ST-final") and dw.status_for("x", False, "Draft final", [])[0] is None)
check("G-D2 status: executable kinds only get Final when fully executed", dw.status_for("lpa", True, "LPA draft", [], "draft") == (None, None) and dw.status_for("lpa", True, "x", [], "fully_executed")[0] == "final")
codes = {"MTV-III", "MTV-III (GP)", "MTV-IV (GP)", "MTV-IV (A)"}
types = {"MTV-III": "fund", "MTV-III (GP)": "gp", "MTV-IV (GP)": "gp", "MTV-IV (A)": "fund"}
check("G-D3 K-1: GP folder -> receiving GP, issuing its fund", dw.k1_parties(["taxes", "gp entities", "x"], ["MTV-III (GP)"], types, 1, codes) == ("MTV-III", ["MTV-III (GP)"], "K1-R2-gp-received"))
check("G-D4 K-1: ambiguous GP fund stays blank (never guessed)", dw.k1_parties(["taxes", "gp entities"], ["MTV-IV (GP)"], types, 1, codes)[0] is None)
check("G-D5 K-1: K-1 folder with many K-1s and one fund -> issued to LP", dw.k1_parties(["taxes", "2024", "k-1s"], ["MTV-III"], types, 12, codes) == ("MTV-III", ["LP"], "K1-R3-issued-to-lps"))
check("G-D6 K-1: unknown stays blank", dw.k1_parties(["misc"], [], types, 1, codes) == (None, [], None))
check("G-D7 no-kind rules apply only when ruled (empty ruling -> nothing)", dw.nokind_rule("Invoice_123", [], only=set()) == (None, None) and dw.nokind_rule("Invoice_123", [], only={"NK02"})[1] == "invoice")
R = dw.NOKIND_RULED
check("G-D8 K1N: 'K-1' / 'Schedule K1' in the name -> k1; 'K-1065' is not a K-1",
      dw.nokind_rule("2023 Schedule K1 - x", [], only=R)[0] == "K1N" and dw.nokind_rule("NJ K-1065 2023", [], only=R) == (None, None))
check("G-D9 K1F: a pdf in a K-1 folder -> k1; a spreadsheet / archive there is skipped",
      dw.nokind_rule("scan_0012", ["taxes", "2023 k-1s"], only=R, family="pdf") == ("K1F", "k1")
      and dw.nokind_rule("allocation", ["taxes", "2023 k-1s"], only=R, family="sheet") == (None, None)
      and dw.nokind_rule("bundle", ["taxes", "k-1s"], only=R, family="archive") == (None, None))
check("G-D10 NK01 is gone (replaced by K1N / K1F); NK12 matches a Workpapers folder",
      "NK01" not in {r[0] for r in dw.NOKIND_RULES} and dw.nokind_rule("tb", ["2023 workpapers"], only={"NK12"})[1] == "workpaper")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
