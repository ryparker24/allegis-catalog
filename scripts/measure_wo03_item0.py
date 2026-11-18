"""CAT-WO-03 item 0: measurements on the THROWAWAY branch (read-only queries), counts and codes only.
LP names (Datum display/legal names) and file names / folder paths are used ONLY in memory for matching and are
never printed, logged or written. Universe = app.v_find (labelled files, secret tier already excluded)."""
import argparse, csv, re, sys
from collections import Counter, defaultdict
import psycopg

ap = argparse.ArgumentParser(description="py db/wo03_prep/measure.py --owner-url-file <owner url file> --endpoint <branch ep-...>")
ap.add_argument("--owner-url-file", required=True)
ap.add_argument("--endpoint", required=True, help="branch endpoint id; the main endpoint is refused")
ap.add_argument("--roster", default=r"C:\DriveCatalog\datum_exports\datum_partner_roster_2026-11-17.csv")
_a = ap.parse_args()


sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "pipeline"))
import dbguard_wo03 as _dbg


def branch():
    url = next(l.strip().partition("=")[2].strip().strip("'\"") if not l.strip().startswith("postgres") else l.strip()
               for l in open(_a.owner_url_file, encoding="utf-8-sig") if "postgres" in l)
    m = re.search(r"@(ep-[a-z0-9-]+?)(-pooler)?\.", url)
    if not m or m.group(1) == _a.endpoint or _a.endpoint == _dbg.main_endpoint():   # CISO review: never main
        sys.exit("REFUSED: --endpoint must be a branch endpoint, not main")
    return psycopg.connect(url[: m.start(1)] + _a.endpoint + url[(m.end(2) if m.group(2) else m.end(1)):], autocommit=True)


ROSTER = _a.roster
rows = list(csv.DictReader(open(ROSTER, encoding="utf-8-sig")))
c = branch()
c.execute("SET default_transaction_read_only = on")

# ---- Datum company -> catalog entity: exact code, name alias, plus the order's PROPOSED mappings (flagged)
PROPOSED = {"Allegis X": "X", "Dragos (SPV)": "ACCSO", "Shape MTV-VI (SPV)": "MTV-VI", "Allegis IVY (SPV)": "IVY", "Allegis TM (SPV)": "TM"}
codes = {r[0] for r in c.execute("select entity_code from ref.entity")}
dmap = {}
for code in {r["company_code"] for r in rows}:
    dmap[code] = code if code in codes else PROPOSED.get(code)
gp_names = {r["company_name"].strip().lower() for r in rows if r["company_kind"] == "gp"} | {r["company_code"].strip().lower() for r in rows if r["company_kind"] == "gp"}
is_gp = lambda r: r["legal_name"].strip().lower() in gp_names or r["display_name"].strip().lower() in gp_names

roster = defaultdict(list)  # catalog entity -> partner rows
for r in rows:
    e = dmap.get(r["company_code"])
    if e:
        r = dict(r); r["is_gp_row"] = is_gp(r)
        roster[e].append(r)

print("== 1. roster size per Datum company (all / LP-subscription expected / GP row / carried_interest), catalog entity")
by = defaultdict(list)
for r in rows: by[r["company_code"]].append(r)
for code in sorted(by, key=lambda k: (by[k][0]["company_kind"], k)):
    rs = by[code]
    gp = sum(1 for r in rs if is_gp(r))
    ci = sum(1 for r in rs if r["interest_kind"] == "carried_interest")
    lp_exp = sum(1 for r in rs if r["interest_kind"] == "capital" and not is_gp(r))
    print(f"  {code:22} {rs[0]['company_kind']:4} all={len(rs):3} lp_sub_expected={lp_exp:3} gp_row={gp} carry={ci}  -> {dmap[code] or 'UNMAPPED'}{' (proposed)' if code in PROPOSED else ''}")

print("\n== 2. Datum company codes with no catalog entity (exact code), before proposals:")
print("  ", sorted(k for k in by if k not in codes))
fund_like = {e for (e, t) in c.execute("select entity_code, coalesce(entity_type,'?') from ref.entity") if t in ("fund", "spv", "?", "gp")}
print("  reverse gap - catalog entities (fund/spv/gp/untyped) with no Datum roster:", sorted(fund_like - set(roster)))

# ---- documents
docs = c.execute("""select f.file_id, f.kind, f.entities, f.fiscal_year, f.period, f.is_primary, f.stage, cf.name, cf.path_segments
                    from app.v_find f join cat.file cf using (file_id)
                    where f.kind in ('subscription_agreement','side_letter','k1','capital_statement','financial_statements','audit_report')""").fetchall()
print(f"\n== 3. candidate documents in the labelled universe: {len(docs)}")

def ents(d): return d[2] or []

