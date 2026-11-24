r"""
CAT-WO-02 · write the R-021 (Parties on K-1s) and R-022 (Status) rule results to cat.document.*_auto,
and the item 9 kind rules Ryan ruled on (RK2-RK4 re-kinds, then the no-kind rules) to kind_auto, whole catalog,
plus the Schwab issuer (PDFs only, round 5), then the CAT-WO-04 version families (families_wo04).

  py pipeline/apply_derive_wo02.py --db-url-file <url file>            # dry run: counts only
  py pipeline/apply_derive_wo02.py --db-url-file <url file> --apply    # writes *_auto (never *_confirmed)
  ... --nokind-ruled K1N,K1F,NK04                                      # item 9: default = derive_wo02.NOKIND_RULED

MUST run after EVERY `drive_crawl.py derive` (full / incremental / derive): ops.build_documents() recomputes
kind_auto / issuer_auto / requires_execution_auto from the rules and would otherwise undo these results, and the
nightly re-sync would then push the old kinds back to Drive (coder review). drive_crawl.derive() calls run(conn)
right after build_documents (release step 9).

--db-url-file is required (no default). Only *_auto columns are written; a person's *_confirmed always wins in
the views. Counts only are printed.
"""
import sys, os, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import derive_wo02 as dw


def run(conn, ruled=None, apply=True, log=print):
    """The whole pass on an open psycopg connection. Commits when apply. Returns the counters."""
    ruled = set(dw.NOKIND_RULED if ruled is None else ruled)
    unknown = ruled - {r[0] for r in dw.NOKIND_RULES}
    if unknown: raise ValueError(f"unknown rule ids: {sorted(unknown)}")
    c = collections.Counter()
    with conn.cursor() as cur:
        cur.execute("SELECT entity_code, entity_type FROM ref.entity")
        ent_type = dict(cur.fetchall())
        cur.execute("SELECT code FROM ref.vocab WHERE list_name = 'executable_kind' AND active IS NOT FALSE")
        executable = {r[0] for r in cur.fetchall()}
        # item 9 · kinds run FIRST and over the WHOLE catalog (labelled or not; Ryan approved the rules catalog-wide),
        # so a file that just became a K-1 also gets its K-1 parties / status below. Machine kinds only: a document
        # with a person's kind_confirmed is never touched.
        #   1. RK2-RK4 re-kind (dw.rekind_rule) - they change a machine kind, e.g. lpa -> operating_agreement
        #   2. the ruled no-kind rules (dw.nokind_rule) on what is still blank
        cur.execute("""SELECT DISTINCT ON (rule_id) pattern FROM ops.decomposition_rule
                       WHERE rule_id = 'ISS-004P' AND active ORDER BY rule_id, version DESC""")
        r = cur.fetchone(); dw.set_bank_pattern(r[0] if r else None)    # NK03: the banks the catalog knows
        # CAT-WO-03.1 audited FS: Datum legal names -> entity codes (ref.party exists from CAT-WO-03 on)
        legal = collections.defaultdict(set)
        cur.execute("SELECT to_regclass('ref.party') IS NOT NULL")
        if cur.fetchone()[0]:
            cur.execute("SELECT DISTINCT datum_company_name, entity_code FROM ref.party WHERE entity_code IS NOT NULL")
            for nm, ent in cur.fetchall():
                legal[dw.legal_key(nm)].add(ent)
        afs_fy = {}
        new_kind, old_kind = {}, {}
        cur.execute("""SELECT fd.document_id, f.name, f.path_segments, f.file_type_family, d.kind_auto,
                              coalesce(d.execution_stage_confirmed, d.execution_stage_auto),
                              coalesce(d.issuer_confirmed, d.issuer_auto), d.kind_confirmed
                       FROM cat.file f JOIN cat.file_document fd ON fd.file_id = f.file_id
                       JOIN cat.document d ON d.document_id = fd.document_id
                       WHERE f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE
                         AND f.noise_flag IS NOT TRUE AND coalesce(f.handling, 'secret') <> 'secret'
                       ORDER BY fd.document_id, (fd.file_role = 'primary') DESC""")
        seen_doc = set()
        issuers = []                                             # Ryan round 5: Schwab -> bank, PDFs only
        for doc, name, segs, fam, kind, stage, issuer, person_kind in cur.fetchall():
            if doc in seen_doc: continue                         # one result per document: the primary copy decides
            seen_doc.add(doc)
            if dw.schwab_issuer((segs or [])[1:], fam, issuer):
                issuers.append(("bank", doc)); c["issuer:schwab-pdf->bank"] += 1
            if person_kind:                                      # a person's kind is never touched ...
                if person_kind == dw.AFS_KIND: afs_fy[doc] = None    # ... but audited statements are annual (FY kept)
                continue
            # CAT-WO-03.1 (Ryan): email / spreadsheet files are never the audited statements (the rules skip them)
            a = dw.afs_rule(name, (segs or [])[1:], kind, legal) if fam not in ("email", "sheet") else None
            if a:                                                # an annual report = audited FS, annual
                rid, fy, _ent = a
                afs_fy[doc] = fy; c[f"afs:{rid}:{kind or '(none)'}"] += 1
                if kind != dw.AFS_KIND:
                    new_kind[doc] = (rid, dw.AFS_KIND); old_kind[doc] = kind
                continue
            rid, k = dw.audit_kind_rule(name, fam, kind)         # P2 emails -> correspondence, P3 sheets -> FS, P5 audited PDFs -> AFS
            if k:
                c[f"kind:{rid}:{kind or '(none)'}->{k}"] += 1
                if k == dw.AFS_KIND: afs_fy[doc] = None          # audited statements are annual (FY kept)
                if k != kind:
                    new_kind[doc] = (rid, k); old_kind[doc] = kind
                continue
            rid, k = dw.rekind_rule(name, kind, stage, issuer)
            if not k and kind is None and ruled:
                rid, k = dw.nokind_rule(name, (segs or [])[1:], only=ruled, family=fam)
            if k and k != kind:
                new_kind[doc] = (rid, k); old_kind[doc] = kind; c[f"kind:{rid}:{kind or '(none)'}->{k}"] += 1
            if new_kind.get(doc, (None, kind))[1] == dw.AFS_KIND:  # e.g. KND-025: audited statements are annual
                afs_fy.setdefault(doc, None)
        kinds = [(k, d, k) for d, (rid, k) in new_kind.items()]
        # a re-kind from an executable kind to a non-executable one (e.g. subscription_agreement -> template,
        # legal_agreement -> formation_filing) also stops being "requires execution": Stage n_a, Status applies
        # (coder review). ops.build_documents does the same for rule kinds.
        not_exec = [(d,) for d, (rid, k) in new_kind.items() if old_kind[d] in executable and k not in executable]
        c["execution:cleared_by_rekind"] = len(not_exec)
        cur.execute("""SELECT v.file_id, v.document_id, f.name, f.path_segments, f.parent_ids[1], v.kind, v.entities,
                              coalesce(v.requires_execution, false), v.stage, v.is_primary, f.file_type_family, v.fiscal_year
                       FROM app.v_find v JOIN cat.file f USING (file_id) WHERE v.document_id IS NOT NULL""")
        rows = cur.fetchall()
        # CAT-WO-06.2: count K-1s per folder with each document's FINAL kind (this run's re-kinds included); counting the
        # kinds from before the re-kinds left K1-R3 unfired on a first pass and fired on a second (Parties flip-flop)
        k1_folder = collections.Counter(r[4] for r in rows if (new_kind[r[1]][1] if r[1] in new_kind else r[5]) == "k1")
        # one result per document: prefer the primary copy's path/name
        rows.sort(key=lambda r: (r[1], not r[9]))
        # CAT-WO-05: R-031 portal postings (Status = Issued) and the R-032 status rules (proposals; Ryan vetoes at the dry run)
        import portals_wo05 as pw
        cur.execute("SELECT to_regclass('ref.portal_posting') IS NOT NULL")
        wo05 = cur.fetchone()[0]
        portal_rule = pw.portal_status(cur) if wo05 else {}
        st_rules = pw.load_status_rules(cur) if wo05 else []
        k1_years = pw.k1_portal_years(cur) if wo05 else set()
        seen, parties, status = set(), [], []
        fy_of = {}
        for fid, doc, name, segs, parent, kind, ents, req, stage, primary, fam, fy in rows:
            if doc in seen: continue
            seen.add(doc)
            fy_of[doc] = fy
            if doc in new_kind:                                   # new_kind holds machine kinds only
                kind = new_kind[doc][1]
                req = kind in executable and bool(req)            # an executable re-kind keeps the file's flag
                if kind not in executable: stage = "n_a"
            segs_l = [s.lower() for s in (segs or [])[1:]]
            if kind == "k1":
                iss, recv, rule = dw.k1_parties(segs_l, ents or [], ent_type, k1_folder[parent], set(ent_type))
                c[f"parties:{rule or 'unknown'}"] += 1
            else:
                iss, recv, rule = None, [], None          # no longer a K-1: rule-set parties are cleared
            parties.append((iss, recv or None, rule, doc))
            st, srule = dw.status_for(kind, bool(req) or kind in executable, name, (segs or [])[1:], stage)
            d_st, d_rule = dw.afs_status(kind, fam)               # P4: a Word file of the audited statements is a draft
            if d_st: st, srule = d_st, d_rule
            if doc in portal_rule:                                # R-031: posted in a portal = Issued (a person's Status still wins)
                st, srule = "issued", portal_rule[doc]
            elif st is None and srule is None and st_rules and not (bool(req) or kind in executable):
                st, srule = pw.first_rule(st_rules, name, (segs or [])[1:], fam, kind, ents or [], fy, k1_years)
            status.append((st, srule, doc)); c[f"status:{st or '-'}"] += 1
            if srule and (srule.startswith("ST5-") or srule.startswith("PORTAL-")): c[f"status_rule:{srule}"] += 1
        # CAT-WO-03 default (Ryan's K1-R2 question): a GP RECEIVES one or a few K-1s a year from its fund. More than
        # K1R2_MAX "received" K-1s for one GP and fiscal year are K-1s the GP issued to its members (or a mixed folder),
        # so that group's parties go back to unknown (the subject step sends them to Match subject) - never a guess.
        grp = collections.Counter((r[0], fy_of.get(d)) for i, r, ru, d in parties if ru == "K1-R2-gp-received" and r)
        crowded = {g for g, n in grp.items() if n > dw.K1R2_MAX}
        if crowded:
            out = []
            for i, r, ru, d in parties:
                if ru == "K1-R2-gp-received" and r and (r[0], fy_of.get(d)) in crowded:
                    c["parties:K1-R2-gp-received"] -= 1; c["parties:K1-R2-crowded->unknown"] += 1
                    out.append((None, None, None, d))
                else:
                    out.append((i, r, ru, d))
            parties = out
        log(f"labelled documents considered (parties / status): {len(seen):,}; catalog documents whose machine kind changes: {len(kinds):,}")
        for k, n in sorted(c.items()): log(f"  {k:<40} {n:>7,}")
        if not apply:
            log("DRY RUN: nothing written"); return c
        # write only what changed (no updated_at churn on every run - coder review)
        if kinds:   # kind_auto only, never over a person's kind
            cur.executemany("""UPDATE cat.document SET kind_auto=%s, updated_at=now()
                               WHERE document_id=%s AND kind_confirmed IS NULL AND kind_auto IS DISTINCT FROM %s""", kinds)
        if not_exec:
            cur.executemany("""UPDATE cat.document SET requires_execution_auto=false, execution_stage_auto='n_a', updated_at=now()
                               WHERE document_id=%s AND (requires_execution_auto, execution_stage_auto) IS DISTINCT FROM (false, 'n_a')""", not_exec)
        if afs_fy:   # audited FS: the report's fiscal year (when the name / year folder gives one) and an ANNUAL period
            cur.executemany("""UPDATE cat.document SET fiscal_year_auto=coalesce(%s, fiscal_year_auto), fiscal_quarter_auto=NULL, fye_flag_auto=true,
                                      updated_at=now()
                               WHERE document_id=%s AND (fiscal_year_auto, fiscal_quarter_auto, fye_flag_auto)
                                     IS DISTINCT FROM (coalesce(%s, fiscal_year_auto), NULL::smallint, true)""",
                            [(fy, d, fy) for d, fy in afs_fy.items()])
        if issuers:  # issuer_auto only where nothing (machine or person) set an issuer
            cur.executemany("UPDATE cat.document SET issuer_auto=%s, updated_at=now() WHERE document_id=%s AND issuer_auto IS NULL AND issuer_confirmed IS NULL", issuers)
        cur.executemany("""UPDATE cat.document SET issuing_entity_auto=%s, receiving_entities_auto=%s, parties_rule=%s, updated_at=now()
                           WHERE document_id=%s AND (issuing_entity_auto, receiving_entities_auto, parties_rule) IS DISTINCT FROM (%s, %s, %s)""",
                        [(i, r, ru, d, i, r, ru) for i, r, ru, d in parties])
        # CAT-WO-03.1 Location: each document's primary-copy path + how many folders hold a copy (the crawl's own data)
        cur.execute("SELECT to_regprocedure('ops.refresh_document_location()') IS NOT NULL")
        if cur.fetchone()[0]:
            cur.execute("SELECT ops.refresh_document_location()"); c["locations"] = cur.fetchone()[0]
        cur.executemany("""UPDATE cat.document SET status_auto=%s, status_rule=%s, updated_at=now()
                           WHERE document_id=%s AND (status_auto, status_rule) IS DISTINCT FROM (%s, %s)""",
                        [(st, ru, d, st, ru) for st, ru, d in status])
    conn.commit()
    # CAT-WO-04: version families, after kind, parties, subject (last night's) and status. Runs here, inside every derive,
    # so the Superseded status it sets is in place before the read-back / re-sync of the same night (else this step's
    # status reset above would be pushed to Drive and flipped back the next night).
    cur = conn.cursor()
    # CAT-WO-06 item 2: first-page reading, after kinds are set and before families / subject / requirements. Incremental,
    # capped per night; a Drive / OCR failure is reported and never stops the derive. Then the content check (fill blanks).
    cur.execute("SELECT to_regclass('cat.doc_page_read') IS NOT NULL")
    if cur.fetchone()[0]:
        import pages_wo06
        pages_wo06.nightly_step(conn, log=log)
        cur = conn.cursor()
    cur.execute("SELECT to_regclass('cat.doc_family_member') IS NOT NULL")
    if cur.fetchone()[0]:
        import families_wo04
        families_wo04.run(conn, apply=True, log=log)
    # CAT-WO-05: Issued date, Published To, posting links, Portal kind conflicts; after families so a posted member stays Issued
    cur.execute("SELECT to_regclass('ref.portal_posting') IS NOT NULL")
    if cur.fetchone()[0]:
        import portals_wo05
        portals_wo05.apply_issued(conn, apply=True, log=log)
    log(f"APPLIED: audited FS {len(afs_fy):,}, kinds {len(kinds):,}, execution cleared {len(not_exec):,}, issuers {len(issuers):,}, parties {len(parties):,} documents, status {len(status):,}")
    return c


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url-file", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--nokind-ruled", default=",".join(sorted(dw.NOKIND_RULED)),
                    help="comma-separated no-kind rule ids Ryan approved (item 9); default: derive_wo02.NOKIND_RULED")
    a = ap.parse_args()
    ruled = {x.strip() for x in a.nokind_ruled.split(",") if x.strip()}
    with psycopg.connect(open(a.db_url_file).read().strip()) as conn:
        try:
            run(conn, ruled, apply=a.apply)
        except ValueError as e:
            sys.exit(str(e))


if __name__ == "__main__":
    main()
