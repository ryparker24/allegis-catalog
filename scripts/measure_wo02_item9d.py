r"""
CAT-WO-02 item 9 · counts for the kind rules AS RULED (Ryan, rounds 2-3): RK2-RK4 re-kinds, then the no-kind rules
(K1N, K1F, NK02-NK08, RK1Q / RK1F, NK12), exactly as pipeline/apply_derive_wo02.py runs them.
READ-ONLY; counts and codes-only NAME / FOLDER PATTERNS (pipeline/safe_patterns.py: LP / person words -> <name>,
other non-generic words -> *). No file names, no paths, no LP names are printed.

Run it after `drive_crawl.py derive` and BEFORE apply_derive_wo02.py --apply (derive resets kind_auto to the rule
results, so this shows what apply would change).

  py scripts/measure_wo02_item9d.py --db-url-file <catalog url file>

Files: every live catalog file (not secret / removed / noise / trashed / shortcut) whose document has no person
kind; labelled = has Allegis labels (app.labelled_file). A document's primary copy decides; every file of the
document is counted.
"""
import sys, os, argparse, collections, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import psycopg
import derive_wo02 as dw
from safe_patterns import Masker, name_pattern

LIVE = """coalesce(f.handling,'secret') <> 'secret' AND f.removed_run IS NULL AND f.trashed IS NOT TRUE
          AND f.is_shortcut IS NOT TRUE AND f.noise_flag IS NOT TRUE"""
OLD_NK03_FOLDER = dw.W(r"‹statements?›")
OLD_NK03_NAME = dw.W(r"(‹statements?›|‹stmts?›)")
EXCL = [("Financial Statements", dw.W(r"‹financial statements?›")), ("Capital Statements", dw.W(r"‹capital statements?›")),
        ("Partner / Capital Account Statements", dw.W(r"‹(partner|partners'?|capital) account statements?›")),
        ("K-1 folder", dw.W(r"(‹k-?1'?s?›(?![0-9])|‹k1s›)"))]

ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
a = ap.parse_args()
with psycopg.connect(open(a.db_url_file).read().strip(), options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
    m = Masker(cur)
    cur.execute("""SELECT DISTINCT ON (rule_id) pattern FROM ops.decomposition_rule
                   WHERE rule_id = 'ISS-004P' AND active ORDER BY rule_id, version DESC""")
    r = cur.fetchone(); dw.set_bank_pattern(r[0] if r else None)
    cur.execute(f"""SELECT fd.document_id, (fd.file_role = 'primary'), f.name, f.path_segments, f.file_type_family,
                           d.kind_auto, coalesce(d.execution_stage_confirmed, d.execution_stage_auto),
                           coalesce(d.issuer_confirmed, d.issuer_auto),
                           EXISTS (SELECT 1 FROM app.labelled_file l WHERE l.file_id = f.file_id)
                    FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id
                    JOIN cat.document d ON d.document_id = fd.document_id
                    WHERE {LIVE} AND d.kind_confirmed IS NULL""")
    rows = cur.fetchall()

# the document decision (primary copy first), as apply_derive_wo02.py makes it
rows.sort(key=lambda r: (r[0], not r[1]))
decision = {}
for doc, prim, name, segs, fam, kind, stage, issuer, lab in rows:
    if doc in decision: continue
    rid, k = dw.rekind_rule(name, kind, stage, issuer)
    if not k and kind is None:
        rid, k = dw.nokind_rule(name, (segs or [])[1:], only=dw.NOKIND_RULED, family=fam)
    decision[doc] = (rid, k) if k and k != kind else (None, None)

cat_n = collections.Counter(); lab_n = collections.Counter(); trans = collections.defaultdict(collections.Counter)
pats = collections.defaultdict(collections.Counter)
nk03_excl = collections.Counter(); nk03_excl_lab = collections.Counter(); nk03_excl_pat = collections.defaultdict(collections.Counter)
nokind_cat = nokind_lab = 0
for doc, prim, name, segs, fam, kind, stage, issuer, lab in rows:
    rid, k = decision[doc]
    if kind is None:
        nokind_cat += 1; nokind_lab += lab
    if rid:
        cat_n[rid] += 1; lab_n[rid] += lab; trans[rid][f"{kind or '(none)'} -> {k}"] += 1
        pats[rid][name_pattern(name, m)] += 1
    # NK03: what the old rule took that the bank-folder ruling now leaves out
    s = (segs or [])[1:]
    if kind is None and rid is None and OLD_NK03_NAME.search(name or "") and any(OLD_NK03_FOLDER.search(x) for x in s):
        why = next((label for label, rx in EXCL if any(rx.search(x) for x in s)), "no bank / account-statement folder")
        nk03_excl[why] += 1; nk03_excl_lab[why] += lab
        stmt = [x for x in s if OLD_NK03_FOLDER.search(x)]
        nk03_excl_pat[why][m.segment(stmt[-1]) if stmt else "?"] += 1

print(f"live catalog files without a person's kind: {len(rows):,}; of them no kind now: {nokind_cat:,} (labelled {nokind_lab:,})")
print("rule | files changed: labelled / whole catalog | kind before -> after | top 3 name patterns")
order = ["RK2", "RK3", "RK4"] + [r[0] for r in dw.NOKIND_RULES]
for rid in order:
    tr = ", ".join(f"{t} {n:,}" for t, n in trans[rid].most_common(4))
    top = "  ·  ".join(f"{p} ({n:,})" for p, n in pats[rid].most_common(3))
    print(f"{rid} | {lab_n[rid]:,} / {cat_n[rid]:,} | {tr} | {top}")
nk_total = sum(cat_n[r] for r in order if not r.startswith("RK") or r in ("RK1Q", "RK1F"))
nk_lab = sum(lab_n[r] for r in order if not r.startswith("RK") or r in ("RK1Q", "RK1F"))
print(f"no-kind files left after the rules: {nokind_cat - nk_total:,} (labelled {nokind_lab - nk_lab:,})")
print("\nNK03 · statement files the bank-folder ruling leaves out (old NK03 matched them), by reason:")
for why, n in nk03_excl.most_common():
    top = "  ·  ".join(f".../{p}/ ({c:,})" for p, c in nk03_excl_pat[why].most_common(4))
    print(f"  {why:<40} {nk03_excl_lab[why]:>6,} / {n:>6,}   statement folders: {top}")
