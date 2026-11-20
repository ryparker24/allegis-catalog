-- CAT-WO-04 · version linking (R-027 L6 Version, R-028 amendments are not supersessions, R-029 "Current versions only"
-- off by default). Families group DOCUMENTS (byte-identical copies are already one document); the family build runs
-- inside derive (pipeline/families_wo04.py). Codes and IDs only. Idempotent.
BEGIN;

-- ------------------------------------------------------------------ the version-token list (data, versioned)
CREATE TABLE IF NOT EXISTS ops.version_token (
  token_id  text NOT NULL CHECK (token_id ~ '^VT-[A-Za-z0-9-]{1,30}$'),
  version   integer NOT NULL DEFAULT 1,
  pattern   text NOT NULL,
  marker    text CHECK (marker IS NULL OR marker IN ('draft', 'redline', 'executed')),
  seq       integer NOT NULL,
  active    boolean NOT NULL DEFAULT true,
  notes     text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (token_id, version)
);
REVOKE ALL ON ops.version_token FROM PUBLIC;
INSERT INTO ops.version_token (token_id, version, pattern, marker, seq, active) VALUES
  ('VT-copy-of', 1, '^\s*copy of\s+', NULL, 1, true),
  ('VT-copy', 1, '(?<![a-z])copy(?![a-z])(\s*\(?\d{1,2}\)?)?', NULL, 2, true),
  ('VT-paren-n', 1, '\(\s*\d{1,2}\s*\)', NULL, 3, true),
  ('VT-fully-exec', 1, '(?<![a-z])fully[\s_-]*executed(?![a-z])', 'executed', 4, true),
  ('VT-executed', 1, '(?<![a-z])(executed|execution version)(?![a-z])', 'executed', 5, true),
  ('VT-signed', 1, '(?<![a-z])(signed|countersigned|counter-signed)(?![a-z])', 'executed', 6, true),
  ('VT-docusign', 1, '(?<![a-z])docu[\s_-]?sign(ed)?(?![a-z])', 'executed', 7, true),
  ('VT-redline', 1, '(?<![a-z])(red[\s_-]?lined?|black[\s_-]?lined?|compare|comparison|markup|marked[\s_-]?up|mark[\s_-]?up)(?![a-z])', 'redline', 8, true),
  ('VT-draft', 1, '(?<![a-z])drafts?(?![a-z])', 'draft', 9, true),
  ('VT-final', 1, '(?<![a-z])final(?![a-z])', NULL, 10, true),
  ('VT-clean', 1, '(?<![a-z])clean(?![a-z])', NULL, 11, true),
  ('VT-vN', 1, '(?<![a-z0-9])v(er(sion)?)?[\s_.-]?\d{1,3}([._]\d{1,2})?(?![0-9])', NULL, 12, true),
  ('VT-revN', 1, '(?<![a-z])rev(ision|ised)?(?![a-z])[\s_.-]?\d{0,3}', NULL, 13, true),
  ('VT-initials', 1, '[\[(]\s*[a-z]{2,4}(\s*[,/&]\s*[a-z]{2,4})*\s*(comments?|edits?)?\s*[\])]', NULL, 14, true),
  ('VT-comments', 1, '(?<![a-z])(with |w[/ ])?(\w+ )?(comments?|edits?|changes)(?![a-z])', 'redline', 15, true),
  ('VT-corrected', 1, '(?<![a-z])(corrected|amended)(?![a-z])(?!\s*(and|&)\s*restated)', NULL, 16, true),
  ('VT-date-ymd', 1, '(?<!\d)(19|20)\d{2}[\s._-]?(0?[1-9]|1[0-2])[\s._-]?(0?[1-9]|[12]\d|3[01])(?!\d)', NULL, 17, true),
  ('VT-date-mdy', 1, '(?<!\d)(0?[1-9]|1[0-2])[\s._/-](0?[1-9]|[12]\d|3[01])[\s._/-]((19|20)?\d{2})(?!\d)', NULL, 18, true),
  ('VT-date-text', 1, '(?<![a-z])(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{1,2}(st|nd|rd|th)?,?\s*((19|20)\d{2})?(?!\d)', NULL, 19, true),
  ('VT-date-6', 1, '(?<!\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])([0-2]\d)(?!\d)', NULL, 20, true)
