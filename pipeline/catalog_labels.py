"""
CAT-WO-02 · shared label logic for the nightly read-back (item 7.1), the re-sync (item 7.2) and item 0.

 - decode():          Drive labelInfo -> catalog codes (via labels_schema.json)
 - expected():        the values the MACHINE writes for a catalog row (same mapping as labels_sync.build_mods)
 - read_labels():     batched files.get(includeLabels) as the signed-in user, with retries; READ-ONLY
 - FIELDS / diff():   the per-field comparison used for drift, read-back and re-sync

Never prints or stores file names. Parties (L11) and Status / Issued date are used only when they exist in
labels_schema.json (i.e. after the labels are published); until then they are skipped, never guessed.
"""
import json, os, time, random, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "..", "src", "lib", "labels_schema.json")

# field key -> (label key, schema field key, kind)   kind: one | many | int | date | text
FIELDS = {
    "kind":               ("doc", "kind", "one"),
    "entities":           ("doc", "entity", "many"),
    "portcos":            ("doc", "portco", "many"),
    "fiscal_year":        ("doc", "fiscal_year", "int"),
    "period":             ("doc", "period", "one"),
    "effective_date":     ("doc", "effective_date", "date"),
    "workstream":         ("doc", "workstream", "one"),
    "issuer":             ("doc", "issuer", "one"),
    "stage":              ("exec", "stage", "one"),
    "executed_date":      ("exec", "executed_date", "date"),
    "status":             ("exec", "status", "one"),          # R-022 (after publish)
    "issued_date":        ("exec", "issued_date", "date"),    # R-022 (after publish)
    "issuing_entity":     ("parties", "issuing_entity", "one"),       # R-021 (after publish)
    "receiving_entities": ("parties", "receiving_entities", "many"),  # R-021 (after publish)
    "tier":               ("handling", "tier", "one"),
    "contains":           ("handling", "contains", "many"),
}
# Fields a person may own (Handling never: read-only in the app, and the machine keeps writing it).
PERSON_FIELDS = ["kind", "entities", "portcos", "fiscal_year", "period", "effective_date", "stage", "executed_date",
                 "status", "issued_date", "issuing_entity", "receiving_entities"]
RESYNC_FIELDS = PERSON_FIELDS + ["workstream", "issuer"]


