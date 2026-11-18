r"""
CAT-WO-03 ruling (c) · Ryan's filled-in applicability workbook -> ops.requirement_applicability.

  py pipeline\applicability_load_wo03.py --db-url-file <branch url file> [--xlsx C:\DriveCatalog\orders\CAT-WO-03_Applicability.xlsx] [--apply] [--release]

Reads the "Applicability" sheet (entity_code, company_kind, subtype_code, ..., Required, ..., note). Required must be
Yes / No; an Unknown or blank row is NOT loaded (the checklist then reads "applicability not set", never Missing).
Refuses unknown entity or subtype codes. Prints codes and counts only (notes are stored, never printed).
"""
import argparse, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbguard_wo03 as dbg

NEED = ["entity_code", "subtype_code", "Required", "note"]


def parse_rows(rows):
    """rows: list of header-keyed dicts -> (loadable [(entity, subtype, required bool, note)], skipped Counter)."""
    out, skipped = [], collections.Counter()
    for r in rows:
        ent, sub = (r.get("entity_code") or "").strip(), (r.get("subtype_code") or "").strip()
        if not ent or not sub:
            continue
        req = str(r.get("Required") or "").strip().lower()
        if req not in ("yes", "no"):
            skipped[req or "blank"] += 1
            continue
        note = r.get("note")
        out.append((ent, sub, req == "yes", str(note).strip()[:500] if note not in (None, "") else None))
    return out, skipped


def main():
    import openpyxl, psycopg
    ap = argparse.ArgumentParser()
    dbg.add_args(ap)
    ap.add_argument("--xlsx", default=r"C:\DriveCatalog\orders\CAT-WO-03_Applicability.xlsx")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    url = dbg.checked_url(a.db_url_file, a.release)
    ws = openpyxl.load_workbook(a.xlsx, data_only=True, read_only=True)["Applicability"]
    it = ws.iter_rows(values_only=True)
    hdr = [str(h).strip() if h is not None else "" for h in next(it)]
    missing = [c for c in NEED if c not in hdr]
    if missing:
        sys.exit(f"REFUSED: the Applicability sheet lacks column(s) {missing}")
    rows = [dict(zip(hdr, v)) for v in it]
    load, skipped = parse_rows(rows)
    with psycopg.connect(url) as con, con.cursor() as cur:
        ents = {r[0] for r in cur.execute("SELECT entity_code FROM ref.entity")}
        subs = {r[0] for r in cur.execute("SELECT subtype_code FROM ref.doc_subtype")}
        bad = sorted({e for e, *_ in load if e not in ents}) + sorted({s for _, s, *_ in load if s not in subs})
        if bad:
            sys.exit(f"REFUSED: unknown entity / subtype code(s): {bad}")
        cur.executemany("""INSERT INTO ops.requirement_applicability (entity_code, subtype_code, required, note, ruled_by, ruled_at)
                           VALUES (%s, %s, %s, %s, 'ryan (CAT-WO-03 applicability workbook)', now())
                           ON CONFLICT (entity_code, subtype_code) DO UPDATE SET required = EXCLUDED.required, note = EXCLUDED.note,
                             ruled_by = EXCLUDED.ruled_by, ruled_at = now()""", load)
        by = collections.Counter((s, "yes" if r else "no") for _, s, r, _ in load)
        print(f"{'loaded' if a.apply else 'DRY RUN (rolled back)'}: {len(load)} rows; skipped (not Yes/No) {dict(skipped) or 0}")
        for s in sorted({s for s, _ in by}):
            print(f"  {s}: Yes {by[(s, 'yes')]} · No {by[(s, 'no')]}")
        if not a.apply:
            con.rollback()


if __name__ == "__main__":
    main()
