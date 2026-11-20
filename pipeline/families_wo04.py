r"""
CAT-WO-04 · the family build inside derive (after kind, parties, subject and status): group labelled documents into
version families (versions_wo04), pick the current member, write cat.doc_family / cat.doc_family_member and the
Superseded status, never over a person's value.

  py pipeline/families_wo04.py --db-url-file <url file>            # dry run: counts only
  py pipeline/families_wo04.py --db-url-file <url file> --apply    # writes

Person-set memberships (method = 'person', from the app's side-panel / merge actions) are never changed here:
  - a document a person put in a family stays there with the person's role / current flag;
  - a document a person removed from its family (family_id NULL, person) is never grouped again;
  - a machine group that holds person-set members joins their family (when they agree on one).
Counts only are printed; file names stay in memory.
"""
import argparse, collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import versions_wo04 as vw


def load_tokens(cur):
    cur.execute("SELECT to_regclass('ops.version_token') IS NOT NULL")
    if not cur.fetchone()[0]:
        return vw.Tokens()
    cur.execute("""SELECT t.token_id, t.pattern, t.marker FROM (SELECT DISTINCT ON (token_id) token_id, pattern, marker, active, seq
                   FROM ops.version_token ORDER BY token_id, version DESC) t WHERE t.active ORDER BY t.seq, t.token_id""")
    rows = cur.fetchall()
    return vw.Tokens(rows)


def load_members(conn, batch=2000):
    """one dict per labelled document (its primary copy decides name / shared drive), streamed in batches"""
    out, seen = [], set()
    with conn.cursor(name="wo04_members") as cur:
        cur.itersize = batch
        cur.execute("""SELECT v.document_id, f.name, v.kind, v.entities, v.subject_codes, v.subject_person,
                              v.fiscal_year, v.period, v.effective_date, f.modified_time, v.stage, v.status,
                              f.drive_id IS NOT NULL, d.status_confirmed IS NOT NULL,
                              d.status_confirmed IS NULL AND d.status_rule = 'VF-superseded'
                       FROM app.v_find_x v JOIN cat.file f USING (file_id) JOIN cat.document d ON d.document_id = v.document_id
                       WHERE v.document_id IS NOT NULL
                       ORDER BY v.document_id, v.is_primary DESC, f.drive_id IS NOT NULL DESC, f.modified_time DESC NULLS LAST""")
        for r in cur:
            if r[0] in seen: continue
            seen.add(r[0])
            out.append(dict(document_id=r[0], name=r[1], kind=r[2], entities=r[3], subject_codes=r[4], subject_person=r[5],
                            fy=r[6], period=r[7], effective_date=r[8], modified_time=r[9], stage=r[10], status=None if r[14] else r[11],   # never ranked on the Superseded this step set
                            shared=r[12], status_person=r[13], person=None))
    return out


def load_person(conn):
    """person-set memberships: doc -> dict(family=<family_id or None>, role, current)"""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('cat.doc_family_member') IS NOT NULL")
        if not cur.fetchone()[0]: return {}, {}
        cur.execute("""SELECT document_id, family_id, role, person_current, supersedes, amends FROM cat.doc_family_member
                       WHERE person_set""")
        p = {d: dict(family=f, role=r, current=c, supersedes=s, amends=a) for d, f, r, c, s, a in cur.fetchall()}
        cur.execute("SELECT document_id, family_id FROM cat.doc_family_member WHERE NOT person_set AND family_id IS NOT NULL")
        prior = dict(cur.fetchall())
    return p, prior


