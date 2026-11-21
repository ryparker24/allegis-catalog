r"""
CAT-WO-05 item 0 · measure (read-only; counts and codes only). Needs ref.portal_posting loaded (portals_wo05 load) on
the database the url file points at. Nothing is written: the checklist effect is simulated in memory.

  py scripts\measure_wo05_item0.py --db-url-file <url file> [--release]
"""
import argparse, collections, datetime, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import dbguard_wo03 as dbg
import portals_wo05 as pw
import requirements_wo03 as rq


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    a = ap.parse_args()
    con = psycopg.connect(dbg.checked_url(a.db_url_file, a.release))
    con.read_only = True
    cur = con.cursor()

    print("1. postings per portal x document type x year")
    cur.execute("""SELECT portal, doc_type, coalesce(fiscal_year::text, '?'), count(*) FROM ref.portal_posting GROUP BY 1,2,3 ORDER BY 1,2,3""")
    by = collections.defaultdict(list)
    for p, t, y, n in cur.fetchall():
        by[(p, t)].append(f"{y}:{n}")
    for (p, t), v in sorted(by.items()):
        print(f"   {p} {t:4} " + " ".join(v))
    cur.execute("SELECT portal, count(*), count(DISTINCT file_id) FROM ref.portal_posting GROUP BY 1 ORDER BY 1")
    for p, n, f in cur.fetchall():
        print(f"   {p}: {n} postings, {f} distinct files")

    print("2. posted files the catalog knows")
    cur.execute(f"""SELECT p.portal, count(DISTINCT p.file_id), count(DISTINCT f.file_id) FILTER (WHERE {pw.LIVE}),
                           count(DISTINCT f.file_id) FILTER (WHERE f.file_id IS NOT NULL AND NOT ({pw.LIVE}))
                    FROM ref.portal_posting p LEFT JOIN cat.file f ON f.file_id = p.file_id GROUP BY 1 ORDER BY 1""")
    for p, n, live, dead in cur.fetchall():
        print(f"   {p}: posted files {n} · in the catalog (live) {live} · in the catalog but removed / trashed / secret {dead} · unknown {n - live - dead}")
    dp = pw.doc_postings(cur)
    m = collections.Counter(mt for v in dp.values() for _, mt in v)
    by_md5_only = sum(1 for v in dp.values() if all(mt == "md5" for _, mt in v))
    cur.execute(f"""SELECT count(DISTINCT f.file_id) FROM ref.portal_posting p JOIN cat.file pf ON pf.file_id = p.file_id
                    JOIN cat.file f ON f.md5 = pf.md5 AND f.file_id <> pf.file_id WHERE pf.md5 IS NOT NULL AND coalesce(pf.size_bytes,0) > 0 AND {pw.LIVE}""")
    print(f"   catalog documents with a posting: {len(dp):,} (links by file ID {m['file_id']:,}, by md5 {m['md5']:,}); "
          f"documents reached ONLY through an md5 copy: {by_md5_only:,}; other catalog files that are md5 copies of a posted file: {cur.fetchone()[0]:,}")

    print("3. catalog documents that would become Issued, by kind (labelled = in Find)")
    ids = sorted(dp)
    cur.execute("""SELECT d.document_id, coalesce(d.kind_confirmed, d.kind_auto), d.status_confirmed, coalesce(d.status_confirmed, d.status_auto),
                          EXISTS (SELECT 1 FROM app.v_find v WHERE v.document_id = d.document_id)
                   FROM cat.document d WHERE d.document_id = ANY(%s)""", (ids,))
    k, cur_st, labelled = collections.Counter(), collections.Counter(), 0
    person_kept = 0
    for d, kind, sp, st, lab in cur.fetchall():
        if sp and sp != "issued":
            person_kept += 1; continue
        if st == "issued":
            cur_st["already issued"] += 1; continue
        k[kind or "(none)"] += 1; cur_st[st or "(blank)"] += 1; labelled += lab
    print(f"   would become Issued: {sum(k.values()):,} (labelled {labelled:,}); already Issued {cur_st.pop('already issued', 0):,}; a person's other Status kept {person_kept:,}")
    print("   by kind: " + ", ".join(f"{x} {n:,}" for x, n in k.most_common()))
    print("   from today's Status: " + ", ".join(f"{x} {n:,}" for x, n in cur_st.most_common()))

    print("4. portal partner codes -> Datum roster")
    cur.execute("""SELECT portal, partner_map, count(DISTINCT portal_partner), count(*) FROM ref.portal_posting
                   WHERE portal_partner IS NOT NULL GROUP BY 1,2 ORDER BY 1,2""")
    for p, mp, n, np in cur.fetchall():
        print(f"   {p} {mp:10} partners {n:3} · postings {np}")
    parts = pw.doc_partners(cur, dp)
    how = collections.Counter(h for v in parts.values() for _, _, h in v)
    print(f"   documents with a mapped partner: {len(parts):,} (pairs by the posting {how['posting']:,}, ambiguous resolved by the document's entity {how['document_entity']:,})")

    print("5. checklist rows whose result would change (simulated; K-1 / PCAP; letters and capital notices have no checklist rule yet)")
    today = datetime.date.today()
    orig = rq.load
    _, _, mix0 = rq.build(cur, today)
    rows0 = {r["req_key"]: r for r in rq.build(cur, today)[1]}
    posted = set(dp)

    def patched(c):
        out = list(orig(c))
        docs, dparty = out[8], out[5]
        cur.execute("SELECT document_id FROM cat.document WHERE status_confirmed IS NOT NULL AND status_confirmed <> 'issued'")
        person = {r[0] for r in cur.fetchall()}
        for d in docs:
            if d["document_id"] in posted and d["document_id"] not in person:
                d["status"] = "issued"
        for d, v in parts.items():
            for code, _e, _h in v:
                if dparty[d].get(code) not in ("confirmed", "high"):
                    dparty[d][code] = "high"
        return tuple(out)
    rq.load = patched
    try:
        _, rows1, mix1 = rq.build(cur, today)
    finally:
        rq.load = orig
    ch = collections.Counter()
    for r in rows1:
        o = rows0.get(r["req_key"])
        a0 = o["result"] if o["result"] != "on_file" else f"on_file:{o['sub_status']}"
        a1 = r["result"] if r["result"] != "on_file" else f"on_file:{r['sub_status']}"
        if a0 != a1:
            ch[(r["rule_id"], a0, a1)] += 1
    for rid in ("K1-SET", "PCAP-Q", "AUDITED-FS", "LP-SUB", "LP-SIDE", "GP-COMMIT"):
        n = sum(v for (r, _, _), v in ch.items() if r == rid)
        print(f"   {rid:10} rows changing {n:,}   before: " + " ".join(f"{k}={v}" for k, v in sorted(mix0[rid].items())))
        print(f"   {'':10}                after:  " + " ".join(f"{k}={v}" for k, v in sorted(mix1[rid].items())))
        for (r, a0, a1), v in sorted(ch.items()):
            if r == rid:
                print(f"   {'':10}   {a0} -> {a1}: {v}")


if __name__ == "__main__":
    main()
