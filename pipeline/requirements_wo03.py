r"""
CAT-WO-03 item 4 · build ops.requirement (derive, nightly): one row per requirement subject, its result, the best
document on file and the runners-up. Person overrides (app.requirement_override) always win; the rebuild never undoes them.

  py pipeline\requirements_wo03.py --db-url-file <branch url file> [--apply] [--release] [--today YYYY-MM-DD]

Subjects (from the active rules in ops.requirement_rule, Datum's roster in ref.party, applicability in
ops.requirement_applicability):
  entity_partner          LP-SUB / LP-SIDE / GP-COMMIT      roster rows passing the rule's partner filter
  entity_fy               AUDITED-FS                        rule's first FY .. last complete FY
  entity_partner_fy       K1-SET                            roster rows x FY
  entity_partner_quarter  PCAP-Q                            roster rows x quarter, rule's first FY .. last complete quarter
An entity of the rule's type with no Datum roster gets one "no roster in Datum" row per period (never an empty Met);
an entity whose conditional applicability is not answered gets "applicability not set" (never Missing).

Candidate scoring (deterministic):
  eligible  = kind in the rule's satisfying kinds or a subtype's candidate kind; the entity is on the document (entities
              or Parties issuing); the period matches (fiscal year; quarter = period q1-q4, 'fy' counts as q4); for a
              partner subject the document is matched to THAT partner (cat.doc_party); not marked Wrong (Catalog Review).
  ranking   = satisfying first, then a satisfying KIND (financial statements over an audit opinion alone), then a person-confirmed partner match, then a high match, then the primary copy, then
              the newest date (signed / issued / effective / modified), then document id.
  result    = met when the best satisfies (rule's stage / status) and its partner match is not low; otherwise on file,
              not final (sub-status: unknown / draft / final_unexecuted / partially_executed / final_not_issued /
              superseded / not_satisfying_kind / partner_unconfirmed); missing when there is no candidate (side letters:
              "none found (not tracked in Datum)").
Prints codes and counts only.
"""
import argparse, collections, datetime, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbguard_wo03 as dbg

URGENCY = {"missing": 0, "unknown": 1, "draft": 2, "final_unexecuted": 3, "final_not_issued": 3, "superseded": 3,
           "not_satisfying_kind": 3, "not_annual": 3, "partner_unconfirmed": 3, "partially_executed": 4, "none_found": 5, "met": 6,
           "not_required": 7, "no_roster": 8, "applicability_not_set": 8}
CONF_RANK = {"confirmed": 2, "high": 1, "low": 0}
MAX_CANDIDATES = 10


# ------------------------------------------------------------------ pure parts (unit-tested)
def periods(subject_type, first_fy, today):
    """the periods a rule checks: [(fy, quarter|None)] up to the last COMPLETE fiscal year / quarter (calendar FY)."""
    if subject_type == "entity_partner":
        return [(None, None)]
    last_fy = today.year - 1
    if subject_type in ("entity_fy", "entity_partner_fy"):
        return [(y, None) for y in range(first_fy or last_fy, last_fy + 1)]
    q_now = (today.month - 1) // 3 + 1                       # the quarter we are in is not complete
    last = (today.year, q_now - 1) if q_now > 1 else (today.year - 1, 4)
    out, y, q = [], first_fy or last[0], 1
    while (y, q) <= last:
        out.append((y, q))
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)
    return out


def req_key(rule_id, entity, partner, fy, q):
    return f"{rule_id}|{entity}|{partner or ''}|{fy or ''}|{('Q' + str(q)) if q else ''}"


def is_annual(doc):
    """CAT-WO-03.1: an annual document has the fiscal-year period or none - never a quarter"""
    return (doc.get("period") or "fy") == "fy"


