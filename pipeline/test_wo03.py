"""CAT-WO-03 pipeline guard tests (offline; synthetic names only).   py pipeline\\test_wo03.py"""
import datetime, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject_wo03 as sw
import requirements_wo03 as rq
import catalog_labels as cl
import roster_load_wo03 as rl
import applicability_load_wo03 as al
import labels_setup_wo03 as ls3

R = []


def check(name, cond, detail=""):
    R.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + (f"  ({detail})" if detail and not cond else ""))


# ---------------------------------------------------------------- roster / applicability loaders
check("G-W1a roster check refuses TIN / address / bank / amount columns",
      rl.forbidden_columns(["company_code", "tax_id", "mailing_address", "bank_account", "commitment_amount", "display_name"])
      == ["tax_id", "mailing_address", "bank_account", "commitment_amount"])
check("G-W1b roster check passes the expected columns", rl.forbidden_columns(rl.ROSTER_COLS) == [] and rl.forbidden_columns(rl.SUBTYPE_COLS) == [])
rows, sk = al.parse_rows([{"entity_code": "ASOF", "subtype_code": "AUD-01", "Required": "Yes", "note": None},
                          {"entity_code": "TM", "subtype_code": "AUD-01", "Required": "No", "note": "x"},
                          {"entity_code": "IVY", "subtype_code": "OFF-05", "Required": "Unknown", "note": None},
                          {"entity_code": "X", "subtype_code": "OFF-05", "Required": None, "note": None}])
check("G-W2 applicability: Yes/No loaded, Unknown / blank NOT loaded (reads 'applicability not set', never Missing)",
      [(e, s, r) for e, s, r, _ in rows] == [("ASOF", "AUD-01", True), ("TM", "AUD-01", False)] and sk == {"unknown": 1, "blank": 1})

# ---------------------------------------------------------------- subject matching (synthetic names)
party = [("FUND-A", "LP-0001", False), ("FUND-A", "LP-0002", False), ("FUND-A", "LP-0003", False), ("FUND-A", "LP-0090", True),
         ("FUND-B", "LP-0004", False)]
alias = [("LP-0001", "Zephyrine Quillfeather Family Trust"), ("LP-0002", "Brontide Holdings LLC"), ("LP-0002", "Brontide Ventures"),
         ("LP-0003", "Allegis Capital, LLC"), ("LP-0090", "Fund A GP, LLC"), ("LP-0004", "Marrowind Partners LP")]
idx = sw.RosterIndex(party, alias)
check("G-S1 one partner's full name in the FILE name -> high",
      sw.match_doc(idx, {"FUND-A"}, ["2025 K-1 Zephyrine Quillfeather.pdf"], ["Taxes", "2025"]) == ("high", [("LP-0001", "FUND-A", "name")]))
check("G-S2 two partners' full names -> low (Match subject lane), never a guess",
      sw.match_doc(idx, {"FUND-A"}, ["Zephyrine Quillfeather and Brontide Holdings side letter.pdf"], [])[0] == "low")
check("G-S3 a distinctive word of a two-word name only -> low (a 7+-letter one-word name is a full name: high)",
      sw.match_doc(idx, {"FUND-A"}, ["Zephyrine sub docs.pdf"], [])[0] == "low"
      and sw.match_doc(idx, {"FUND-A"}, ["Brontide sub docs.pdf"], [])[0] == "high")
check("G-S4 another entity's partner is never matched (roster of the document's entities only)",
      sw.match_doc(idx, {"FUND-A"}, ["Marrowind Partners K-1.pdf"], [])[0] in ("none",))
check("G-S5 no roster for the entity -> no_roster", sw.match_doc(idx, {"FUND-Z"}, ["x.pdf"], []) == ("no_roster", []))
check("G-S6 a manager named 'Allegis Capital, LLC' does not match every Allegis folder",
      sw.match_doc(idx, {"FUND-A"}, ["Q3 report.pdf"], ["Allegis Capital", "Fund A"])[0] == "none")
