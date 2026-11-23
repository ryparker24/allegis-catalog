"""CAT-WO-06.1 · labelling new files in the labelled scope (offline; invented IDs only)."""
import datetime, inspect, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_labels as cl
import label_new_wo061 as ln

R = []
def check(name, cond, detail=""):
    R.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + (f"  -- {detail}" if detail and not cond else ""))

S = cl.Schema(cl.load_schema())
row = dict(file_id="1AbCdEfGhIjKlMnOpQ", handling="normal", document_id=4242, kind="capital_statement", fiscal_year=2025, fq=4, fye=False,
           eff=datetime.date(2025, 12, 31), signed=None, workstream=None, issuer=None, req_exec=False, stage="n_a", pii_lp=True,
           entities=["CIP-II"], portcos=None, status="final", issued_date=None, issuing_entity=None, receiving_entities=None,
           subject_codes=["LP-0101"], subject_person=None, personnel=None, version_family=None, version_role=None,
           version_supersedes=None, version_amends=None, published_channels=None, published_date=None, published_ids=None,
           content_flags=["tax_id"])
mods, fields = ln.full_mods(row, S)
blob = json.dumps(mods)
lid = {k: v["label_id"] for k, v in S.S.items()}
labels = {m["labelId"] for m in mods}
check("full label set: Allegis Document, Handling and Catalog Review are applied (with the catalog values)",
      {lid["doc"], lid["handling"], lid["review"]} <= labels and {"kind", "entities", "fiscal_year", "period", "status", "subject_codes"} <= set(fields), str(fields))
check("Catalog ID = the catalog document id; Catalog Review = Needs review",
      '"4242"' in blob and S.S["review"]["fields"]["status"]["choices"]["needs_review"] in blob)
check("dates are RFC 3339 strings (CAT-WO-03.2)", '"2025-12-31"' in blob and '"year"' not in blob)
check("never an unset on a new file (only values the catalog has)", "unsetValues" not in blob)
H = S.S["handling"]["fields"]
check("Handling: tier from the catalog + Contains LP PII / Tax ID (R-037)",
      H["tier"]["choices"]["normal"] in blob and H["contains"]["choices"]["lp_pii"] in blob and H["contains"]["choices"]["tax_id"] in blob)
m2, f2 = ln.full_mods(dict(row, handling="secret"), S)
check("Secret tier is never labelled", m2 is None and f2 == [])
src = inspect.getsource(ln)
check("scope excludes Secret, noise, shortcuts, trashed, removed and already-labelled files",
      all(x in ln.SCOPE_SQL for x in ("<> 'secret'", "noise_flag IS NOT TRUE", "is_shortcut IS NOT TRUE", "trashed IS NOT TRUE",
                                       "removed_run IS NULL", "app.labelled_file")))
check("a file that already carries any catalog label is skipped (read live right before writing)",
      "already_carries_a_label" in src and "read_labels(svc, seg" in inspect.getsource(ln.run))
check("streamed: batches of 25 files, segments of 500 rows", ln.BATCH == 25 and "range(0, len(ids), 500)" in inspect.getsource(ln.run))
check("logs counts and codes only (no file name is ever selected)", "f.name" not in ln.SCOPE_SQL and not re.search(r"log\(f?[\"'][^\n]*\{[^}]*(?<!__)name(?!__)", src))
check("a Drive failure never stops the nightly", "label NOT run" in inspect.getsource(ln.nightly_step))

print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