def satisfies(doc, satisfied_when):
    if satisfied_when.get("annual") and not is_annual(doc):
        return False
    st = satisfied_when.get("stage")
    if st is not None:
        return doc.get("stage") in st
    ss = satisfied_when.get("status")
    if ss is not None:
        return doc.get("status") in ss
    return True


def sub_status(doc, satisfied_when, satisfying_kind):
    if not satisfying_kind:
        return "not_satisfying_kind"
    if satisfied_when.get("annual") and not is_annual(doc):
        return "not_annual"
    if satisfied_when.get("stage") is not None:
        s = doc.get("stage")
        return s if s in ("draft", "final_unexecuted", "partially_executed") else "unknown"
    s = doc.get("status")
    if s in (None, ""):
        return "unknown"
    if s in ("draft", "in_review"):
        return "draft"
    if s == "final":
        return "final_not_issued"
    return "superseded" if s == "superseded" else "unknown"


def rank_key(c):
    return (not c["satisfying"], not c["kind_satisfying"], -CONF_RANK.get(c.get("partner_conf") or "high", 1), not c["is_primary"],
            -(c["date_ord"] or 0), c["document_id"])


def evaluate(cands, satisfied_when, override=None, no_candidate_result="missing", link_doc=None):
    """cands: eligible candidate dicts (kind_satisfying, stage, status, partner_conf, is_primary, date_ord, document_id,
    file_id ...). -> (result, sub_status, best or None, sorted candidates, override_id)."""
    for c in cands:
        c["satisfying"] = bool(c["kind_satisfying"] and satisfies(c, satisfied_when))
    ranked = sorted(cands, key=rank_key)
    if override and override["action"] == "not_required":
        return "not_required", None, (ranked[0] if ranked else None), ranked, override["override_id"]
    if override and override["action"] == "link":
        best = link_doc or {"file_id": override["file_id"], "document_id": override.get("document_id")}
        return "met", None, dict(best, source="person"), ranked, override["override_id"]
    if not ranked:
        return no_candidate_result, None, None, ranked, None
    best = ranked[0]
    if best["satisfying"] and best.get("partner_conf") != "low":
        return "met", None, best, ranked, None
    sub = "partner_unconfirmed" if best["satisfying"] else sub_status(best, satisfied_when, best["kind_satisfying"])
    return "on_file", sub, best, ranked, None


# ------------------------------------------------------------------ DB
DOCS_SQL = """
SELECT DISTINCT ON (x.document_id) x.document_id, x.file_id, x.kind, x.entities, x.issuing_entity, x.fiscal_year, x.period,
       x.stage, x.status, x.is_primary,
       coalesce(x.signed_date, x.issued_date, x.effective_date, x.modified_time::date) AS dt
FROM app.v_find_x x
WHERE x.document_id IS NOT NULL AND x.kind = ANY(%s)
ORDER BY x.document_id, x.is_primary DESC NULLS LAST, x.file_id
"""
# Catalog Review = Wrong on ANY file of the document (the latest app review, or the live label read back) excludes it
WRONG_SQL = """
SELECT DISTINCT fd.document_id FROM cat.file_document fd
WHERE fd.file_id IN (SELECT file_id FROM (SELECT DISTINCT ON (file_id) file_id, status FROM app.review_event
                                          WHERE status IN ('confirmed', 'wrong') ORDER BY file_id, event_id DESC) r WHERE r.status = 'wrong'
                     UNION SELECT file_id FROM ops.label_state WHERE review_status = 'wrong')
"""


