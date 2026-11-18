r"""
CAT-WO-02 · write the R-021 (Parties on K-1s) and R-022 (Status) rule results to cat.document.*_auto,
and - only for rules Ryan has ruled on - the item 9 no-kind rules to kind_auto.

  py pipeline/apply_derive_wo02.py --db-url-file <url file>            # dry run: counts only
  py pipeline/apply_derive_wo02.py --db-url-file <url file> --apply    # writes *_auto (never *_confirmed)
  ... --nokind-ruled K1N,K1F,NK04                                      # item 9: default = derive_wo02.NOKIND_RULED

--db-url-file is required (no default). Only *_auto columns are written; a person's *_confirmed always wins in
the views. Counts only are printed.
"""
import sys, os, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg
import derive_wo02 as dw

ap = argparse.ArgumentParser()
ap.add_argument("--db-url-file", required=True)
ap.add_argument("--apply", action="store_true")
ap.add_argument("--nokind-ruled", default=",".join(sorted(dw.NOKIND_RULED)),
                help="comma-separated no-kind rule ids Ryan approved (item 9); default: derive_wo02.NOKIND_RULED")
a = ap.parse_args()
ruled = {x.strip() for x in a.nokind_ruled.split(",") if x.strip()}
unknown = ruled - {r[0] for r in dw.NOKIND_RULES}
if unknown: sys.exit(f"unknown rule ids: {sorted(unknown)}")

with psycopg.connect(open(a.db_url_file).read().strip()) as conn, conn.cursor() as cur:
    cur.execute("SELECT entity_code, entity_type FROM ref.entity")
    ent_type = dict(cur.fetchall())
    cur.execute("SELECT code FROM ref.vocab WHERE list_name = 'executable_kind'")
    executable = {r[0] for r in cur.fetchall()}
    c = collections.Counter()
    # item 9 · the ruled no-kind rules run FIRST and over the WHOLE catalog (labelled or not; Ryan approved them
    # catalog-wide), so a file that just became a K-1 also gets its K-1 parties / status in the pass below.
    new_kind = {}
    if ruled:
        cur.execute("""SELECT fd.document_id, f.name, f.path_segments, f.file_type_family
                       FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id
                       JOIN cat.document d ON d.document_id = fd.document_id
                       WHERE f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE
                         AND f.noise_flag IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret'
                         AND d.kind_confirmed IS NULL AND d.kind_auto IS NULL
                       ORDER BY fd.document_id, (fd.file_role = 'primary') DESC""")
        for doc, name, segs, fam in cur.fetchall():
            if doc in new_kind: continue                     # one result per document: the primary copy decides
            rid, k = dw.nokind_rule(name, (segs or [])[1:], only=ruled, family=fam)
            new_kind[doc] = (rid, k)
        new_kind = {d: rk for d, rk in new_kind.items() if rk[1]}
        for rid, _ in new_kind.values(): c[f"kind:{rid}"] += 1
    kinds = [(k, d) for d, (rid, k) in new_kind.items()]
    cur.execute("""SELECT v.file_id, v.document_id, f.name, f.path_segments, f.parent_ids[1], v.kind, v.entities,
                          coalesce(v.requires_execution, false), v.stage, v.is_primary, f.file_type_family
                   FROM app.v_find v JOIN cat.file f USING (file_id) WHERE v.document_id IS NOT NULL""")
    rows = cur.fetchall()
    k1_folder = collections.Counter(r[4] for r in rows if r[5] == "k1")
    # one result per document: prefer the primary copy's path/name
    rows.sort(key=lambda r: (r[1], not r[9]))
    seen, parties, status = set(), [], []
    for fid, doc, name, segs, parent, kind, ents, req, stage, primary, fam in rows:
        if doc in seen: continue
        seen.add(doc)
        kind = kind or new_kind.get(doc, (None, None))[1]
        segs_l = [s.lower() for s in (segs or [])[1:]]
        if kind == "k1":
            iss, recv, rule = dw.k1_parties(segs_l, ents or [], ent_type, k1_folder[parent], set(ent_type))
            c[f"parties:{rule or 'unknown'}"] += 1
        else:
            iss, recv, rule = None, [], None          # no longer a K-1: rule-set parties are cleared
        parties.append((iss, recv or None, rule, doc))
        st, srule = dw.status_for(kind, bool(req) or kind in executable, name, (segs or [])[1:], stage)
        status.append((st, srule, doc)); c[f"status:{st or '-'}"] += 1
    print(f"labelled documents considered (parties / status): {len(seen):,}; catalog documents given a kind: {len(kinds):,}")
    for k, n in sorted(c.items()): print(f"  {k:<36} {n:>7,}")
    if not a.apply:
        print("DRY RUN: nothing written"); sys.exit(0)
    # write only what changed (no updated_at churn on every run - coder review)
    cur.executemany("""UPDATE cat.document SET issuing_entity_auto=%s, receiving_entities_auto=%s, parties_rule=%s, updated_at=now()
                       WHERE document_id=%s AND (issuing_entity_auto, receiving_entities_auto, parties_rule) IS DISTINCT FROM (%s, %s, %s)""",
                    [(i, r, ru, d, i, r, ru) for i, r, ru, d in parties])
    cur.executemany("""UPDATE cat.document SET status_auto=%s, status_rule=%s, updated_at=now()
                       WHERE document_id=%s AND (status_auto, status_rule) IS DISTINCT FROM (%s, %s)""",
                    [(st, ru, d, st, ru) for st, ru, d in status])
    if kinds:   # kind_auto only, never over a person's kind; a later derive (build_documents) recomputes kind_auto,
                # so this script runs after every `drive_crawl.py derive`
        cur.executemany("UPDATE cat.document SET kind_auto=%s, updated_at=now() WHERE document_id=%s AND kind_auto IS NULL AND kind_confirmed IS NULL", kinds)
    conn.commit()
    print(f"APPLIED: parties {len(parties):,} documents, status {len(status):,}, no-kind kinds {len(kinds):,}")
