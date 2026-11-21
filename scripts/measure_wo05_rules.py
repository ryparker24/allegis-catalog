r"""
CAT-WO-05 R-032 · measure each Status rule (read-only; counts and codes only), for Ryan's veto at the dry run.

  py scripts\measure_wo05_rules.py --db-url-file <url file> [--release] [--sample 200] [--seed 5]

Scope: labelled documents (Find), non-executable kinds (Stage covers executable ones), primary copy decides.
Per rule:
  matches      documents the rule matches on its own (any current Status)
  effective    documents it sets (blank after the released rules and portal postings, first matching rule wins)
  precision    against independent evidence, on all its matches and on a seeded random sample:
                 person    a person-set Status (status_confirmed). Status strength: draft / in_review < final < issued.
                           agree = the same Status; consistent = the person's is STRONGER in the same direction (a Final
                           rule on a document a person marked Issued); contradicts = the person's points the other way
                           (a Final / Issued rule on a person's Draft, a Draft rule on a person's Final / Issued)
                 portal    posted in a portal = Issued: consistent for Final / Issued rules, contradicts a Draft rule
                 version   Draft rules: a non-current version member (supports Draft)
  --sample-file writes a LOCAL spot-check sheet (catalog ID, rule, kind, Drive link; never a name) for Ryan.
Prints rule IDs, kinds and counts only.
"""
import argparse, collections, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import dbguard_wo03 as dbg
import derive_wo02 as dw
import portals_wo05 as pw


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--sample-file", help="local CSV (outside the repo): 25 random matches per rule with their Drive links")
    a = ap.parse_args()
    con = psycopg.connect(dbg.checked_url(a.db_url_file, a.release))
    con.read_only = True
    cur = con.cursor()
    rules = pw.load_status_rules(cur, include_vetoed=True)
    k1y = pw.k1_portal_years(cur)
    portal = pw.portal_status(cur)
    cur.execute("SELECT code FROM ref.vocab WHERE list_name = 'executable_kind' AND active IS NOT FALSE")
    executable = {r[0] for r in cur.fetchall()}
    cur.execute("""SELECT v.document_id, f.name, f.path_segments, f.file_type_family, v.kind, v.entities, v.fiscal_year,
                          coalesce(v.requires_execution, false), v.stage, d.status_confirmed, d.status_rule, v.version_role, v.web_view_link
                   FROM app.v_find_x v JOIN cat.file f USING (file_id) JOIN cat.document d ON d.document_id = v.document_id
                   WHERE v.document_id IS NOT NULL ORDER BY v.document_id, v.is_primary DESC NULLS LAST, v.file_id""")
    seen, docs = set(), []
    for r in cur:
        if r[0] in seen: continue
        seen.add(r[0]); docs.append(r)
    print(f"labelled documents {len(docs):,}; Status rules {len(rules)} (active {sum(r['active'] for r in rules)})")
    match = collections.defaultdict(list)
    eff = collections.Counter()
    eff_kind = collections.defaultdict(collections.Counter)
    blank_after = 0
    link = {}
    for d, name, segs, fam, kind, ents, fy, req, stage, sp, srule, vrole, wl in docs:
        link[d] = wl
        if bool(req) or kind in executable:
            continue
        segs = (segs or [])[1:]
        base, brule = dw.status_for(kind, False, name, segs, stage)
        a_st, a_rule = dw.afs_status(kind, fam)
        if a_st: base, brule = a_st, a_rule
        if d in portal: base, brule = "issued", portal[d]
        for r in rules:
            if pw.rule_matches(r, name, segs, fam, kind, ents or [], fy, k1y):
                match[r["rule_id"]].append((d, kind, sp, d in portal, vrole))
        if base is None and brule is None:
            st, rid = pw.first_rule([r for r in rules if r["active"]], name, segs, fam, kind, ents or [], fy, k1y)
            if rid:
                eff[rid] += 1; eff_kind[rid][kind or "(none)"] += 1
            else:
                blank_after += 1
    rng = random.Random(a.seed)
    RANK = {"draft": 0, "in_review": 0, "final": 1, "issued": 2}

    def judge(val, person):
        if not person or person == "superseded":
            return None
        if val == "draft":
            return "agree" if RANK.get(person) == 0 else "contradicts"
        rv, rp = RANK[val], RANK.get(person, -1)
        return "agree" if rp == rv else "consistent" if rp > rv else "contradicts"

    sheet = []
    for r in rules:
        rid, val = r["rule_id"], r["value"]
        ms = match[rid]
        print(f"\n{rid}  -> {val}{'' if r['active'] else '  (VETOED)'}  priority {r['priority']} · {r.get('note') or ''}".rstrip(" ·"))
        print(f"   matches {len(ms):,} · effective (sets it) {eff[rid]:,}")
        if val != "working":
            for label, pool in (("all matches", ms), (f"sample of {min(a.sample, len(ms))}", rng.sample(ms, min(a.sample, len(ms))) if ms else [])):
                j = collections.Counter(judge(val, x[2]) for x in pool)
                po = sum(1 for x in pool if x[3])
                vr = sum(1 for x in pool if x[4] in ("superseded", "draft_of", "redline"))
                bits = [f"person: agree {j['agree']}, consistent {j['consistent']}, contradicts {j['contradicts']}",
                        f"posted {po} ({'contradicts' if val == 'draft' else 'consistent'})"]
                if val == "draft": bits.append(f"non-current version {vr} (supports)")
                print(f"   {label}: " + "; ".join(bits))
        if eff_kind[rid]:
            print("   effective by kind: " + ", ".join(f"{k} {n:,}" for k, n in eff_kind[rid].most_common(8)))
        for x in rng.sample(ms, min(25, len(ms))) if ms else []:
            sheet.append((rid, val, x[0], x[1] or "", link.get(x[0]) or ""))
    if a.sample_file:
        import csv
        with open(a.sample_file, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["rule_id", "proposes", "catalog_id", "kind", "drive_link", "ryan_says_ok (y/n)"])
            w.writerows(sheet)
        print(f"\nspot-check sheet: {len(sheet)} rows written (local file)")
    print(f"\nnon-executable labelled documents still without a Status after all active rules: {blank_after:,}")


if __name__ == "__main__":
    main()
