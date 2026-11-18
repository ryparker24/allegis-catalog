r"""
CAT-WO-02 item 9 · PROPOSED K-1 kind rules for the no-kind K-1-looking files (the FY2023 gap from CAT-WO-03 prep).
READ-ONLY; counts only (no names, no paths printed).

  py scripts/measure_wo02_item9c.py --db-url-file <catalog url file>

Universe: every live catalog file (not secret / removed / noise / trashed / shortcut), labelled or not.
"""
import sys, os, argparse, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import psycopg
from derive_wo02 import W

# K1N: the NAME says K-1 ("K-1", "K1", "K-1s", "Schedule K-1") - not "K-1065"-style numbers
K1N = W(r"(‹k-?1(?![0-9])|‹k1s›|‹k-1s›|‹schedule k-?1(?![0-9]))")
# K1F: a FOLDER is named for K-1s ("2023 K-1s", "K-1s from PwC", "Final K-1s", "<x> K1s")
K1F = W(r"(‹k-?1'?s?›(?![0-9])|‹k1s›)")
# the folder rule only for document-like files (a spreadsheet in a K-1 folder is usually a workpaper / allocation)
DOC_FAMILIES = {"pdf", "image", "doc"}   # values in cat.file.file_type_family; sheets/email/archives excluded

ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
a = ap.parse_args()
with psycopg.connect(open(a.db_url_file).read().strip(), options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
    cur.execute("""SELECT f.file_id, f.name, f.path_segments, f.file_type_family,
                          coalesce(d.kind_confirmed, d.kind_auto) AS kind,
                          coalesce(d.fiscal_year_confirmed, d.fiscal_year_auto) AS fy,
                          EXISTS (SELECT 1 FROM app.labelled_file l WHERE l.file_id = f.file_id) AS labelled
                   FROM cat.file f
                   LEFT JOIN cat.file_document fd ON fd.file_id = f.file_id
                   LEFT JOIN cat.document d ON d.document_id = fd.document_id
                   WHERE coalesce(f.handling,'secret') <> 'secret' AND f.removed_run IS NULL AND f.trashed IS NOT TRUE
                     AND f.is_shortcut IS NOT TRUE AND f.noise_flag IS NOT TRUE""")
    rows = cur.fetchall()
print(f"live catalog files: {len(rows):,}")

def rule(name, segs, fam):
    if K1N.search(name or ""): return "K1N name"
    if any(K1F.search(s) for s in (segs or [])[1:]) and (fam or "") in DOC_FAMILIES: return "K1F folder (document-like)"
    if any(K1F.search(s) for s in (segs or [])[1:]): return "K1F folder (spreadsheet/other: NOT proposed)"
    return None

looking = [(r, rule(r[1], r[2], r[3])) for r in rows]
looking = [(r, rl) for r, rl in looking if rl]
by_fy = collections.Counter(); by_fy_none = collections.Counter(); fam = collections.Counter(); hits = collections.Counter()
lab = collections.Counter(); before_k = collections.Counter()
for r, rl in looking:
    fy = r[5] or "(none)"
    by_fy[fy] += 1
    if r[4] is None:
        by_fy_none[fy] += 1
        hits[(rl, fy == 2023)] += 1
        fam[(r[3] or "?", rl)] += 1
        lab[(r[6], rl)] += 1
    else:
        before_k[r[4]] += 1
print(f"K-1-looking files (name or K-1 folder): {len(looking):,}; with a kind already: {sum(before_k.values()):,} "
      f"(k1 {before_k['k1']:,}; other kinds {sum(before_k.values()) - before_k['k1']:,}: " + ", ".join(f"{k} {n:,}" for k, n in before_k.most_common(6) if k != 'k1') + ")")
print("no-kind K-1-looking files by fiscal year:  " + ", ".join(f"{k} {n:,}" for k, n in sorted(by_fy_none.items(), key=lambda x: str(x[0]))))
print(f"  FY2023: K-1-looking {by_fy[2023]:,}, of which no kind {by_fy_none[2023]:,}")
print("\nPROPOSED (none applied) - first match wins, no-kind files only -> kind k1:")
for rl in ("K1N name", "K1F folder (document-like)", "K1F folder (spreadsheet/other: NOT proposed)"):
    print(f"  {rl:<46} FY2023 {hits[(rl, True)]:>6,}   all years {hits[(rl, True)] + hits[(rl, False)]:>6,}"
          f"   labelled {lab[(True, rl)]:>6,} / unlabelled {lab[(False, rl)]:>6,}")
print("  file types of the no-kind matches: " + ", ".join(f"{f}/{rl.split()[0]} {n:,}" for (f, rl), n in fam.most_common(10)))
prop = hits[("K1N name", True)] + hits[("K1F folder (document-like)", True)]
prop_all = prop + hits[("K1N name", False)] + hits[("K1F folder (document-like)", False)]
print(f"\nkind before -> after (proposed rules K1N + K1F-document): (none) -> k1  FY2023 {prop:,} · all years {prop_all:,}")
print(f"FY2023 no-kind K-1-looking files left without a kind: {by_fy_none[2023] - prop:,} (spreadsheets etc. in K-1 folders)")