def plan(members, tokens, person, prior):
    """
    The whole computation, no writes. Returns (families, rows, stats):
      families: list of dict(fid (existing id or None), confidence, reason, member docs, hits)
      rows: doc -> dict(fam (index into families), role, supersedes, amends, method, confidence)
    """
    by_doc = {m["document_id"]: m for m in members}
    for d, p in person.items():
        if d in by_doc: by_doc[d]["person"] = p
    # documents a person took out of every family are never grouped; documents a person placed in a family take part
    # in grouping only so that a NEW version that arrives later joins the person's family (as a machine member)
    pinned = {d: p["family"] for d, p in person.items() if p["family"] is not None}
    cand = [m for m in members if m["person"] is None or m["document_id"] in pinned]
    raw = vw.build(cand, tokens)
    pf = collections.defaultdict(list)                       # person family id -> members
    for d, fid in pinned.items():
        if d in by_doc: pf[fid].append(by_doc[d])
    fams, stats0 = [], collections.Counter()
    for f in raw:
        pins = {pinned[m["document_id"]] for m in f["members"] if m["document_id"] in pinned}
        free_m = [m for m in f["members"] if m["document_id"] not in pinned]
        if not pins:
            fams.append(f); continue
        if len(pins) == 1 and f["confidence"] == "high" and free_m:
            pf[next(iter(pins))].extend(free_m); stats0["joined_person_family"] += len(free_m)
        # otherwise the free members stay alone (a group spanning two person families is never merged by the machine)
    # reuse prior family ids (stable IDs across nightly runs): the id most of a group's members had last time
    used = set(pf)
    for f in fams:
        c = collections.Counter(prior.get(m["document_id"]) for m in f["members"] if prior.get(m["document_id"]))
        f["fid"] = None
        for fid, _ in c.most_common():
            if fid not in used:
                f["fid"] = fid; used.add(fid); break
    for fid, ms in pf.items():
        fams.append(dict(fid=fid, members=ms, confidence="person", reason=["person"], hits=collections.Counter()))
    rows, cur_of = {}, []
    for i, f in enumerate(fams):
        cur, roles = vw.pick(f["members"])
        f["current"] = cur
        cur_of.append((i, cur))
        for m in f["members"]:
            role, sup = roles[m["document_id"]]
            p = m["person"]
            if p and p.get("role"):                         # a person's role / links are kept as set
                role, sup = p["role"], p.get("supersedes")
            rows[m["document_id"]] = dict(fam=i, role=role, supersedes=sup, amends=(p or {}).get("amends"),
                                          method="person" if p else "rule", confidence=f["confidence"])
    # R-028: amendments and A&Rs, over high-confidence and person families only (medium ones wait in Review)
    applied = [(i, c) for i, c in cur_of if fams[i]["confidence"] in ("high", "person")]
    # documents that are alone (no family) still count as bases / amendments: give them single-member families
    in_fam = set(rows)
    for m in members:
        if m["document_id"] in in_fam or m["person"] is not None: continue
        if m["kind"] in vw.AMENDS_BASE or m["kind"] in vw.AMENDS_BASE.values():
            pid = prior.get(m["document_id"])
            if pid in used: pid = None
            used.add(pid)
            fams.append(dict(fid=pid, members=[m], confidence="high", reason=["single"],
                             hits=collections.Counter(), current=m))
            i = len(fams) - 1
            rows[m["document_id"]] = dict(fam=i, role="current", supersedes=None, amends=None, method="rule", confidence="high")
            applied.append((i, m))
    amends, ar_sup, ambiguous = vw.amendment_links(applied, by_doc)
    stats = collections.Counter(stats0)
    for i in set(ambiguous):
        if fams[i]["confidence"] == "high":
            fams[i]["confidence"] = "medium"; fams[i]["reason"] = fams[i]["reason"] + ["amendment base unclear"]
            stats["amendment_base_ambiguous"] += 1
    for i, cur in applied:
        f = fams[i]
        d = cur["document_id"]
        if d in amends and rows[d]["method"] == "rule":
            base = amends[d]
            for m in f["members"]:
                if rows[m["document_id"]]["method"] == "rule":
                    rows[m["document_id"]]["amends"] = base
            if rows[d]["role"] == "current":
                rows[d]["role"] = "amends"                       # the amendment stays current alongside its base
            stats["amends"] += 1
            if base in ar_sup:                                   # its base was restated: the A&R carries it
                rows[d]["role"] = "superseded"; rows[d]["supersedes"] = ar_sup[base]
                stats["amendment_restated"] += 1
        if d in ar_sup and rows[d]["method"] == "rule":          # an earlier base, restated by an A&R
            for m in f["members"]:
                r = rows[m["document_id"]]
                if r["method"] == "rule" and not (vw.executed(m) and not vw.executed(by_doc[ar_sup[d]])):
                    if r["role"] == "current" or m is cur:
                        r["role"] = "superseded"; r["supersedes"] = ar_sup[d]
            stats["ar_supersedes"] += 1
    # single-member families made only to link bases / amendments are kept only when they link something
    linked = set(amends) | set(amends.values()) | set(ar_sup) | set(ar_sup.values())
    for i, f in enumerate(fams):
        if f.get("reason") == ["single"] and f["members"][0]["document_id"] not in linked:
            f["drop"] = True
            rows.pop(f["members"][0]["document_id"], None)
    # Status -> Superseded where it was blank or machine-set (never over a person's Status)
    for d, r in rows.items():
        m = by_doc[d]
        r["status_superseded"] = (r["role"] in ("superseded", "redline", "draft_of") and fams[r["fam"]]["confidence"] in ("high", "person")
                                  and not m["status_person"] and m["status"] != "superseded")
    return fams, rows, stats


def run(conn, apply=True, log=print, commit=True):
    with conn.cursor() as cur:
        tokens = load_tokens(cur)
    members = load_members(conn)
    person, prior = load_person(conn)
    fams, rows, stats = plan(members, tokens, person, prior)
    live = [f for f in fams if not f.get("drop")]
    c = collections.Counter(f["confidence"] for f in live)
    log(f"documents considered {len(members):,}; families {len(live):,} ({', '.join(f'{k} {v:,}' for k, v in sorted(c.items()))}); "
        f"members {sum(len(f['members']) for f in live):,}")
    for k, v in sorted(stats.items()): log(f"  {k:<32} {v:>7,}")
    if not apply:
        log("DRY RUN: nothing written"); return fams, rows, stats
    write(conn, live, fams, rows, commit=commit)
    return fams, rows, stats


