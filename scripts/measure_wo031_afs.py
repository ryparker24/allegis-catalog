r"""
CAT-WO-03.1 · measure the proposed audited-FS rule BEFORE building it. Read-only. Codes, ids and counts only:
file and folder names are matched in memory and never printed.

  py scripts\measure_wo031_afs.py --db-url-file <url file> [--release]

Rule (Ryan, 2026-11-19):
  A. name "<firm> <YYYY> Annual Report - <entity legal name>"            -> audited_financial_statements, FY = YYYY
  B. or a "_Final Reports" folder with "Annual Report" in the file name    -> audited_financial_statements
  entity from the legal name (Datum company_name); CIP-I's legal name only when the name has no "II", "III" or "2".
Reports: candidates by current kind; entity resolved / ambiguous / none; AUD-01 rows (entity x FY) filled; and
"Annual Report" files the rule misses (by reason).
"""
import argparse, collections, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import dbguard_wo03 as dbg

NAME_A = re.compile(r"^(?P<firm>.+?)\s+(?P<fy>(19|20)\d{2})\s+annual\s+report\s*[-–—]\s*(?P<legal>.+?)(\.[a-z0-9]{2,5})?$", re.I)
ANNUAL = re.compile(r"\bannual\s+report\b", re.I)
FINAL_SEG = re.compile(r"^_?final\s+reports?$", re.I)
YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
CIP1_EXCLUDE = re.compile(r"(\bII\b|\bIII\b|(?<![0-9])2(?![0-9]))")


SUFFIX = {"lp", "llc", "inc", "ltd", "l", "p", "c"}


def norm(s):
    """lower-case words, punctuation dropped, trailing entity-form words (L.P., LLC ...) removed"""
    t = re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()
    while t and t[-1] in SUFFIX:
        t.pop()
    return " ".join(t)


def legal_entities(name, legal):
    """entities whose Datum legal name appears in the file name (whole words, longest wins); CIP-I only without II/III/2"""
    n = " " + re.sub(r"[^a-z0-9]+", " ", (name or "").lower()) + " "
    best, hits = 0, set()
    for lg, ents in legal.items():
        if lg and f" {lg} " in n:
            if len(lg) > best: best, hits = len(lg), set(ents)
            elif len(lg) == best: hits |= ents
    if "CIP-I" in hits and CIP1_EXCLUDE.search(name or ""):
        hits.discard("CIP-I")
    return hits


def main():
    import psycopg
    ap = argparse.ArgumentParser(); dbg.add_args(ap); a = ap.parse_args()
    conn = psycopg.connect(dbg.checked_url(a.db_url_file, a.release))
    cur = conn.cursor()
    # legal names: Datum company names mapped to catalog entities
    legal = collections.defaultdict(set)
    for name, ent in cur.execute("SELECT DISTINCT datum_company_name, entity_code FROM ref.party WHERE entity_code IS NOT NULL"):
        legal[norm(name)].add(ent)
    required = {r[0] for r in cur.execute("SELECT entity_code FROM ops.requirement WHERE rule_id = 'AUDITED-FS'")}
    aud_rows = {(e, fy): res for e, fy, res in cur.execute("SELECT entity_code, fiscal_year, result FROM app.v_requirement WHERE rule_id = 'AUDITED-FS'")}
    cur.execute("""SELECT fd.document_id, f.name, f.path_segments, coalesce(d.kind_confirmed, d.kind_auto), fd.file_role = 'primary'
                   FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id JOIN cat.document d ON d.document_id = fd.document_id
                   WHERE f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE AND f.noise_flag IS NOT TRUE
                     AND f.name ~* 'annual[[:space:]]+report'""")
    docs = {}
    for doc, name, segs, kind, prim in cur.fetchall():
        a_m = NAME_A.match(name or "")
        b_m = any(FINAL_SEG.match(s or "") for s in (segs or []))
        hit = None
        ents = legal_entities(name, legal)
        if a_m:
            hit = ("A", int(a_m.group("fy")), ents)
        elif b_m:
            ys = {int(y) for y in YEAR.findall(name or "")}
            if len(ys) != 1:   # else the year folder (e.g. .../2025/2025-Q4/_Final Reports)
                ys = {int(y) for sg in (segs or []) for y in YEAR.findall(sg or "") if re.fullmatch(r"(19|20)\d{2}", (sg or "").strip())}
            hit = ("B", ys.pop() if len(ys) == 1 else None, ents)
        d = docs.setdefault(doc, {"kind": kind, "hits": [], "miss": None})
        if hit:
            d["hits"].append(hit)
        elif d["miss"] is None:
            d["miss"] = "annual_report_name_other_shape"
    rule_docs = {k: v for k, v in docs.items() if v["hits"]}
    print(f"documents with 'Annual Report' in a file name: {len(docs):,}; matched by the rule: {len(rule_docs):,}")
    print("  by path:", dict(collections.Counter(h[0] for v in rule_docs.values() for h in v["hits"][:1])))
    print("  current kind of matched documents:", dict(collections.Counter(v["kind"] or "(none)" for v in rule_docs.values()).most_common()))
    ent_state = collections.Counter()
    filled = collections.defaultdict(set)
    for doc, v in rule_docs.items():
        ents = set().union(*[h[2] for h in v["hits"]])
        fys = {h[1] for h in v["hits"] if h[1]}
        ent_state["entity resolved" if len(ents) == 1 else "entity ambiguous" if ents else "no entity from name"] += 1
        if len(ents) == 1 and len(fys) == 1:
            filled[(next(iter(ents)), next(iter(fys)))].add(doc)
    print("  entity:", dict(ent_state))
    print("AUD-01 rows (entity x FY) the rule would give a candidate to:")
    for (e, fy), ds in sorted(filled.items()):
        if e in required:
            print(f"  {e:10} FY{fy}  docs={len(ds)}  today={aud_rows.get((e, fy), 'not a row (FY before 2022 or not required)')}")
    other = sorted({k for k in filled if k[0] not in required})
    print(f"  (+{len(other)} entity x FY outside AUD-01 (not Required = Yes): {', '.join(sorted({e for e, _ in other}))})")
    print("AUD-01 rows still without a rule candidate:")
    for (e, fy), res in sorted(aud_rows.items()):
        if (e, fy) not in filled:
            print(f"  {e:10} FY{fy}  today={res}")
    miss = collections.Counter(v["miss"] for v in docs.values() if not v["hits"])
    print("'Annual Report' documents the rule misses:", dict(miss))
    # unresolved legal names (codes can't be shown: report counts only, by whether a company word is present)
    unres = sum(1 for v in rule_docs.values() if not set().union(*[h[2] for h in v["hits"]]) and any(h[0] == "A" for h in v["hits"]))
    print(f"  shape-A matches whose legal name maps to no Datum company: {unres}")
    conn.rollback()


if __name__ == "__main__":
    main()