print("\n== 3a. subscription_agreement / side_letter per entity (all copies | primary), vs LP-subscription roster")
sub = Counter(); subp = Counter(); sl = Counter(); slp = Counter(); noent = Counter()
for d in docs:
    if d[1] not in ("subscription_agreement", "side_letter"): continue
    if not ents(d): noent[d[1]] += 1
    for e in ents(d):
        (sub if d[1] == "subscription_agreement" else sl)[e] += 1
        if d[5]: (subp if d[1] == "subscription_agreement" else slp)[e] += 1
for e in sorted(set(sub) | set(sl) | set(roster)):
    lp_exp = sum(1 for r in roster.get(e, []) if r["interest_kind"] == "capital" and not r["is_gp_row"])
    print(f"  {e:20} sub={sub[e]:4} | {subp[e]:4}   side_letter={sl[e]:3} | {slp[e]:3}   roster_lp={lp_exp if e in roster else 'no roster'}")
print("  with no entity:", dict(noent))

# ---- partner auto-match (folder, then file name), in memory only
SUFFIX = r"\b(llc|l\.?l\.?c|lp|l\.?p|inc|ltd|limited|corp|corporation|co|company|trust|the|fund|partners?|holdings?|investments?|ttee|trustee|tr|dtd|u/a|ua|revocable|living|family|foundation|of|and|&)\b"
def norm(s): return re.sub(r"\s+", " ", re.sub(SUFFIX, " ", re.sub(r"[^a-z0-9&/ ]+", " ", (s or "").lower()))).strip()
def toks(s): return [t for t in norm(s).split() if len(t) >= 3]

result = defaultdict(Counter)  # kind -> high/low/none/no_roster
for d in docs:
    if d[1] not in ("subscription_agreement", "side_letter", "k1"): continue
    cands = [r for e in ents(d) for r in roster.get(e, [])]
    if not cands:
        result[d[1]]["no_roster"] += 1; continue
    fname = norm(d[7]); segs = [norm(s) for s in (d[8] or [])]
    full, partial = set(), set()
    for r in cands:
        names = {norm(r["legal_name"]), norm(r["display_name"])} - {""}
        if any(n and (n in segs) for n in names):
            full.add(("folder", r["partner_code"])); continue
        if any(len(n) >= 6 and n in fname for n in names):
            full.add(("name", r["partner_code"])); continue
        tk = set(toks(r["legal_name"])) | set(toks(r["display_name"]))
        if tk and any(t in fname.split() or any(t in s.split() for s in segs) for t in tk if len(t) >= 5):
            partial.add(r["partner_code"])
    fp = {p for _, p in full}
    if len(fp) == 1:
        result[d[1]]["high_folder" if any(m == "folder" for m, _ in full) else "high_name"] += 1
    elif len(fp) > 1 or partial:
        result[d[1]]["low"] += 1
    else:
        result[d[1]]["none"] += 1
print("\n== 4. partner auto-match (high = exactly one roster partner by folder segment or full name; low = several or token only)")
for k, v in result.items():
    n = sum(v.values())
    print(f"  {k:24} n={n:5} " + "  ".join(f"{x}={v[x]} ({100*v[x]/n:.0f}%)" for x in ("high_folder", "high_name", "low", "none", "no_roster")))

print("\n== 5. K-1s per entity x FY (primary copies) vs roster size (partners), FY2021-2025")
k1 = Counter()
for d in docs:
    if d[1] == "k1" and d[5] and d[3]:
        for e in ents(d): k1[(e, d[3])] += 1
years = [2021, 2022, 2023, 2024, 2025]
for e in sorted({e for e, _ in k1} | set(roster)):
    print(f"  {e:20} roster={len(roster[e]) if e in roster else '-':>4}  " + "  ".join(f"{y}:{k1[(e, y)]:4}" for y in years))

print("\n== 6. capital_statement (PCAP) per entity x quarter, FY2024-2025 (all copies)")
pc = Counter()
for d in docs:
    if d[1] == "capital_statement" and d[3]:
        for e in ents(d): pc[(e, d[3], d[4] or "-")] += 1
for e in sorted({e for e, _, _ in pc}):
    print(f"  {e:20} " + "  ".join(f"{y}{q}:{pc[(e, y, q)]:3}" for y in (2024, 2025) for q in ("q1", "q2", "q3", "q4")) + f"   (no quarter: {sum(v for (e2, y, q), v in pc.items() if e2 == e and q == '-')})")

print("\n== 7. audited FS: financial_statements / audit_report per entity x FY (primary), FY2022-2025")
fs = Counter()
for d in docs:
    if d[1] in ("financial_statements", "audit_report") and d[5] and d[3]:
        for e in ents(d): fs[(e, d[3], d[1])] += 1
for e in sorted({e for e, _, _ in fs}):
    print(f"  {e:20} " + "  ".join(f"{y}:{fs[(e, y, 'financial_statements')]}/{fs[(e, y, 'audit_report')]}" for y in (2022, 2023, 2024, 2025)))