def load_schema(path=SCHEMA_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Schema:
    def __init__(self, S):
        self.S = S
        self.label_ids = {k: v["label_id"] for k, v in S.items()}
        self.by_label_id = {v["label_id"]: k for k, v in S.items()}
        self.choice_code = {}  # (label, field, choice_id) -> code
        self.field_key = {}    # (label_id, field_id) -> (label, field)
        for lk, L in S.items():
            for fk, F in L["fields"].items():
                self.field_key[(L["label_id"], F["field_id"])] = (lk, fk)
                for code, cid in (F.get("choices") or {}).items():
                    self.choice_code[(lk, fk, cid)] = code

    def has(self, field):
        lk, fk, _ = FIELDS[field]
        return lk in self.S and fk in self.S[lk]["fields"]

    def active_fields(self, fields=None):
        return [f for f in (fields or FIELDS) if self.has(f)]

    def include_labels(self):
        return ",".join(self.label_ids.values())

    def decode(self, label_info):
        """labelInfo -> {field: value} plus review_status / reviewed_by_set / has_doc_label."""
        out = {f: ([] if FIELDS[f][2] == "many" else None) for f in FIELDS}
        out.update(review_status=None, reviewed_by_set=False, has_doc_label=False)
        for L in (label_info or {}).get("labels", []) or []:
            lk = self.by_label_id.get(L.get("id"))
            if not lk:
                continue
            if lk == "doc":
                out["has_doc_label"] = True
            for fid, fv in (L.get("fields") or {}).items():
                k = self.field_key.get((L["id"], fid))
                if not k:
                    continue
                _, fk = k
                sel = [self.choice_code.get((lk, fk, c), "?" + c) for c in (fv.get("selection") or [])]
                if lk == "review":
                    if fk == "status": out["review_status"] = sel[0] if sel else None
                    if fk == "reviewed_by": out["reviewed_by_set"] = bool(fv.get("user"))
                    continue
                for f, (flk, ffk, kind) in FIELDS.items():
                    if (flk, ffk) != (lk, fk):
                        continue
                    if kind == "one": out[f] = sel[0] if sel else None
                    elif kind == "many": out[f] = sorted(sel)
                    elif kind == "int": out[f] = int(fv["integer"][0]) if fv.get("integer") else None
                    elif kind == "date": out[f] = (fv.get("dateString") or [None])[0]
        return out


def _iso(v):
    if v is None: return None
    if isinstance(v, (datetime.date, datetime.datetime)): return v.isoformat()[:10]
    return str(v)[:10]


def expected(r, schema):
    """What the machine writes for one catalog row (dict with the labels_sync SQL columns + WO-02 columns).
    Mirrors labels_sync.build_mods exactly for the v1 fields, plus R-021/R-022 fields when published."""
    period = f"q{r['fq']}" if r.get("fq") else ("fy" if r.get("fye") else None)
    exec_on = bool(r.get("req_exec") and r.get("stage") and r.get("stage") != "unknown")
    e = {
        "kind": r.get("kind"), "entities": sorted(r.get("entities") or []), "portcos": sorted(r.get("portcos") or []),
        "fiscal_year": r.get("fiscal_year"), "period": period, "effective_date": _iso(r.get("eff")),
        "workstream": r.get("workstream"), "issuer": r.get("issuer"),
        "stage": r.get("stage") if exec_on else None,
        "executed_date": _iso(r.get("signed")) if exec_on and r.get("stage") == "fully_executed" else None,
        "status": r.get("status"), "issued_date": _iso(r.get("issued_date")),
        "issuing_entity": r.get("issuing_entity"), "receiving_entities": sorted(r.get("receiving_entities") or []),
        "tier": r.get("handling"), "contains": ["lp_pii"] if r.get("pii_lp") else [],
    }
    # a choice that does not exist on the published label cannot be written: the machine writes nothing for it
    for f, (lk, fk, kind) in FIELDS.items():
        if not schema.has(f):
            e[f] = [] if kind == "many" else None
            continue
        ch = schema.S[lk]["fields"][fk].get("choices")
        if ch is not None:
            if kind == "one" and e[f] is not None and e[f] not in ch: e[f] = None
            if kind == "many": e[f] = sorted(x for x in e[f] if x in ch)
    return e


def norm(v):
    if isinstance(v, list): return "|".join(sorted(str(x) for x in v))
    return "" if v is None else str(v)


def diff(a, b, fields):
    return [f for f in fields if norm(a.get(f)) != norm(b.get(f))]


# ------------------------------------------------------------------ Drive reads (batched, read-only)
def read_labels(svc, ids, include_labels, batch=100, on_progress=None, on_item=None):
    """{file_id: {'http': 200|404|..., 'labelInfo': {...}|None}}. Retries 429/5xx/rate-limit with backoff.
    With on_item(file_id, result) each result is handed over as its batch completes and NOT kept (memory stays
    flat on a full ~60k-file read-back); the return value is then empty."""
    out, todo, done = {}, list(ids), 0
    while todo:
        chunk, todo = todo[:batch], todo[batch:]
        retry = []

        def cb(req_id, resp, exc, _c=chunk):
            fid = _c[int(req_id)]
            if exc is None:
                out[fid] = {"http": 200, "labelInfo": resp.get("labelInfo")}
                return
            st = getattr(exc, "status_code", 0) or getattr(getattr(exc, "resp", None), "status", 0)
            if st in (429, 500, 502, 503) or (st == 403 and "rate" in str(exc).lower()):
                retry.append(fid)
            else:
                out[fid] = {"http": st or 0, "labelInfo": None}

        b = svc.new_batch_http_request(callback=cb)
        for i, fid in enumerate(chunk):
            b.add(svc.files().get(fileId=fid, fields="id,labelInfo", includeLabels=include_labels, supportsAllDrives=True), request_id=str(i))
        for attempt in range(6):
            try:
                b.execute(); break
            except Exception:
                time.sleep(2 ** attempt + random.random())
        else:
            for fid in chunk:
                out.setdefault(fid, {"http": 0, "labelInfo": None})
        if on_item:
            for fid in chunk:
                if fid in out: on_item(fid, out.pop(fid))
        if retry:
            todo = retry + todo
            time.sleep(3 + random.random() * 3)
        done += len(chunk) - len(retry)
        if on_progress: on_progress(done, len(ids))
    return out


# ------------------------------------------------------------------ catalog rows (same columns as labels_sync.SQL)
CATALOG_SQL = """
SELECT f.file_id, f.handling, d.document_id,
       coalesce(d.kind_confirmed, d.kind_auto) AS kind,
       coalesce(d.fiscal_year_confirmed, d.fiscal_year_auto) AS fiscal_year,
       coalesce(d.fiscal_quarter_confirmed, d.fiscal_quarter_auto) AS fq,
       coalesce(d.fye_flag_confirmed, d.fye_flag_auto) AS fye,
       coalesce(d.effective_date_confirmed, d.effective_date_auto) AS eff,
       coalesce(d.signed_date_confirmed, d.signed_date_auto) AS signed,
       coalesce(d.workstream_confirmed, d.workstream_auto) AS workstream,
       coalesce(d.issuer_confirmed, d.issuer_auto) AS issuer,
       coalesce(d.requires_execution_confirmed, d.requires_execution_auto) AS req_exec,
       coalesce(d.execution_stage_confirmed, d.execution_stage_auto) AS stage,
       coalesce(d.pii_lp_flag_confirmed, d.pii_lp_flag_auto) AS pii_lp,
       coalesce(d.entities_confirmed, (SELECT array_agg(DISTINCT e.entity_code) FROM cat.v_file_entity e WHERE e.file_id=f.file_id)) AS entities,
       coalesce(d.portcos_confirmed, (SELECT array_agg(DISTINCT p.portco_code) FROM cat.v_file_portco p WHERE p.file_id=f.file_id)) AS portcos,
       coalesce(d.status_confirmed, d.status_auto) AS status,
       coalesce(d.issued_date_confirmed, d.issued_date_auto) AS issued_date,
       coalesce(d.issuing_entity_confirmed, d.issuing_entity_auto) AS issuing_entity,
       coalesce(d.receiving_entities_confirmed, d.receiving_entities_auto) AS receiving_entities,
       d.updated_at
FROM cat.file f
LEFT JOIN cat.file_document fd ON fd.file_id=f.file_id
LEFT JOIN cat.document d ON d.document_id=fd.document_id
WHERE f.file_id = ANY(%s)
"""
# Before migration 004 the WO-02 columns don't exist: the item-0 measurement uses this variant.
CATALOG_SQL_V1 = (CATALOG_SQL
    .replace("coalesce(d.entities_confirmed, (SELECT", "((SELECT").replace("e.file_id=f.file_id)) AS entities", "e.file_id=f.file_id)) AS entities")
    .replace("coalesce(d.portcos_confirmed, (SELECT", "((SELECT").replace("p.file_id=f.file_id)) AS portcos", "p.file_id=f.file_id)) AS portcos")
    .replace("coalesce(d.status_confirmed, d.status_auto)", "NULL::text")
    .replace("coalesce(d.issued_date_confirmed, d.issued_date_auto)", "NULL::date")
    .replace("coalesce(d.issuing_entity_confirmed, d.issuing_entity_auto)", "NULL::text")
    .replace("coalesce(d.receiving_entities_confirmed, d.receiving_entities_auto)", "NULL::text[]"))


def catalog_rows(cur, ids, v1=False):
    cur.execute(CATALOG_SQL_V1 if v1 else CATALOG_SQL, (list(ids),))
    cols = [c.name for c in cur.description]
    return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


def drive_service(token_file, scopes):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    c = Credentials.from_authorized_user_file(token_file, scopes)
    if not c.valid:
        c.refresh(Request())   # in memory only: the token file is never rewritten by this module
    return build("drive", "v3", credentials=c, cache_discovery=False)
