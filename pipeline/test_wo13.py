"""CAT-WO-13 · PCAP cadence per fund (R-058). Offline (no DB, no Drive). Invented codes only."""
import datetime, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requirements_wo03 as rq

R = []
def check(name, cond, detail=""):
    R.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + (f"  -- {detail}" if detail and not cond else ""))

K = rq.cadence_keep
check("C1 quarterly: quarters >= first_period only",
      not K(("quarterly", 20254), 2025, 3) and K(("quarterly", 20254), 2025, 4) and K(("quarterly", 20254), 2026, 1))
check("C2 annual: Q4 only, from first_period's year",
      K(("annual", 20254), 2025, 4) and not K(("annual", 20254), 2026, 1) and not K(("annual", 20254), 2025, 3)
      and not K(("annual", 20264), 2025, 4))
check("C3 none: no rows", not K(("none", None), 2025, 4) and not K(("none", 20254), None, None))
check("C4 no cadence row: annual from the rule's first FY (Q4 only)",
      K(None, 2025, 4, 2025) and not K(None, 2025, 1, 2025) and not K(None, 2024, 4, 2025) and not K(None, 2026, 2, 2025))

RULE = {"rule_id": "PCAP-Q", "subtype_code": None, "subject_type": "entity_partner_quarter", "period_from": 2025,
        "entity_filter": {"company_kind": ["fund", "spv"], "cadence": "ops.requirement_cadence"},
        "partner_filter": {"interest_kind": ["capital", "carried_interest"]}}
party = [{"entity": e, "partner": "LP-0001", "ckind": "fund", "interest": "capital", "is_gp": False} for e in ("QF", "AF", "OF", "NF")]
etype = {"QF": "fund", "AF": "fund", "OF": "fund", "NF": "fund", "NOROSTER": "fund"}
cad = {"QF": ("quarterly", 20254), "AF": ("annual", 20254), "NF": ("none", None)}
subs = rq.subjects(RULE, {}, party, etype, datetime.date(2026, 11, 25), {}, cad)
per = lambda e: sorted((x[2], x[3]) for x in subs if x[0] == e)
check("C5 builder: quarterly fund -> 2025 Q4 .. 2026 Q3", per("QF") == [(2025, 4), (2026, 1), (2026, 2), (2026, 3)], str(per("QF")))
check("C6 builder: annual fund -> 2025 Q4 only", per("AF") == [(2025, 4)], str(per("AF")))
check("C7 builder: other fund (no row) -> annual fallback 2025 Q4", per("OF") == [(2025, 4)], str(per("OF")))
check("C8 builder: none -> no rows", per("NF") == [], str(per("NF")))
check("C9 builder: a no-roster entity follows its cadence too (fallback annual)", per("NOROSTER") == [(2025, 4)], str(per("NOROSTER")))
v1 = dict(RULE, entity_filter={"company_kind": ["fund", "spv"]})
check("C10 a rule without entity_filter.cadence is unchanged (v1: every quarter from FY2025)",
      len([x for x in rq.subjects(v1, {}, party, etype, datetime.date(2026, 11, 25), {}, cad) if x[0] == "NF"]) == 7)
print(f"\n{sum(R)}/{len(R)} passed")