ON CONFLICT (token_id, version) DO UPDATE SET seq = EXCLUDED.seq
  WHERE ops.version_token.pattern = EXCLUDED.pattern;

-- ------------------------------------------------------------------ families
CREATE TABLE IF NOT EXISTS cat.doc_family (
  family_id           bigserial PRIMARY KEY,
  method              text NOT NULL CHECK (method IN ('rule', 'person')),
  confidence          text NOT NULL CHECK (confidence IN ('high', 'medium', 'person')),
  reason              text[] NOT NULL DEFAULT '{}',          -- which keys matched (codes: stem, kind, entities, ...)
  current_document_id bigint REFERENCES cat.document (document_id) ON DELETE SET NULL,
  n_members           integer NOT NULL DEFAULT 0,
  reviewed_by         text CHECK (reviewed_by IS NULL OR reviewed_by ~ '^[a-z0-9._%+-]{1,64}@allegiscapital\.com$'),
  reviewed_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON cat.doc_family FROM PUBLIC;

CREATE TABLE IF NOT EXISTS cat.doc_family_member (
  document_id    bigint PRIMARY KEY REFERENCES cat.document (document_id) ON DELETE CASCADE,
  family_id      bigint REFERENCES cat.doc_family (family_id) ON DELETE CASCADE,   -- NULL: a person took it out of every family
  role           text CHECK (role IS NULL OR role IN ('current', 'superseded', 'amends', 'redline', 'draft_of')),
  supersedes     bigint,                                  -- the catalog ID (document) this one is superseded by
  amends         bigint,                                  -- R-028: the base document an amendment adds to
  method         text NOT NULL CHECK (method IN ('rule', 'person')),
  confidence     text CHECK (confidence IS NULL OR confidence IN ('high', 'medium', 'person')),
  person_set     boolean NOT NULL DEFAULT false,          -- never changed by the nightly run
  person_current boolean NOT NULL DEFAULT false,
  set_by         text CHECK (set_by IS NULL OR set_by ~ '^[a-z0-9._%+-]{1,64}@allegiscapital\.com$'),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (family_id IS NOT NULL OR person_set),
  CHECK (NOT person_current OR role = 'current')
);
CREATE INDEX IF NOT EXISTS doc_family_member_family ON cat.doc_family_member (family_id);
REVOKE ALL ON cat.doc_family_member FROM PUBLIC;

-- a machine Status of Superseded set by the family build (status_rule VF-superseded) is the only status_auto this
-- order writes; status_confirmed (a person's) is never touched
ALTER TABLE app.review_event DROP CONSTRAINT IF EXISTS review_event_source;
ALTER TABLE app.review_event ADD CONSTRAINT review_event_source
  CHECK (source IN ('review', 'find_single', 'find_bulk', 'review_edit', 'match_subject', 'checklist_link', 'version_link'));

-- picking the current member (order: 1 person, 2 fully executed, 3 issued, 4 final, 5 partially executed,
-- 6 final not signed, 7 in review, 8 draft; nothing known sits between in review and draft); lower is better
CREATE OR REPLACE FUNCTION ops.version_rank(stage text, status text) RETURNS integer
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN stage = 'fully_executed' THEN 1 WHEN status = 'issued' THEN 2 WHEN status = 'final' THEN 3
              WHEN stage = 'partially_executed' THEN 4 WHEN stage = 'final_unexecuted' THEN 5 WHEN status = 'in_review' THEN 6
              WHEN status = 'draft' OR stage = 'draft' THEN 8 ELSE 7 END $$;

CREATE OR REPLACE FUNCTION ops.family_recount(fid bigint) RETURNS void
LANGUAGE sql SET search_path = pg_catalog, pg_temp AS $$
  UPDATE cat.doc_family f SET n_members = (SELECT count(*) FROM cat.doc_family_member m WHERE m.family_id = f.family_id),
         current_document_id = coalesce((SELECT m.document_id FROM cat.doc_family_member m WHERE m.family_id = f.family_id
                                          AND m.role = 'current' ORDER BY m.person_current DESC, m.document_id LIMIT 1), f.current_document_id),
         updated_at = now()
   WHERE f.family_id = fid $$;
REVOKE ALL ON FUNCTION ops.family_recount(bigint) FROM PUBLIC;

-- ------------------------------------------------------------------ person actions (side panel, Find merge, Review lane)
-- The app records each action as an app.review_event (source version_link, edits.version = {action, ...}); this
-- trigger applies it at once as PERSON-SET rows the nightly run never changes. catalog_app gains no privilege: it
-- still only INSERTs events. Actions:
--   mark_current {document}          the document becomes its family's current member (others: superseded by it)
--   remove       {document}          out of its family, and never grouped again
--   move         {document, family}  into another family, superseded by that family's current member
--   amends       {document, base}    R-028: an amendment of base (stays current alongside it)
--   merge        {documents[]}       one new family; current = best Stage / Status, then latest date
--   accept       {family}            a proposed (medium) family is right as it stands
--   split        {family, documents[]} those members leave (a new family when 2 or more)
CREATE OR REPLACE FUNCTION app.tg_review_event_version() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  v jsonb := coalesce(NEW.edits, '{}'::jsonb)->'version';
  act text := v->>'action';
  who text := lower(NEW.reviewer_email);
  doc bigint := nullif(v->>'document', '')::bigint;
  fid bigint;
  tgt bigint;
  cur bigint;
  docs bigint[];
  old_fams bigint[];
BEGIN
  IF NEW.source <> 'version_link' OR v IS NULL OR act IS NULL THEN RETURN NEW; END IF;
  IF who !~ '^[a-z0-9._%+-]{1,64}@allegiscapital\.com$' THEN who := NULL; END IF;
  BEGIN
  IF act IN ('mark_current', 'remove', 'move', 'amends') AND doc IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'check_violation', MESSAGE = 'version action without a document';
  END IF;
  SELECT family_id INTO fid FROM cat.doc_family_member WHERE document_id = doc;

  IF act = 'mark_current' THEN
    IF fid IS NULL THEN RAISE EXCEPTION USING ERRCODE = 'check_violation', MESSAGE = 'not in a family'; END IF;
    -- the whole family is frozen as the person now sees it
    UPDATE cat.doc_family_member SET person_set = true, method = 'person', person_current = false, set_by = coalesce(set_by, who),
           role = CASE WHEN role = 'current' THEN 'superseded' ELSE role END,
           supersedes = CASE WHEN role IN ('current', 'superseded', 'redline', 'draft_of') THEN doc ELSE supersedes END,
           updated_at = now()
     WHERE family_id = fid AND document_id <> doc AND role IS DISTINCT FROM 'amends';
    UPDATE cat.doc_family_member SET person_set = true, method = 'person', person_current = true, role = 'current',
           supersedes = NULL, set_by = who, updated_at = now() WHERE document_id = doc;
    UPDATE cat.doc_family SET confidence = 'person', method = 'person', current_document_id = doc, reviewed_by = who,
           reviewed_at = now(), updated_at = now() WHERE family_id = fid;

  ELSIF act = 'remove' THEN
    UPDATE cat.doc_family_member SET family_id = NULL, role = NULL, supersedes = NULL, amends = NULL, person_set = true,
           person_current = false, method = 'person', set_by = who, updated_at = now() WHERE document_id = doc;
    INSERT INTO cat.doc_family_member (document_id, family_id, method, person_set, set_by)
    VALUES (doc, NULL, 'person', true, who) ON CONFLICT (document_id) DO NOTHING;

  ELSIF act = 'move' THEN
    tgt := (v->>'family')::bigint;
    SELECT current_document_id INTO cur FROM cat.doc_family WHERE family_id = tgt;
    IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'check_violation', MESSAGE = 'no such family'; END IF;
    INSERT INTO cat.doc_family_member (document_id, family_id, role, supersedes, method, confidence, person_set, set_by)
    VALUES (doc, tgt, 'superseded', cur, 'person', 'person', true, who)
    ON CONFLICT (document_id) DO UPDATE SET family_id = tgt, role = 'superseded', supersedes = cur, amends = NULL,
       method = 'person', confidence = 'person', person_set = true, person_current = false, set_by = who, updated_at = now();
    UPDATE cat.doc_family SET confidence = 'person', method = 'person', reviewed_by = who, reviewed_at = now() WHERE family_id = tgt;
    PERFORM ops.family_recount(tgt);

  ELSIF act = 'amends' THEN
    tgt := (v->>'base')::bigint;
    IF tgt IS NULL OR tgt = doc OR NOT EXISTS (SELECT 1 FROM cat.document WHERE document_id = tgt) THEN
      RAISE EXCEPTION USING ERRCODE = 'check_violation', MESSAGE = 'no such base document';
    END IF;
    IF fid IS NULL THEN   -- an amendment on its own gets its own (person) family
      INSERT INTO cat.doc_family (method, confidence, current_document_id, reviewed_by, reviewed_at)
      VALUES ('person', 'person', doc, who, now()) RETURNING family_id INTO fid;
    END IF;
    INSERT INTO cat.doc_family_member (document_id, family_id, role, amends, method, confidence, person_set, person_current, set_by)
    VALUES (doc, fid, 'amends', tgt, 'person', 'person', true, false, who)
    ON CONFLICT (document_id) DO UPDATE SET family_id = fid, role = 'amends', amends = tgt, supersedes = NULL,
       method = 'person', person_set = true, person_current = false, set_by = who, updated_at = now();

  ELSIF act IN ('merge', 'split') THEN
    docs := ARRAY(SELECT DISTINCT x::bigint FROM jsonb_array_elements_text(coalesce(v->'documents', '[]'::jsonb)) x);
    IF act = 'split' THEN
      fid := (v->>'family')::bigint;
      docs := ARRAY(SELECT document_id FROM cat.doc_family_member WHERE family_id = fid AND document_id = ANY(docs));
      -- the members that stay are reviewed too (frozen as the person left them)
      UPDATE cat.doc_family_member SET person_set = true, method = 'person', set_by = coalesce(set_by, who), updated_at = now()
       WHERE family_id = fid AND NOT (document_id = ANY(docs));
      UPDATE cat.doc_family SET confidence = 'person', method = 'person', reviewed_by = who, reviewed_at = now() WHERE family_id = fid;
    END IF;
    IF cardinality(docs) = 1 AND act = 'split' THEN
      UPDATE cat.doc_family_member SET family_id = NULL, role = NULL, supersedes = NULL, amends = NULL, person_set = true,
             person_current = false, method = 'person', set_by = who, updated_at = now() WHERE document_id = docs[1];
    ELSIF cardinality(docs) >= 2 THEN
      old_fams := ARRAY(SELECT DISTINCT family_id FROM cat.doc_family_member WHERE document_id = ANY(docs) AND family_id IS NOT NULL);
      SELECT d.document_id INTO cur FROM cat.document d WHERE d.document_id = ANY(docs)
       ORDER BY ops.version_rank(coalesce(d.execution_stage_confirmed, d.execution_stage_auto), coalesce(d.status_confirmed, d.status_auto)),
                coalesce(d.effective_date_confirmed, d.effective_date_auto) DESC NULLS LAST, d.updated_at DESC, d.document_id LIMIT 1;
      INSERT INTO cat.doc_family (method, confidence, current_document_id, reviewed_by, reviewed_at)
      VALUES ('person', 'person', cur, who, now()) RETURNING family_id INTO tgt;
      INSERT INTO cat.doc_family_member (document_id, family_id, role, supersedes, method, confidence, person_set, person_current, set_by)
      SELECT x, tgt, CASE WHEN x = cur THEN 'current' ELSE 'superseded' END, CASE WHEN x = cur THEN NULL ELSE cur END,
             'person', 'person', true, false, who FROM unnest(docs) x
      ON CONFLICT (document_id) DO UPDATE SET family_id = EXCLUDED.family_id, role = EXCLUDED.role, supersedes = EXCLUDED.supersedes,
         amends = NULL, method = 'person', confidence = 'person', person_set = true, person_current = false, set_by = who, updated_at = now();
      PERFORM ops.family_recount(f) FROM unnest(old_fams) f;
      fid := tgt;
    END IF;

  ELSIF act = 'accept' THEN
    fid := (v->>'family')::bigint;
    UPDATE cat.doc_family_member SET person_set = true, method = 'person', confidence = 'person', set_by = coalesce(set_by, who), updated_at = now()
     WHERE family_id = fid;
    UPDATE cat.doc_family SET confidence = 'person', method = 'person', reviewed_by = who, reviewed_at = now(), updated_at = now() WHERE family_id = fid;
  ELSE
    RAISE EXCEPTION USING ERRCODE = 'check_violation', MESSAGE = 'unknown version action';
  END IF;

  -- Status follows the roles at once (machine Status only; a person's Status always wins in the views)
  UPDATE cat.document d SET status_auto = 'superseded', status_rule = 'VF-superseded', updated_at = now()
    FROM cat.doc_family_member m JOIN cat.doc_family f ON f.family_id = m.family_id
   WHERE m.document_id = d.document_id AND m.family_id IN (fid, tgt) AND m.role IN ('superseded', 'redline', 'draft_of')
     AND f.confidence IN ('high', 'person') AND d.status_confirmed IS NULL AND d.status_auto IS DISTINCT FROM 'superseded';
  UPDATE cat.document d SET status_auto = NULL, status_rule = NULL, updated_at = now()
    FROM cat.doc_family_member m
   WHERE m.document_id = d.document_id AND (m.family_id IN (fid, tgt) OR m.document_id = doc OR m.document_id = ANY(coalesce(docs, '{}')))
     AND (m.role IS NULL OR m.role IN ('current', 'amends')) AND d.status_rule = 'VF-superseded';
  IF fid IS NOT NULL THEN PERFORM ops.family_recount(fid); END IF;
  IF tgt IS NOT NULL AND tgt IS DISTINCT FROM fid THEN PERFORM ops.family_recount(tgt); END IF;
  EXCEPTION WHEN check_violation OR invalid_text_representation OR numeric_value_out_of_range OR foreign_key_violation THEN
    RAISE WARNING 'review_event_version: event % not applied (%)', NEW.event_id, SQLSTATE;
  END;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION app.tg_review_event_version() FROM PUBLIC;
DROP TRIGGER IF EXISTS review_event_version ON app.review_event;
CREATE TRIGGER review_event_version AFTER INSERT ON app.review_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_review_event_version();

-- ------------------------------------------------------------------ views
-- Find: version role (applied families only: high or person-reviewed; a medium family is a proposal in Review),
-- the family and its size
CREATE OR REPLACE VIEW app.v_find_x WITH (security_barrier = true) AS
 SELECT v.file_id, v.document_id, v.web_view_link, v.mime_type, v.file_type_family, v.modified_time, v.tier, v.kind,
    v.fiscal_year, v.period, v.effective_date, v.workstream, v.issuer, v.requires_execution, v.stage, v.signed_date, v.pii_lp,
    COALESCE(d.entities_confirmed, v.entities) AS entities,
    COALESCE(d.portcos_confirmed, v.portcos) AS portcos,
    v.is_primary, v.confidence, v.stage_suggested, v.signals, v.reviewed,
    COALESCE(d.issuing_entity_confirmed, d.issuing_entity_auto) AS issuing_entity,
    COALESCE(d.receiving_entities_confirmed, d.receiving_entities_auto, '{}'::text[]) AS receiving_entities,
    COALESCE(d.status_confirmed, d.status_auto) AS status,
    COALESCE(d.issued_date_confirmed, d.issued_date_auto) AS issued_date,
    COALESCE(d.subject_codes_confirmed, d.subject_codes_auto, '{}'::text[]) AS subject_codes,
    COALESCE(d.subject_person_confirmed, d.subject_person_auto) AS subject_person,
    array_to_string(COALESCE(dl.path_segments, fo.path_segments), ' › ') AS location,
    COALESCE(dl.folder_id, fo.parent_ids[1]) AS location_folder_id,
    GREATEST(COALESCE(dl.n_folders, 1) - 1, 0) AS other_locations,
    CASE WHEN fam.confidence IN ('high', 'person') THEN fm.family_id END AS family_id,
    CASE WHEN fam.confidence IN ('high', 'person') THEN fm.role END AS version_role,
    CASE WHEN fam.confidence IN ('high', 'person') THEN fam.n_members END AS versions
   FROM app.v_find v
     LEFT JOIN cat.document d ON d.document_id = v.document_id
     LEFT JOIN cat.document_location dl ON dl.document_id = v.document_id
     LEFT JOIN cat.file fo ON fo.file_id = v.file_id
     LEFT JOIN cat.doc_family_member fm ON fm.document_id = v.document_id
     LEFT JOIN cat.doc_family fam ON fam.family_id = fm.family_id;

-- every member of a family, with the copy to open (its primary live copy) for the side-panel timeline; the app shows a
-- member only after a live access check as the user (R-020) and counts the rest
CREATE OR REPLACE VIEW app.v_family_member WITH (security_barrier = true) AS
 SELECT m.family_id, f.confidence AS family_confidence, f.reason AS family_reason, f.current_document_id,
        m.document_id, m.role, m.supersedes, m.amends, m.person_set, m.person_current,
        coalesce(d.kind_confirmed, d.kind_auto) AS kind,
        coalesce(d.execution_stage_confirmed, d.execution_stage_auto) AS stage,
        coalesce(d.status_confirmed, d.status_auto) AS status,
        coalesce(d.effective_date_confirmed, d.effective_date_auto) AS effective_date,
        coalesce(d.fiscal_year_confirmed, d.fiscal_year_auto) AS fiscal_year,
        p.file_id, p.web_view_link, p.modified_time
   FROM cat.doc_family_member m
   JOIN cat.doc_family f ON f.family_id = m.family_id
   JOIN cat.document d ON d.document_id = m.document_id
   LEFT JOIN LATERAL (
     SELECT fi.file_id, fi.web_view_link, fi.modified_time FROM cat.file_document fd JOIN cat.file fi ON fi.file_id = fd.file_id
      WHERE fd.document_id = m.document_id AND fi.removed_run IS NULL AND fi.trashed IS NOT TRUE AND fi.is_shortcut IS NOT TRUE
        AND COALESCE(fi.handling, 'secret') <> 'secret'
      ORDER BY (fd.file_role = 'primary') DESC, fi.drive_id IS NOT NULL DESC, fi.file_id LIMIT 1) p ON true;

-- the Review lane "Link versions": proposed (medium) families, not yet reviewed
CREATE OR REPLACE VIEW app.v_link_versions WITH (security_barrier = true) AS
 SELECT f.family_id, f.reason, f.n_members, f.current_document_id, f.updated_at
   FROM cat.doc_family f WHERE f.confidence = 'medium';

REVOKE ALL ON app.v_family_member, app.v_link_versions FROM PUBLIC;
GRANT SELECT ON app.v_find_x, app.v_family_member, app.v_link_versions TO catalog_app;
COMMIT;
