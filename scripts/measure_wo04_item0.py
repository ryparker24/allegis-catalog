r"""
CAT-WO-04 item 0 · measure version families BEFORE building. Read-only, counts and codes only (names stay in memory).

  py scripts\measure_wo04_item0.py --db-url-file <url file> [--release] [--samples 5]

Runs exactly the build's code (pipeline/families_wo04.plan) with no person-set rows.
"""
import argparse, collections, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import dbguard_wo03 as dbg, families_wo04 as fw, versions_wo04 as vw


def main():
    import psycopg
    ap = argparse.ArgumentParser(); dbg.add_args(ap)
    ap.add_argument("--samples", type=int, default=0, help="per kind, N sample families described by codes / patterns")
    a = ap.parse_args()
    conn = psycopg.connect(dbg.checked_url(a.db_url_file, a.release))
    with conn.cursor() as cur:
        tokens = fw.load_tokens(cur)
    members = fw.load_members(conn)
    person, prior = fw.load_person(conn)
    fams, rows, stats = fw.plan(members, tokens, person, prior)
    live = [f for f in fams if not f.get("drop")]
    by_doc = {m["document_id"]: m for m in members}
    multi = [f for f in live if len(f["members"]) > 1]
    print(f"labelled documents {len(members):,}; families {len(live):,} (multi-member {len(multi):,}; "
          f"single-member base/amendment links {len(live) - len(multi):,})")
    print("\n1. documents in multi-member families, by kind (high / medium)")
    k = collections.defaultdict(collections.Counter)
    for f in multi:
        for m in f["members"]: k[m["kind"]][f["confidence"]] += 1
    for kind, c in sorted(k.items(), key=lambda x: -sum(x[1].values())):
        print(f"   {kind:<32} {sum(c.values()):>6,}   high {c['high']:>6,}  medium {c['medium']:>6,}")
    print(f"   {'TOTAL':<32} {sum(sum(c.values()) for c in k.values()):>6,}")
    print("\n2. family size distribution, by confidence")
    sz = collections.Counter((f["confidence"], min(len(f["members"]), 10)) for f in multi)
    for conf in ("high", "medium"):
        print(f"   {conf:<7} " + "  ".join(f"{n if n < 10 else '10+'}:{sz[(conf, n)]:,}" for n in range(2, 11)))
    rc = collections.Counter(" + ".join(f["reason"]) for f in multi)
    for r, n in rc.most_common(): print(f"   reason {r:<60} {n:>6,}")
    print("\n3. token hits that drove grouping (members of multi-member families carrying the token)")
    th = collections.Counter()
    for f in multi: th.update(f["hits"])
    for t, n in th.most_common(): print(f"   {t:<16} {n:>7,}")
    print("\n4. roles (high + amendment links; medium families wait in Review)")
    rl = collections.Counter((fams[r["fam"]]["confidence"], r["role"]) for r in rows.values())
    for (conf, role), n in sorted(rl.items()): print(f"   {conf:<7} {role:<12} {n:>7,}")
    for kk, v in sorted(stats.items()): print(f"   {kk:<32} {v:>7,}")
    print("\n5. picks that disagree with today's Stage / Status (high families)")
    dis = collections.Counter()
    for d, r in rows.items():
        if fams[r["fam"]]["confidence"] != "high": continue
        m = by_doc[d]
        if r["role"] in ("superseded", "redline", "draft_of"):
            if m["status"] in ("final", "issued"): dis[f"not current, Status {m['status']}"] += 1
            if m["stage"] == "fully_executed": dis["not current, Stage fully_executed"] += 1
        if r["role"] == "current" and len(fams[r["fam"]]["members"]) > 1:
            if m["status"] in ("draft", "in_review"): dis[f"current, Status {m['status']}"] += 1
            if m["stage"] in ("draft", "final_unexecuted"): dis[f"current, Stage {m['stage']}"] += 1
            if m["status"] is None and m["stage"] in (None, "n_a", "unknown"): dis["current, no Status / Stage"] += 1
    for kk, v in sorted(dis.items()): print(f"   {kk:<40} {v:>7,}")
    # expected label writes: L6 on every labelled file of a member (high + person; medium only after review)
    print("\n6. expected label writes (high families only; medium wait for Review)")
    docs = {d for d, r in rows.items() if fams[r["fam"]]["confidence"] in ("high", "person")}
    sup = {d for d, r in rows.items() if r.get("status_superseded")}
    nf = collections.Counter()
    with conn.cursor(name="wo04_files") as cur:
        cur.itersize = 2000
        cur.execute("SELECT document_id FROM app.v_find_x WHERE document_id IS NOT NULL")
        for (d,) in cur:
            if d in docs: nf["l6"] += 1
            if d in sup: nf["sup"] += 1
    print(f"   L6 Version on {nf['l6']:,} files ({len(docs):,} documents)")
    print(f"   Status -> Superseded on {nf['sup']:,} files ({len(sup):,} documents; blank or machine Status only)")
    medium_docs = {d for d, r in rows.items() if fams[r["fam"]]["confidence"] == "medium"}
    print(f"   Link versions Review lane: {sum(1 for f in multi if f['confidence'] == 'medium'):,} families, {len(medium_docs):,} documents")
    if a.samples:
        print("\n7. sample families (codes / patterns only)")
        top = [kk for kk, _ in sorted(k.items(), key=lambda x: -sum(x[1].values()))[:5]]
        for kind in top:
            print(f"   -- {kind}")
            fs = [f for f in multi if f["members"][0]["kind"] == kind][:: max(1, len([f for f in multi if f['members'][0]['kind'] == kind]) // a.samples)][:a.samples]
            for f in fs:
                m0 = f["members"][0]
                desc = ", ".join(f"{rows[m['document_id']]['role']}[{m['stage'] or '-'}/{m['status'] or '-'}; {'+'.join(m['hits']) or 'no token'}]"
                                 for m in sorted(f["members"], key=lambda m: rows[m["document_id"]]["role"] != "current"))
                print(f"   {f['confidence']:<6} ents {'+'.join(m0['entities'] or []) or '-'} fy {m0['fy'] or '-'} {m0['period'] or ''} "
                      f"subj {'y' if vw.subj(m0) else '-'} n={len(f['members'])}: {desc}")


if __name__ == "__main__":
    main()