check("G-S7 the fund's own GP row: full GP name in the FILE name -> high; in a FOLDER name -> not matched",
      sw.match_doc(idx, {"FUND-A"}, ["Fund A GP LLC subscription.pdf"], [])[1] == [("LP-0090", "FUND-A", "name")]
      and sw.match_doc(idx, {"FUND-A"}, ["k1 2025.pdf"], ["Fund A GP"])[0] == "none")
check("G-S8 folder match only when no file-name match and exactly one partner",
      sw.match_doc(idx, {"FUND-A"}, ["k1 2025.pdf"], ["Zephyrine Quillfeather"]) == ("high", [("LP-0001", "FUND-A", "folder")]))
check("G-S9 personnel markers (offer letter / employment agreement / severance) and not a K-1",
      sw.personnel(["Offer Letter - signed.pdf"]) and sw.personnel(["Employment Agreement v2.docx"]) and not sw.personnel(["2025 K-1.pdf"]))
check("G-S10 staff match needs exactly one full staff name",
      sw.staff_match([("a.b@allegiscapital.com", ["Alba Brightwater"]), ("c@allegiscapital.com", ["Cass Dunmore"])], ["Offer letter Alba Brightwater.pdf"])
      == "a.b@allegiscapital.com"
      and sw.staff_match([("a.b@allegiscapital.com", ["Alba Brightwater"])], ["Offer letter Alba.pdf"]) is None)

# ---------------------------------------------------------------- Subject code(s) is codes only (R-026)
codes, dropped = cl.codes_from_text("LP-0001, Zephyrine Quillfeather, gpm-01;GM-0003")
check("G-T1 Subject code(s) read back: only roster codes are kept, a typed name is dropped and counted",
      codes == ["GM-0003", "GPM-01", "LP-0001"] and dropped == 2)


class FakeSchema:
    def __init__(self, S): self.S = S
    def has(self, f):
        lk, fk, _ = cl.FIELDS[f]
        return lk in self.S and fk in self.S[lk]["fields"]


S = {"parties": {"label_id": "P", "fields": {"subject_codes": {"field_id": "sc", "type": "textOptions"},
                                              "subject_person": {"field_id": "sp", "type": "userOptions"}}},
     "handling": {"label_id": "H", "fields": {"tier": {"field_id": "t", "choices": {"normal": "n", "restricted": "r", "secret": "s"}},
                                               "contains": {"field_id": "c", "choices": {"lp_pii": "l", "personnel": "p"}}}}}
e = cl.expected({"subject_codes": ["LP-0001", "Zephyrine Quillfeather"], "subject_person": "Some Name"}, FakeSchema(S))
check("G-T2 no typed name ever reaches Subject code(s) / Subject (person) (the machine writes codes and staff accounts only)",
      e["subject_codes"] == ["LP-0001"] and e["subject_person"] is None)
import label_sync_wo02 as ls2
mods = ls2.mods_for(["subject_codes"], {"subject_codes": ["LP-0002", "LP-0001"]}, FakeSchema(S))
check("G-T3 Subject code(s) is written as one text value of codes",
      mods == [{"labelId": "P", "fieldModifications": [{"fieldId": "sc", "setTextValues": ["LP-0001, LP-0002"]}]}])
fs = FakeSchema(S)
check("G-T4 personnel: Handling is RAISED to Restricted + Personnel info",
      cl.handling_raise({"_personnel": True}, {"tier": "normal", "contains": ["lp_pii"]}, fs) == {"tier": "restricted", "contains": ["lp_pii", "personnel"]})
check("G-T5 personnel: never lowers secret / restricted, never removes a Contains choice",
      cl.handling_raise({"_personnel": True}, {"tier": "secret", "contains": ["personnel"]}, fs) == {}
      and cl.handling_raise({"_personnel": True}, {"tier": "restricted", "contains": []}, fs) == {"contains": ["personnel"]})
check("G-T6 not personnel, or Personnel info not published: Handling untouched",
      cl.handling_raise({"_personnel": False}, {"tier": "normal"}, fs) == {}
      and cl.handling_raise({"_personnel": True}, {"tier": "normal"}, FakeSchema({"handling": {"label_id": "H", "fields": {"contains": {"field_id": "c", "choices": {"lp_pii": "l"}}}}})) == {})
