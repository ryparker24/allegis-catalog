r"""
CAT-WO-02 item 0.1 / 0.2 and item 9 lists (READ-ONLY, counts and codes-only patterns).

  py scripts/measure_wo02_item0.py --db-url-file <catalog url file>

0.1  K-1 parties: how many K-1s each rule (pipeline/derive_wo02.py) would set issuing / receiving / both.
0.2  Status markers: files each name/folder marker would set, by kind; and the resulting Status by rule.
9    No-kind backlog: top 50 folder paths and name patterns, generalised by pipeline/safe_patterns.py.
"""
import sys, os, argparse, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import psycopg
import derive_wo02 as dw
from safe_patterns import Masker, name_pattern

ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
ap.add_argument("--only", choices=["k1", "status", "nokind"], default=None)
a = ap.parse_args()
url = open(a.db_url_file).read().strip()

with psycopg.connect(url, options="-c default_transaction_read_only=on") as c, c.cursor() as cur:
    m = Masker(cur)
    cur.execute("SELECT entity_code, entity_type FROM ref.entity")
    ent_type = dict(cur.fetchall())
    cur.execute("SELECT code FROM ref.vocab WHERE list_name = 'executable_kind'")
    executable_kinds = {r[0] for r in cur.fetchall()}
    cur.execute("""SELECT v.file_id, f.name, f.path_segments, f.parent_ids[1], v.kind, v.entities,
                          coalesce(v.requires_execution, false), v.stage
                   FROM app.v_find v JOIN cat.file f USING (file_id)""")
    rows = cur.fetchall()
print(f"labelled files in scope (app.v_find): {len(rows):,}")
codes = set(ent_type)

# ------------------------------------------------------------------ 0.1
if a.only in (None, "k1"):
    k1 = [r for r in rows if r[4] == "k1"]
    per_folder = collections.Counter(r[3] for r in k1)
    by_rule = collections.Counter(); totals = collections.Counter(); issuers = collections.Counter(); receivers = collections.Counter()
    for fid, name, segs, parent, kind, ents, req, stage in k1:
        segs_l = [s.lower() for s in (segs or [])[1:]]
        iss, recv, rule = dw.k1_parties(segs_l, ents or [], ent_type, per_folder[parent], codes)
        by_rule[(rule or "unknown", bool(iss), bool(recv))] += 1
        totals["issuing set"] += bool(iss); totals["receiving set"] += bool(recv); totals["both set"] += bool(iss and recv)
        if iss: issuers[ent_type.get(iss, "?")] += 1
        for x in recv: receivers["LP" if x == "LP" else ent_type.get(x, "?")] += 1
    print(f"\n== 0.1 K-1 parties ({len(k1):,} labelled K-1s; coverage BEFORE = 0 issuing / 0 receiving: the fields don't exist yet)")
    for (rule, i, r), n in sorted(by_rule.items(), key=lambda x: -x[1]):
        print(f"  {rule:<26} issuing={'set' if i else '-':<4} receiving={'set' if r else '-':<4} {n:>6,}")
    print(f"  AFTER (if applied): issuing set {totals['issuing set']:,} · receiving set {totals['receiving set']:,} · both {totals['both set']:,} · neither {len(k1) - totals['issuing set'] - totals['receiving set'] + totals['both set']:,}")
    print(f"  issuing by entity type: {dict(issuers)} · receiving by type: {dict(receivers)}")

# ------------------------------------------------------------------ 0.2
if a.only in (None, "status"):
    mk = collections.Counter(); mk_kind = collections.defaultdict(collections.Counter)
    st_rule = collections.Counter(); st_kind = collections.defaultdict(collections.Counter)
    for fid, name, segs, parent, kind, ents, req, stage in rows:
        segs_l = [s for s in (segs or [])[1:]]
        execu = bool(req) or (kind in executable_kinds)
        for x in dw.markers(name, segs_l):
            mk[x] += 1; mk_kind[x][kind or "(none)"] += 1
        st, rule = dw.status_for(kind, execu, name, segs_l, stage)
        st_rule[(rule or "-", st or "-")] += 1
        if st: st_kind[st][kind or "(none)"] += 1
    print("\n== 0.2 Status markers (labelled files; a file can carry several markers)")
    for x, n in mk.most_common():
        top = ", ".join(f"{k} {v:,}" for k, v in mk_kind[x].most_common(6))
        print(f"  {x:<15} {n:>7,}   top kinds: {top}")
    print("  resulting Status (non-executable kinds by markers; executable kinds: Final only when fully executed):")
    for (rule, st), n in sorted(st_rule.items(), key=lambda x: -x[1]):
        print(f"    {rule:<24} -> {st:<10} {n:>7,}")
    for st in dw.STATUS_CODES:
        if st_kind[st]:
            print(f"    {st:<10} by kind: " + ", ".join(f"{k} {v:,}" for k, v in st_kind[st].most_common(8)))

# ------------------------------------------------------------------ item 9 lists
if a.only in (None, "nokind"):
    nk = [r for r in rows if r[4] is None]
    paths = collections.Counter(); names = collections.Counter()
    for fid, name, segs, parent, kind, ents, req, stage in nk:
        paths[m.path((segs or [])[1:])] += 1
        names[name_pattern(name, m)] += 1
    print(f"\n== 9 No-kind files: {len(nk):,}")
    print("  top 50 folder paths (codes / generic words only; * = other words, <name> = an LP or person name):")
    for p, n in paths.most_common(50): print(f"  {n:>6,}  …/{p}/")
    print("  top 50 name patterns:")
    for p, n in names.most_common(50): print(f"  {n:>6,}  {p}")
    rule_n = collections.Counter()
    for fid, name, segs, parent, kind, ents, req, stage in nk:
        rid, k = dw.nokind_rule(name, [s for s in (segs or [])[1:]])
        rule_n[rid or "none"] += 1
    print("  PROPOSED rules (first match wins; none applied):")
    for rid, kind, frx, nrx, desc in dw.NOKIND_RULES:
        print(f"    {rid}  -> {kind:<20} {rule_n[rid]:>6,}   {desc}")
    print(f"    no rule matches             {rule_n['none']:>6,}   (stay no-kind -> Review queue)")
