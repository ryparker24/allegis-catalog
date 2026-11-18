r"""
CAT-WO-02 · PROPOSED legal-name entity rules (Ryan, round 4) - one per entity, from the company_name column of the
Datum partner roster export. READ-ONLY; nothing is applied. Prints CODES AND COUNTS ONLY: no company names, no
patterns built from them, no file names. Only company_code / company_kind / company_name are read from the CSV; the
partner columns are never used.

  py scripts/measure_wo02_legalnames.py --db-url-file <catalog url file> --roster <datum_partner_roster_*.csv>

Pattern per entity: the legal name without its L.P. / LLC / Inc suffix, words joined by any punctuation / spaces,
whole words, and NOT followed by another fund number (so "Cyber Innovation Partners, L.P." never matches
"Cyber Innovation Partners II"). It reads the file name and every folder name, like the ENT-* / ENT-*P pairs.
Gains = live catalog files that would get the entity and do not have it today. Conflicts = files that would then
carry the entity AND another entity of the same family (e.g. CIP-I on a file that is CIP-II today).
"""
import sys, os, re, csv, argparse, collections
import psycopg

# Datum company_code -> catalog entity code. Only clear mappings; the rest are listed, never guessed.
MAP = {"ASOF": "ASOF", "Allegis IVY (SPV)": "IVY", "Allegis TM (SPV)": "TM", "Allegis X": "X", "Dragos (SPV)": "ACCSO",
       "CIP-I": "CIP-I", "CIP-I (GP)": "CIP-I (GP)", "CIP-II": "CIP-II", "CSOP": "CSOP",
       "MTV-IV (A)": "MTV-IV (A)", "MTV-IV (Annex)": "MTV-IV (Annex)", "MTV-IV (Annex) (GP)": "MTV-IV (Annex) (GP)",
       "MTV-IV (B)": "MTV-IV (B)", "MTV-IV (GP)": "MTV-IV (GP)", "MTV-V (A)": "MTV-V (A)", "MTV-V (B)": "MTV-V (B)",
       "MTV-V (GP)": "MTV-V (GP)", "MTV-V (MTEF)": "MTV-V (MTEF)", "NL-I": "NL-I", "NL-II": "NL-II", "Shape MTV-VI (SPV)": "MTV-VI"}
SUFFIX = re.compile(r"[\s,]*\b(l\.?\s?p\.?|l\.?\s?l\.?\s?c\.?|inc\.?|ltd\.?|limited partnership)\s*$", re.I)
# a fund number right after the name (II, IV, 2) - not a year (2019), which is common after a fund name
NUM_AFTER = r"(?![\W_]*(?:i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![a-z0-9]))"


def legal_rx(name):
    base = name.strip()
    while SUFFIX.search(base): base = SUFFIX.sub("", base).strip()
    words = [w for w in re.split(r"[\W_]+", base) if w]
    if len(words) < 2: return None, len(words)
    return re.compile(r"(?<![a-z0-9])" + r"[\W_]*".join(re.escape(w) for w in words) + r"(?![a-z0-9])" + NUM_AFTER, re.I), len(words)


ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
ap.add_argument("--roster", required=True)
a = ap.parse_args()
comp = {}
with open(a.roster, encoding="utf-8-sig", newline="") as f:
    for row in csv.DictReader(f):
        comp[row["company_code"]] = (row["company_kind"], row["company_name"])

LIVE = """coalesce(f.handling,'secret') <> 'secret' AND f.removed_run IS NULL AND f.trashed IS NOT TRUE
          AND f.is_shortcut IS NOT TRUE AND f.noise_flag IS NOT TRUE"""
with psycopg.connect(open(a.db_url_file).read().strip(), options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
    cur.execute("SELECT entity_code, family FROM ref.entity")
    family = dict(cur.fetchall())
    cur.execute("SELECT file_id, array_agg(entity_code) FROM cat.v_file_entity GROUP BY file_id")
    ents_of = dict(cur.fetchall())
    cur.execute(f"""SELECT f.file_id, f.name, f.path_segments, (l.file_id IS NOT NULL)
                    FROM cat.file f LEFT JOIN app.labelled_file l ON l.file_id = f.file_id WHERE {LIVE}""")
    files = [(fid, n, sg, lab, ents_of.get(fid) or []) for fid, n, sg, lab in cur.fetchall()]

rules = {}
for dcode, (kind, name) in comp.items():
    if dcode not in MAP: continue
    rx, nw = legal_rx(name)
    rules[MAP[dcode]] = (dcode, rx, nw)
print(f"roster companies: {len(comp)}; mapped to a catalog entity: {len(rules)}; live catalog files scanned: {len(files):,}")
seg_cache = {}
def hits(rx, s):
    k = (id(rx), s)
    if k not in seg_cache: seg_cache[k] = bool(rx.search(s))
    return seg_cache[k]

print("entity | words in legal name | files matched | gaining the entity: labelled / catalog | conflicting second entity (same family): labelled / catalog, with")
for ent, (dcode, rx, nw) in sorted(rules.items()):
    if rx is None:
        print(f"{ent} | {nw} | - | not proposed: legal name too short to be specific |"); continue
    m = g = gl = cf = cfl = 0; with_ = collections.Counter()
    for fid, name, segs, lab, ents in files:
        if not (rx.search(name or "") or any(hits(rx, s) for s in (segs or [])[1:])): continue
        m += 1
        if ent in ents: continue
        g += 1; gl += lab
        other = [e for e in ents if e != ent and family.get(e) and family.get(e) == family.get(ent)]
        if other:
            cf += 1; cfl += lab; with_.update(other)
    print(f"{ent} | {nw} | {m:,} | {gl:,} / {g:,} | {cfl:,} / {cf:,}" + (f" ({', '.join(f'{e} {n:,}' for e, n in with_.most_common(4))})" if with_ else ""))
print("not mapped (no catalog entity, or the mapping is not clear): " + ", ".join(sorted(k for k in comp if k not in MAP)))
