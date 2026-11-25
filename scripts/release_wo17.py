r"""CAT-WO-17 release steps. Run AFTER migration 017. Throwaway first; main only with --release (Ryan's go-ahead 2026-11-25).

  py scripts\release_wo17.py --db-url-file <url file> [--release] derive    the nightly's derive (pages off) + checklists,
                                                                             with a before/after of what Find shows
  py scripts\release_wo17.py --db-url-file <url file> [--release] copyzips --from-url-file <throwaway url file>
                                                                             copy the zip listing made on the throwaway
                                                                             (same Drive files, same md5) instead of
                                                                             downloading 9 GB again
ops.build_documents() is never run on its own: the later derive steps (ruled kinds, parties, status) must follow it.
Codes and counts only."""
import argparse, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(APP, "pipeline"))
import dbguard_wo03 as dbg

SNAP_COLS = "file_id, document_id, kind, fiscal_year, stage, status, entities::text AS entities, is_primary"
DIFF = """SELECT count(*) AS rows_before,
  count(*) FILTER (WHERE a.file_id IS NULL) AS gone,
  count(*) FILTER (WHERE a.is_primary IS DISTINCT FROM b.is_primary) AS primary_flipped,
  count(*) FILTER (WHERE a.kind IS DISTINCT FROM b.kind) AS kind_changed,
  count(*) FILTER (WHERE a.fiscal_year IS DISTINCT FROM b.fiscal_year) AS fy_changed,
  count(*) FILTER (WHERE a.stage IS DISTINCT FROM b.stage) AS stage_changed,
  count(*) FILTER (WHERE a.status IS DISTINCT FROM b.status) AS status_changed,
  count(*) FILTER (WHERE a.entities::text IS DISTINCT FROM b.entities) AS entities_changed
FROM ops.wo17_release_before b LEFT JOIN app.v_find_x a USING (file_id)"""


def unpooled(url):
    return url.replace("-pooler.", ".")          # derive uses temp tables + COPY


def main():
    import psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("step", choices=["derive", "copyzips"])
    ap.add_argument("--from-url-file")
    a = ap.parse_args()
    url = unpooled(dbg.checked_url(a.db_url_file, a.release))
    lg = lambda m: print(m, flush=True)
    with psycopg.connect(url) as con:
        ok = con.execute("SELECT to_regclass('cat.zip_member') IS NOT NULL AND position('R-060 v2' IN pg_get_functiondef('ops.build_documents()'::regprocedure)) > 0").fetchone()[0]
        if not ok:
            sys.exit("REFUSED: migration 017 is not on this database")

    if a.step == "derive":
        os.environ["CATWO06_PAGES"] = "0"                # no page reading here; content already read stays in use
        os.environ["CATALOG_APP_DIR"] = APP              # the derive hooks load THIS checkout's pipeline
        home = os.environ.get("DRIVECATALOG_DIR", r"C:\DriveCatalog")
        sys.path.insert(0, home)
        cwd = os.getcwd(); os.chdir(home)
        import drive_crawl as dc
        with psycopg.connect(url) as con:
            # kept if it exists: a second run still compares against the state before CAT-WO-17
            con.execute(f"CREATE TABLE IF NOT EXISTS ops.wo17_release_before AS SELECT {SNAP_COLS} FROM app.v_find_x")
            con.commit()
            before = con.execute("SELECT count(*), count(*) FILTER (WHERE is_primary IS NOT FALSE) FROM app.v_find_x").fetchone()
        t = time.time()
        con = psycopg.connect(url)
        try:
            dc.derive(con)
        finally:
            con.close()
        lg(f"derive done ({time.time() - t:.0f}s)")
        t = time.time()
        dc.wo03_checklists(lambda: psycopg.connect(url))
        lg(f"checklists done ({time.time() - t:.0f}s)")
        os.chdir(cwd)
        with psycopg.connect(url) as con:
            cur = con.execute(DIFF)
            lg("find before/after: " + ", ".join(f"{d.name} {v:,}" for d, v in zip(cur.description, cur.fetchone())))
            after = con.execute("SELECT count(*), count(*) FILTER (WHERE is_primary IS NOT FALSE) FROM app.v_find_x").fetchone()
            lg(f"find rows {before[0]:,} -> {after[0]:,}; shown with copies hidden {before[1]:,} -> {after[1]:,}")
            for r in con.execute("SELECT rule_id, result, count(*) FROM app.v_requirement GROUP BY 1, 2 ORDER BY 1, 2").fetchall():
                lg(f"  checklist {r[0]} {r[1]}: {r[2]:,}")
        return

    if not a.from_url_file:
        sys.exit("copyzips needs --from-url-file")
    src_url = unpooled(dbg.checked_url(a.from_url_file, False))     # the source is never main
    with psycopg.connect(src_url) as src, psycopg.connect(url) as dst:
        live = {r[0]: r[1] for r in dst.execute("SELECT file_id, md5 FROM cat.file WHERE removed_run IS NULL AND handling <> 'secret'").fetchall()}
        zl = [r for r in src.execute("SELECT zip_file_id, zip_md5, status, member_count, note, rule_version, listed_at FROM cat.zip_listing").fetchall()
              if r[0] in live and live[r[0]] == r[1]]
        keep = {r[0] for r in zl}
        lg(f"zip listings to copy: {len(zl):,} (same file, same md5 on the target)")
        with dst.cursor() as cur:
            cur.execute("DELETE FROM cat.zip_listing WHERE zip_file_id = ANY(%s)", (list(keep),))
            cur.executemany("INSERT INTO cat.zip_listing (zip_file_id, zip_md5, status, member_count, note, rule_version, listed_at) VALUES (%s,%s,%s,%s,%s,%s,%s)", zl)
            n = 0
            with src.cursor(name="zm") as sc, cur.copy("""COPY cat.zip_member (zip_file_id, member_path, parent_member, is_dir, size_bytes,
                    compressed_bytes, crc32, member_mtime, md5, encrypted, nested_zip) FROM STDIN""") as cp:
                sc.execute("""SELECT zip_file_id, member_path, parent_member, is_dir, size_bytes, compressed_bytes, crc32, member_mtime, md5,
                              encrypted, nested_zip FROM cat.zip_member""")
                for row in sc:
                    if row[0] in keep:
                        cp.write_row(row); n += 1
        dst.commit()
        lg(f"zip members copied: {n:,}")


if __name__ == "__main__":
    main()