def write(conn, live, fams, rows, commit=True):
    """Families and members. Machine rows are replaced each run; person rows are never touched. Status -> superseded
    on status_auto only (status_confirmed is the person's and always wins in the views)."""
    with conn.cursor() as cur:
        # 1. family ids: keep existing ones, create the new (one statement each, not one round trip per family)
        new = [f for f in live if f.get("fid") is None]
        if new:
            cur.execute("SELECT nextval('cat.doc_family_family_id_seq') FROM generate_series(1, %s)", (len(new),))
            for f, (fid,) in zip(new, cur.fetchall()): f["fid"] = fid
        cur.execute("DROP TABLE IF EXISTS pg_temp.wo04_f, pg_temp.wo04_m")
        cur.execute("CREATE TEMP TABLE wo04_f (family_id bigint PRIMARY KEY, confidence text, reason text[], current_document_id bigint) ON COMMIT DROP")
        with cur.copy("COPY wo04_f FROM STDIN") as cp:
            for f in live:
                cp.write_row((f["fid"], f["confidence"], f["reason"], f["current"]["document_id"]))
        cur.execute("""INSERT INTO cat.doc_family (family_id, method, confidence, reason, current_document_id)
                       SELECT family_id, 'rule', confidence, reason, current_document_id FROM wo04_f w
                       WHERE NOT EXISTS (SELECT 1 FROM cat.doc_family f WHERE f.family_id = w.family_id)""")
        # a reviewed (person) family keeps its confidence and reason; only its current member is refreshed
        cur.execute("""UPDATE cat.doc_family f SET confidence = CASE WHEN f.confidence = 'person' THEN f.confidence ELSE w.confidence END,
                              reason = CASE WHEN f.confidence = 'person' THEN f.reason ELSE w.reason END,
                              current_document_id = w.current_document_id, updated_at = now()
                       FROM wo04_f w WHERE w.family_id = f.family_id
                         AND (f.current_document_id IS DISTINCT FROM w.current_document_id
                              OR (f.confidence <> 'person' AND (f.confidence, f.reason) IS DISTINCT FROM (w.confidence, w.reason)))""")
        # 2. machine members: replace (person rows stay)
        cur.execute("CREATE TEMP TABLE wo04_m (document_id bigint PRIMARY KEY, family_id bigint, role text, supersedes bigint, "
                    "amends bigint, confidence text, status_superseded boolean) ON COMMIT DROP")
        with cur.copy("COPY wo04_m FROM STDIN") as cp:
            for d, r in rows.items():
                if r["method"] != "rule": continue
                cp.write_row((d, fams[r["fam"]]["fid"], r["role"], r["supersedes"], r["amends"], fams[r["fam"]]["confidence"], r["status_superseded"]))
        cur.execute("""DELETE FROM cat.doc_family_member m WHERE NOT m.person_set
                       AND NOT EXISTS (SELECT 1 FROM wo04_m w WHERE w.document_id = m.document_id)""")
        cur.execute("""INSERT INTO cat.doc_family_member AS m (document_id, family_id, role, supersedes, amends, method, confidence, person_set)
                       SELECT document_id, family_id, role, supersedes, amends, 'rule', confidence, false FROM wo04_m
                       ON CONFLICT (document_id) DO UPDATE SET family_id=excluded.family_id, role=excluded.role,
                           supersedes=excluded.supersedes, amends=excluded.amends, confidence=excluded.confidence, updated_at=now()
                       WHERE NOT m.person_set AND (m.family_id, m.role, m.supersedes, m.amends, m.confidence)
                             IS DISTINCT FROM (excluded.family_id, excluded.role, excluded.supersedes, excluded.amends, excluded.confidence)""")
        # 3. Superseded status (machine) on members that are no longer current; cleared when they are again
        cur.execute("""UPDATE cat.document d SET status_auto='superseded', status_rule='VF-superseded', updated_at=now()
                       FROM wo04_m w WHERE w.document_id = d.document_id AND w.status_superseded
                         AND d.status_confirmed IS NULL AND d.status_auto IS DISTINCT FROM 'superseded'""")
        # a family member whose machine status was made superseded and is current again: status back to the rule's
        # (apply_derive_wo02 recomputes status_auto every derive, before this step, so only rows THIS step set remain)
        cur.execute("""UPDATE cat.doc_family f SET n_members = n.c, method = CASE WHEN f.confidence = 'person' THEN 'person' ELSE f.method END
                       FROM (SELECT family_id, count(*)::int c FROM cat.doc_family_member WHERE family_id IS NOT NULL GROUP BY 1) n
                       WHERE n.family_id = f.family_id AND f.n_members IS DISTINCT FROM n.c""")
        # 4. families with no member left
        cur.execute("""DELETE FROM cat.doc_family f WHERE NOT EXISTS (SELECT 1 FROM cat.doc_family_member m WHERE m.family_id = f.family_id)""")
    if commit:                      # the DB guard test runs the build twice inside one transaction it rolls back
        conn.commit()


def main():
    import psycopg, dbguard_wo03 as dbg
    ap = argparse.ArgumentParser(); dbg.add_args(ap)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    with psycopg.connect(dbg.checked_url(a.db_url_file, a.release)) as conn:
        run(conn, apply=a.apply)


if __name__ == "__main__":
    main()