def load(cur):
    cur.execute("""SELECT DISTINCT ON (rule_id) rule_id, version, checklist, subtype_code, satisfying_kinds, subject_type, entity_filter,
                          partner_filter, period_from, satisfied_when
                   FROM ops.requirement_rule WHERE active ORDER BY rule_id, version DESC""")
    rules = [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]
    cur.execute("SELECT subtype_code, kind, role FROM ref.doc_subtype_kind")
    sk = collections.defaultdict(dict)
    for s, k, role in cur.fetchall():
        sk[s][k] = role
    cur.execute("SELECT entity_code, subtype_code, required FROM ops.requirement_applicability")
    app = {(e, s): r for e, s, r in cur.fetchall()}
    cur.execute("""SELECT DISTINCT entity_code, partner_code, datum_company_kind, interest_kind, is_company_gp
                   FROM ref.party WHERE entity_code IS NOT NULL ORDER BY 1, 2""")
    party = [dict(zip(["entity", "partner", "ckind", "interest", "is_gp"], r)) for r in cur.fetchall()]
    cur.execute("SELECT entity_code, entity_type FROM ref.entity WHERE active IS NOT FALSE")
    etype = dict(cur.fetchall())
    cur.execute("SELECT document_id, partner_code, confidence FROM cat.doc_party")
    dparty = collections.defaultdict(dict)
    for d, p, c in cur.fetchall():
        dparty[d][p] = c
    cur.execute(WRONG_SQL)
    wrong = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT DISTINCT ON (req_key) req_key, override_id, action, file_id, document_id FROM app.requirement_override ORDER BY req_key, override_id DESC")
    overrides = {r[0]: dict(zip(["req_key", "override_id", "action", "file_id", "document_id"], r)) for r in cur.fetchall() if r[2] != "clear"}
    kinds = sorted({k for r in rules for k in r["satisfying_kinds"]} | {k for s in sk.values() for k, role in s.items() if role == "candidate"})
    cur.execute(DOCS_SQL, (kinds,))
    docs = [dict(zip(["document_id", "file_id", "kind", "entities", "issuing", "fy", "period", "stage", "status", "is_primary", "dt"], r))
            for r in cur.fetchall()]
    return rules, sk, app, party, etype, dparty, wrong, overrides, docs


def subjects(rule, app, party, etype, today):
    """-> [(entity, partner|None, fy, q, preset_result|None)]"""
    ef, pf = rule["entity_filter"] or {}, rule["partner_filter"] or {}
    kinds = set(ef.get("company_kind") or [])
    plus_app = set(ef.get("plus_applicability") or [])
    sub = rule["subtype_code"]
    need_app = ef.get("applicability") == "required"
    pers = periods(rule["subject_type"], rule["period_from"], today)
    per_partner = "partner" in rule["subject_type"]
    # one Datum company kind per entity, deterministic (fund > spv > gp) when two companies map to one entity
    rank = {"fund": 0, "spv": 1, "gp": 2}
    roster_ckind = {}
    for p in party:
        k = roster_ckind.get(p["entity"])
        if k is None or rank.get(p["ckind"], 9) < rank.get(k, 9):
            roster_ckind[p["entity"]] = p["ckind"]
    # entity-level rules (audited FS) don't need a roster: catalog entities of the type count too (coder review)
    scope_ckind = dict(roster_ckind)
    if not per_partner:
        for e, t in etype.items():
            scope_ckind.setdefault(e, t)
    out = []

    def entity_ok(e, ckind):
        """None = in scope; a string = the preset result for the entity's rows; False = not in the checklist."""
        if ckind in kinds:
            if need_app:
                a = app.get((e, sub))
                return "applicability_not_set" if a is None else (None if a else False)
            return None
        if ckind in plus_app:
            a = app.get((e, sub))
            return False if a is None or not a else None
        return False

    for e, ckind in sorted(scope_ckind.items()):
        ok = entity_ok(e, ckind)
        if ok is False:
            continue
        for fy, q in pers:
            if ok == "applicability_not_set":
                out.append((e, None, fy, q, ok)); continue
            if not per_partner:
                out.append((e, None, fy, q, None)); continue
            for p in party:
                if p["entity"] != e:
                    continue
                if "interest_kind" in pf and p["interest"] not in pf["interest_kind"]:
                    continue
                if "is_company_gp" in pf and bool(p["is_gp"]) != bool(pf["is_company_gp"]):
                    continue
                if rule["rule_id"] == "GP-COMMIT" and p["interest"] != "capital":
                    continue                                    # carried-interest rows expect no subscription
                out.append((e, p["partner"], fy, q, None))
    # the reverse gap: catalog entities of the rule's type with no Datum roster ("no roster in Datum", never an empty Met)
    if per_partner:
        rtypes = kinds | ({"manco"} if rule["subtype_code"] == "AUD-03" else set())   # Datum: AUD-03 required for mancos
        for e, t in sorted(etype.items()):
            if t in rtypes and e not in roster_ckind:
                for fy, q in pers:
                    out.append((e, None, fy, q, "no_roster"))
    seen, uniq = set(), []                    # one row per key (two relationships of one partner -> one requirement)
    for x in out:
        k = (x[0], x[1], x[2], x[3])
        if k not in seen:
            seen.add(k); uniq.append(x)
    return uniq