hm = ls2.handling_mods({"tier": "restricted", "contains": ["personnel"]}, fs)
check("G-T7 handling mods write only tier=restricted and the Contains list", json.dumps(hm) == json.dumps(
    [{"labelId": "H", "fieldModifications": [{"fieldId": "t", "setSelectionValues": ["r"]}, {"fieldId": "c", "setSelectionValues": ["p"]}]}]))

# ---------------------------------------------------------------- requirements
d = datetime.date(2026, 11, 18)
check("G-R1 periods: last complete FY / quarter (FY2025; quarters 2025Q1..2026Q3)",
      rq.periods("entity_partner_fy", 2025, d) == [(2025, None)] and rq.periods("entity_partner_quarter", 2025, d)[-1] == (2026, 3)
      and len(rq.periods("entity_partner_quarter", 2025, d)) == 7 and rq.periods("entity_fy", 2022, d) == [(y, None) for y in (2022, 2023, 2024, 2025)])


def cand(doc, **k):
    base = {"document_id": doc, "file_id": f"f{doc:010d}", "kind": "subscription_agreement", "stage": "fully_executed", "status": None,
            "is_primary": True, "partner_conf": "high", "date_ord": 700000, "kind_satisfying": True}
    base.update(k)
    return base


SW = {"stage": ["fully_executed"]}
r, sub, best, ranked, _ = rq.evaluate([cand(1, stage="draft", date_ord=800000), cand(2)], SW)
check("G-R2 satisfying beats newer non-satisfying", r == "met" and best["document_id"] == 2)
r, sub, best, *_ = rq.evaluate([cand(1, partner_conf="high", date_ord=900000), cand(2, partner_conf="confirmed")], SW)
check("G-R3 person-confirmed beats machine; then newest", best["document_id"] == 2)
r, sub, best, *_ = rq.evaluate([cand(1, stage="partially_executed")], SW)
check("G-R4 on file, not final, with the sub-status", (r, sub) == ("on_file", "partially_executed"))
r, sub, *_ = rq.evaluate([], {"stage": ["fully_executed"]}, no_candidate_result="none_found")
check("G-R5 side letters with no candidate read 'none found', never Missing", r == "none_found")
r, sub, best, *_ = rq.evaluate([cand(1, partner_conf="low")], SW)
check("G-R6 a low partner match never makes Met", (r, sub) == ("on_file", "partner_unconfirmed"))
r, sub, best, *_ = rq.evaluate([cand(1, kind="audit_report", kind_satisfying=False, status="final"), cand(2, kind="financial_statements", status=None)],
                               {"status": ["final", "issued"]})
check("G-R7 a satisfying kind outranks a candidate-only kind (FS over the audit opinion alone)", best["document_id"] == 2 and sub == "unknown")
ov = {"action": "not_required", "override_id": 7}
check("G-R8 override Not required wins over a Met candidate", rq.evaluate([cand(1)], SW, ov)[0] == "not_required")
ov = {"action": "link", "override_id": 8, "file_id": "fLINKED00001", "document_id": 9}
res = rq.evaluate([cand(1, stage="draft")], SW, ov)
check("G-R9 override Link: met with the linked file, source person", res[0] == "met" and res[2]["file_id"] == "fLINKED00001" and res[2]["source"] == "person")

# ---------------------------------------------------------------- labels plan (offline)
schema = json.load(open(ls3.SCHEMA_PATH, encoding="utf-8"))
p = ls3.plan(schema, list(schema["doc"]["fields"]["entity"]["choices"]) + ["NEW-1"])
check("G-L1 label plan: new entity choices, Subject fields, Personnel info, within limits",
      p["new_entities"] == ["NEW-1"] and p["add_personnel"] and set(p["add_subject_fields"]) <= {"subject_codes", "subject_person"} and not p["problems"])
p = ls3.plan(schema, [f"E{i}" for i in range(300)])
check("G-L2 label plan refuses more than 200 choices", any("choices > 200" in x for x in p["problems"]))

print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
