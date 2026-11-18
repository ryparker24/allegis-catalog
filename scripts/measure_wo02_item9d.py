r"""
CAT-WO-02 item 9 · the ruling table for NK02-NK12 and T1 (Ryan: "a table I can rule on without reading code").
READ-ONLY; counts and codes-only NAME PATTERNS (pipeline/safe_patterns.py: LP / person words -> <name>, other
non-generic words -> *). No file names, no paths, no LP names are printed.

  py scripts/measure_wo02_item9d.py --db-url-file <catalog url file>

NK: whole catalog = every live catalog file (not secret / removed / noise / trashed / shortcut) whose document has
    no kind; labelled = those with Allegis labels (app.labelled_file). The approved K1N / K1F run first, then
    NK02-NK12 in order; first match wins, so each file is counted once.
T1: files whose kind is still decided by the tie-break (two kind rules at the same priority / distance / source
    give different kinds), after the KND-024 ruling.
"""
import sys, os, argparse, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import psycopg
import derive_wo02 as dw
from safe_patterns import Masker, name_pattern

LIVE = """coalesce(f.handling,'secret') <> 'secret' AND f.removed_run IS NULL AND f.trashed IS NOT TRUE
          AND f.is_shortcut IS NOT TRUE AND f.noise_flag IS NOT TRUE"""
ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
a = ap.parse_args()
with psycopg.connect(open(a.db_url_file).read().strip(), options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
    m = Masker(cur)
    cur.execute(f"""SELECT f.name, f.path_segments, f.file_type_family,
                           EXISTS (SELECT 1 FROM app.labelled_file l WHERE l.file_id = f.file_id)
                    FROM cat.file f
                    LEFT JOIN cat.file_document fd ON fd.file_id = f.file_id
                    LEFT JOIN cat.document d ON d.document_id = fd.document_id
                    WHERE {LIVE} AND coalesce(d.kind_confirmed, d.kind_auto) IS NULL""")
    nokind = cur.fetchall()
    # T1: the two best kind signals of a file tie on (priority, distance, from-the-name) but differ in value
    cur.execute(f"""WITH s AS (
                      SELECT s.file_id, s.value, s.rule_id, s.priority, s.distance, (s.source = 'name') AS nm,
                             row_number() OVER (PARTITION BY s.file_id ORDER BY s.priority, s.distance,
                                                (s.source = 'name') DESC, s.rule_id, s.value) AS rn
                      FROM cat.file_signal s
                      JOIN ops.decomposition_rule r ON r.rule_id = s.rule_id AND r.version = s.rule_version AND NOT r.multi
                      WHERE s.field = 'kind')
                    SELECT a.value, a.rule_id, b.value, b.rule_id, f.name,
                           EXISTS (SELECT 1 FROM app.labelled_file l WHERE l.file_id = f.file_id)
                    FROM s a JOIN s b ON b.file_id = a.file_id AND b.rn = 2
                    JOIN cat.file f ON f.file_id = a.file_id
                    WHERE a.rn = 1 AND {LIVE} AND (a.priority, a.distance, a.nm) = (b.priority, b.distance, b.nm)
                      AND a.value <> b.value""")
    ties = cur.fetchall()

order = [r[0] for r in dw.NOKIND_RULES]
every = set(order)
hits = collections.Counter(); lab = collections.Counter(); pats = collections.defaultdict(collections.Counter)
for name, segs, fam, labelled in nokind:
    rid, kind = dw.nokind_rule(name, (segs or [])[1:], only=every, family=fam)
    if not rid: continue
    hits[rid] += 1; lab[rid] += labelled
    pats[rid][name_pattern(name, m)] += 1
print(f"live catalog files with no kind: {len(nokind):,} (labelled {sum(r[3] for r in nokind):,})")
print("rule | kind (none ->) | whole catalog | labelled | top 3 name patterns (count)")
for rid, kind, frx, nrx, desc in dw.NOKIND_RULES:
    top = "  ·  ".join(f"{p} ({n:,})" for p, n in pats[rid].most_common(3))
    print(f"{rid} | {kind} | {hits[rid]:,} | {lab[rid]:,} | {top}")
left = len(nokind) - sum(hits.values())
print(f"no rule | stays no kind | {left:,} | {sum(r[3] for r in nokind) - sum(lab.values()):,} |")

print(f"\nT1 still-tied kinds (after KND-024 -> 24): {len(ties):,} files, labelled {sum(t[5] for t in ties):,}")
tc = collections.Counter(); tl = collections.Counter(); tp = collections.defaultdict(collections.Counter)
for v1, r1, v2, r2, name, labelled in ties:
    k = (v1, r1, v2, r2); tc[k] += 1; tl[k] += labelled; tp[k][name_pattern(name, m)] += 1
for k, n in tc.most_common(12):
    top = "  ·  ".join(f"{p} ({c:,})" for p, c in tp[k].most_common(3))
    print(f"{k[0]} ({k[1]}) beats {k[2]} ({k[3]}) | {n:,} | {tl[k]:,} | {top}")