def build(cur, today, log=print):
    rules, sk, app, party, etype, dparty, wrong, overrides, docs = load(cur)
    by_entity = collections.defaultdict(list)
    for d in docs:
        if d["document_id"] in wrong:
            continue
        for e in set(d["entities"] or []) | ({d["issuing"]} if d["issuing"] else set()):
            by_entity[e].append(d)
    by_doc = {d["document_id"]: d for d in docs}
    by_file = {d["file_id"]: d for d in docs}
    run = f"req_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    rows, mix = [], collections.defaultdict(collections.Counter)
    for rule in rules:
        sat_kinds = set(rule["satisfying_kinds"])
        cand_kinds = sat_kinds | {k for k, role in sk.get(rule["subtype_code"] or "", {}).items() if role == "candidate"}
        sw = rule["satisfied_when"] or {}
        no_cand = "none_found" if sw.get("no_candidate_result") == "none_found" else "missing"
        for e, p, fy, q, preset in subjects(rule, app, party, etype, today):
            key = req_key(rule["rule_id"], e, p, fy, q)
            base = dict(req_key=key, rule_id=rule["rule_id"], rule_version=rule["version"], checklist=rule["checklist"],
                        subtype_code=rule["subtype_code"], subject_type=rule["subject_type"], entity_code=e, partner_code=p,
                        fiscal_year=fy, fiscal_quarter=q)
            if preset:
                rows.append(dict(base, result=preset, sub_status=None, urgency=URGENCY[preset], best=None, cands=[], override_id=None))
                mix[rule["rule_id"]][preset] += 1
                continue
            cands = []
            for d in by_entity.get(e, ()):
                if d["kind"] not in cand_kinds:
                    continue
                if fy is not None and d["fy"] != fy:
                    continue
                if q is not None and (d["period"] or "") not in (f"q{q}",) + (("fy",) if q == 4 else ()):
                    continue
                conf = None
                if p is not None:
                    conf = dparty.get(d["document_id"], {}).get(p)
                    if conf is None:
                        continue
                cands.append({"document_id": d["document_id"], "file_id": d["file_id"], "kind": d["kind"], "stage": d["stage"],
                              "status": d["status"], "period": d["period"], "is_primary": bool(d["is_primary"]), "partner_conf": conf,
                              "date": d["dt"].isoformat() if d["dt"] else None, "date_ord": d["dt"].toordinal() if d["dt"] else None,
                              "kind_satisfying": d["kind"] in sat_kinds})
            ov = overrides.get(key)
            link_doc = None
            if ov and ov["action"] == "link":
                ld = by_file.get(ov["file_id"]) or by_doc.get(ov["document_id"])
                link_doc = ld and {"document_id": ld["document_id"], "file_id": ov["file_id"], "kind": ld["kind"], "stage": ld["stage"],
                                   "status": ld["status"], "date": ld["dt"].isoformat() if ld["dt"] else None}
            # the MACHINE result is stored; app.v_requirement applies the latest override at read time, so Link / Not required /
            # Clear show at once and the rebuild never undoes them (coder review: storing the override broke Clear)
            result, sub, best, ranked, _ = evaluate(cands, sw, None, no_cand)
            ov_id = ov["override_id"] if ov else None
            urg = URGENCY[sub] if result == "on_file" else URGENCY[result]
            rows.append(dict(base, result=result, sub_status=sub, urgency=urg, best=best, cands=ranked, override_id=ov_id))
            mix[rule["rule_id"]][result if result != "on_file" else f"on_file:{sub}"] += 1
    return run, rows, mix


def reason(best, result, sub):
    if best is None:
        return None
    if best.get("source") == "person":
        return "linked by a person"
    bits = [best.get("kind") or "?"]
    if best.get("stage") and best["stage"] != "n_a": bits.append(f"stage {best['stage']}")
    if best.get("status"): bits.append(f"status {best['status']}")
    if best.get("period") and best["period"] != "fy": bits.append(f"period {best['period']}")
    if best.get("partner_conf"): bits.append(f"partner match {best['partner_conf']}")
    if not best.get("is_primary", True): bits.append("a copy (primary not in scope)")
    return ("qualifies: " if result == "met" else f"does not qualify ({sub}): ") + ", ".join(bits)


def write(cur, run, rows):
    cur.execute("DELETE FROM ops.requirement")   # not TRUNCATE: no ACCESS EXCLUSIVE lock, app reads keep working (coder review)
    data = []
    for r in rows:
        b = r["best"]
        cj = [{k: c.get(k) for k in ("document_id", "file_id", "kind", "stage", "status", "date", "satisfying", "partner_conf", "is_primary")}
              for c in r["cands"][:MAX_CANDIDATES]]
        data.append((r["req_key"], r["rule_id"], r["rule_version"], r["checklist"], r["subtype_code"], r["subject_type"], r["entity_code"],
                     r["partner_code"], r["fiscal_year"], r["fiscal_quarter"], r["result"], r["sub_status"], r["urgency"],
                     b and b.get("document_id"), b and b.get("file_id"), b and b.get("kind"), b and b.get("stage"), b and b.get("status"),
                     b and b.get("date"), reason(b, r["result"], r["sub_status"]), b and ("person" if b.get("source") == "person" else "auto"),
                     json.dumps(cj), len(r["cands"]), r["override_id"], run))
    cur.executemany("""INSERT INTO ops.requirement (req_key, rule_id, rule_version, checklist, subtype_code, subject_type, entity_code,
                         partner_code, fiscal_year, fiscal_quarter, result, sub_status, urgency, best_document_id, best_file_id, best_kind,
                         best_stage, best_status, best_date, best_reason, best_source, candidates, n_candidates, override_id, built_run)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""", data)


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--today", help="YYYY-MM-DD (tests); default today")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    with psycopg.connect(url) as conn:
        run_build(conn, today, apply=a.apply)


def run_build(conn, today=None, apply=False, log=print):
    """Rebuild ops.requirement on an open connection (nightly hook in drive_crawl.py, or main). Commits only when apply."""
    today = today or datetime.date.today()
    t0 = time.time()
    with conn.cursor() as cur:
        run, rows, mix = build(cur, today, log=log)
        if apply:
            write(cur, run, rows)
            conn.commit()
        else:
            conn.rollback()
    log(f"REQUIREMENTS {'APPLIED' if apply else 'DRY RUN (nothing written)'}: {len(rows):,} rows · run {run} · {time.time() - t0:.0f}s")
    for rid in sorted(mix):
        v = mix[rid]
        log(f"  {rid:10} n={sum(v.values()):5,}  " + "  ".join(f"{k}={n:,}" for k, n in sorted(v.items(), key=lambda kv: URGENCY.get(kv[0].split(':')[-1], 9))))


if __name__ == "__main__":
    main()
