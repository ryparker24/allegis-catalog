-- CAT-WO-03.1 (Ryan found it live, 2026-11-18): an app edit wrote the Drive label but not the catalog value that
-- filters and sort use (cat.document.*_confirmed was only set by the NEXT nightly read-back), so a filter said
-- "issued: 1" while the column (live from Drive) showed many Issued.
--
-- Fix: when the app records a SUCCESSFUL label write (app.review_event with labels_written), the same INSERT applies
-- the written values to the document's *_confirmed columns at once - as person-set, exactly as the read-back would.
-- catalog_app gains NO privilege: it still only INSERTs app.review_event; this trigger runs as the owner and touches
-- only the columns the event names. Idempotent.
BEGIN;

CREATE OR REPLACE FUNCTION app.tg_review_event_apply() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
  e jsonb := coalesce(NEW.edits, '{}'::jsonb);
  st text;
  arr text[];
BEGIN
  -- only a write Drive accepted (labels_written non-empty) on a catalogued document; a Subject decision recorded
  -- while its field was unpublished (labels_written = {}) stays with the nightly subject step
  IF NEW.document_id IS NULL OR coalesce(cardinality(NEW.labels_written), 0) = 0 THEN
    RETURN NEW;
  END IF;
  -- the audit event must always land (Drive is already written): a value the catalog refuses is left to the read-back
  BEGIN

  -- Allegis Document
  IF e ? 'kind' THEN
    UPDATE cat.document SET kind_confirmed = e->>'kind', updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'entities' THEN
    arr := CASE WHEN jsonb_typeof(e->'entities') = 'array' THEN ARRAY(SELECT jsonb_array_elements_text(e->'entities') ORDER BY 1) END;
    UPDATE cat.document SET entities_confirmed = nullif(arr, '{}'), updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'portcos' THEN
    arr := CASE WHEN jsonb_typeof(e->'portcos') = 'array' THEN ARRAY(SELECT jsonb_array_elements_text(e->'portcos') ORDER BY 1) END;
    UPDATE cat.document SET portcos_confirmed = nullif(arr, '{}'), updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'fiscal_year' THEN
    UPDATE cat.document SET fiscal_year_confirmed = (e->>'fiscal_year')::int, updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'period' THEN   -- same split as the read-back (label_sync_wo02.confirm_updates); month / as_of: label only
    IF e->>'period' IN ('q1', 'q2', 'q3', 'q4') THEN
      UPDATE cat.document SET fiscal_quarter_confirmed = substr(e->>'period', 2)::smallint, fye_flag_confirmed = false, updated_at = now()
       WHERE document_id = NEW.document_id;
    ELSIF e->>'period' = 'fy' THEN
      UPDATE cat.document SET fiscal_quarter_confirmed = NULL, fye_flag_confirmed = true, updated_at = now() WHERE document_id = NEW.document_id;
    END IF;
  END IF;
  IF e ? 'effective_date' THEN
    UPDATE cat.document SET effective_date_confirmed = (e->>'effective_date')::date, updated_at = now() WHERE document_id = NEW.document_id;
  END IF;

  -- Parties
  IF e ? 'issuing_entity' THEN
    UPDATE cat.document SET issuing_entity_confirmed = e->>'issuing_entity', updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'receiving_entities' THEN
    arr := CASE WHEN jsonb_typeof(e->'receiving_entities') = 'array' THEN ARRAY(SELECT jsonb_array_elements_text(e->'receiving_entities') ORDER BY 1) END;
    UPDATE cat.document SET receiving_entities_confirmed = nullif(arr, '{}'), updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'subject_codes' THEN   -- R-026: [] is a person's "none" and stays '{}' (NULL would let machine codes back)
    arr := CASE WHEN jsonb_typeof(e->'subject_codes') = 'array' THEN ARRAY(SELECT jsonb_array_elements_text(e->'subject_codes') ORDER BY 1) END;
    UPDATE cat.document SET subject_codes_confirmed = arr, updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'subject_person' THEN
    UPDATE cat.document SET subject_person_confirmed = e->>'subject_person', updated_at = now() WHERE document_id = NEW.document_id;
  END IF;

  -- Status & Execution: Status / Issued date from edits; Stage / Executed date from edits (Find) or the event's own
  -- stage / executed_date columns (the Review form)
  IF e ? 'status' THEN
    UPDATE cat.document SET status_confirmed = e->>'status', updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'issued_date' THEN
    UPDATE cat.document SET issued_date_confirmed = (e->>'issued_date')::date, updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  st := CASE WHEN e ? 'stage' THEN e->>'stage' WHEN 'exec' = ANY(NEW.labels_written) THEN NEW.stage END;
  IF st IS NOT NULL OR e ? 'stage' THEN
    UPDATE cat.document SET execution_stage_confirmed = st, updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  IF e ? 'executed_date' THEN
    UPDATE cat.document SET signed_date_confirmed = (e->>'executed_date')::date, updated_at = now() WHERE document_id = NEW.document_id;
  ELSIF NEW.executed_date IS NOT NULL AND 'exec' = ANY(NEW.labels_written) THEN
    UPDATE cat.document SET signed_date_confirmed = NEW.executed_date, updated_at = now() WHERE document_id = NEW.document_id;
  ELSIF st IS NOT NULL AND st <> 'fully_executed' THEN   -- the write cleared a stale executed date on the label
    UPDATE cat.document SET signed_date_confirmed = NULL, updated_at = now() WHERE document_id = NEW.document_id;
  END IF;
  EXCEPTION WHEN check_violation OR invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow
                 OR numeric_value_out_of_range THEN
    RAISE WARNING 'review_event_apply: event % not applied to the catalog (%); the nightly read-back will', NEW.event_id, SQLSTATE;
  END;
  RETURN NEW;
END $$;

REVOKE ALL ON FUNCTION app.tg_review_event_apply() FROM PUBLIC;

DROP TRIGGER IF EXISTS review_event_apply ON app.review_event;
CREATE TRIGGER review_event_apply AFTER INSERT ON app.review_event
  FOR EACH ROW EXECUTE FUNCTION app.tg_review_event_apply();

-- a checklist row's "This is the one" now also writes the document's labels to match the requirement (source checklist_link)
ALTER TABLE app.review_event DROP CONSTRAINT IF EXISTS review_event_source;
ALTER TABLE app.review_event ADD CONSTRAINT review_event_source
  CHECK (source IN ('review', 'find_single', 'find_bulk', 'review_edit', 'match_subject', 'checklist_link'));

-- ------------------------------------------------------------------ Location (Ryan 2026-11-19)
-- drive › folder path of the document's PRIMARY copy (in scope: live, not secret), else the row's own file; the parent
-- folder id (link to Drive); how many OTHER folders hold a copy. From the crawl's own path data (refreshed nightly),
-- never a label. The app shows it only on rows that pass the live access check (as names); never logged.
-- precomputed per document (the crawl's path data changes only when the crawl runs): ops.refresh_document_location()
-- runs here and after every derive (pipeline/apply_derive_wo02.py), so Find pays a plain join, not a per-row lookup
CREATE TABLE IF NOT EXISTS cat.document_location (
  document_id   bigint PRIMARY KEY REFERENCES cat.document (document_id) ON DELETE CASCADE,
  path_segments text[] NOT NULL,
  folder_id     text,
  n_folders     integer NOT NULL,
  refreshed_at  timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON cat.document_location FROM PUBLIC;

CREATE OR REPLACE FUNCTION ops.refresh_document_location() RETURNS integer
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE n integer;
BEGIN
  DELETE FROM cat.document_location;
  WITH f AS (
    SELECT fd.document_id, fd.file_role, f.file_id, f.path_segments, f.parent_ids[1] AS folder_id
      FROM cat.file_document fd JOIN cat.file f ON f.file_id = fd.file_id
     WHERE f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE
       AND COALESCE(f.handling, 'secret') <> 'secret' AND f.path_segments IS NOT NULL),
  n AS (SELECT document_id, count(DISTINCT folder_id)::int AS n_folders FROM f GROUP BY document_id)
  INSERT INTO cat.document_location (document_id, path_segments, folder_id, n_folders)
  SELECT DISTINCT ON (f.document_id) f.document_id, f.path_segments, f.folder_id, n.n_folders
    FROM f JOIN n USING (document_id)
   ORDER BY f.document_id, (f.file_role = 'primary') DESC, f.file_id;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION ops.refresh_document_location() FROM PUBLIC;
SELECT ops.refresh_document_location();

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
    GREATEST(COALESCE(dl.n_folders, 1) - 1, 0) AS other_locations
   FROM app.v_find v
     LEFT JOIN cat.document d ON d.document_id = v.document_id
     LEFT JOIN cat.document_location dl ON dl.document_id = v.document_id
     LEFT JOIN cat.file fo ON fo.file_id = v.file_id;

-- the Review queue gets Location too (filter / sort / group); same body as 005, plus the precomputed path
CREATE OR REPLACE VIEW app.v_review_queue WITH (security_barrier = true) AS
 SELECT q.file_id, q.document_id, q.web_view_link, q.mime_type, q.file_type_family, q.modified_time, q.tier, q.kind, q.fiscal_year, q.period,
    q.effective_date, q.workstream, q.issuer, q.requires_execution, q.stage, q.signed_date, q.pii_lp, q.entities, q.portcos, q.is_primary,
    q.confidence, q.stage_suggested, q.signals, q.reviewed, q.queue_reason,
        CASE q.queue_reason
            WHEN 'stage_unknown'::text THEN 1
            WHEN 'low_confidence_executed'::text THEN 2
            WHEN 'no_kind'::text THEN 3
            WHEN 'match_subject'::text THEN 4
            ELSE 5
        END AS queue_rank,
        CASE q.confidence
            WHEN 'none'::text THEN 0
            WHEN 'low'::text THEN 1
            WHEN 'medium'::text THEN 2
            WHEN 'high'::text THEN 3
            ELSE 4
        END AS confidence_rank,
    q.status, q.subject_candidates,
    array_to_string(COALESCE(dl.path_segments, fo.path_segments), ' › ') AS location,
    COALESCE(dl.folder_id, fo.parent_ids[1]) AS location_folder_id,
    GREATEST(COALESCE(dl.n_folders, 1) - 1, 0) AS other_locations
   FROM ( SELECT v.file_id, v.document_id, v.web_view_link, v.mime_type, v.file_type_family, v.modified_time, v.tier, v.kind,
            v.fiscal_year, v.period, v.effective_date, v.workstream, v.issuer, v.requires_execution, v.stage, v.signed_date,
            v.pii_lp, v.entities, v.portcos, v.is_primary, v.confidence, v.stage_suggested, v.signals, v.reviewed,
            COALESCE(d.status_confirmed, d.status_auto) AS status,
            sc.partner_codes AS subject_candidates,
                CASE
                    WHEN NOT v.reviewed AND (v.requires_execution AND (v.stage = 'unknown'::text)) THEN 'stage_unknown'::text
                    WHEN NOT v.reviewed AND ((v.stage = 'fully_executed'::text) AND (v.confidence = 'low'::text)) THEN 'low_confidence_executed'::text
                    WHEN NOT v.reviewed AND (v.kind IS NULL) THEN 'no_kind'::text
                    -- Match subject does NOT depend on an earlier Confirm / Wrong review (coder review: files reviewed under
                    -- WO-01/02 must still reach it); only a Subject decision takes the file out of this lane
                    WHEN sc.document_id IS NOT NULL AND NOT EXISTS (
                         SELECT 1 FROM app.review_event m WHERE m.document_id = v.document_id AND m.source = 'match_subject') THEN 'match_subject'::text
                    WHEN NOT v.reviewed AND (NOT COALESCE(v.requires_execution, false) AND COALESCE(d.status_confirmed, d.status_auto) IS NULL) THEN 'status_unknown'::text
                    ELSE NULL::text
                END AS queue_reason
           FROM app.v_find v
           LEFT JOIN cat.document d ON d.document_id = v.document_id
           LEFT JOIN app.v_subject_candidates sc ON sc.document_id = v.document_id
          WHERE (NOT v.reviewed OR sc.document_id IS NOT NULL)) q
     LEFT JOIN cat.document_location dl ON dl.document_id = q.document_id
     LEFT JOIN cat.file fo ON fo.file_id = q.file_id
  WHERE (q.queue_reason IS NOT NULL);

-- every copy of a document (not secret, live) with its location: the side panel lists them AFTER a live check of each
-- copy as the user (a copy the user can't open is counted, never shown)
CREATE OR REPLACE VIEW app.v_document_location WITH (security_barrier = true) AS
 SELECT fd.document_id, f.file_id, fd.file_role = 'primary' AS is_primary,
        array_to_string(f.path_segments, ' › ') AS location, f.parent_ids[1] AS location_folder_id
   FROM cat.file_document fd JOIN cat.file f ON f.file_id = fd.file_id
  WHERE f.removed_run IS NULL AND f.trashed IS NOT TRUE AND f.is_shortcut IS NOT TRUE AND COALESCE(f.handling, 'secret') <> 'secret';
REVOKE ALL ON app.v_document_location FROM PUBLIC;
GRANT SELECT ON app.v_find_x, app.v_document_location TO catalog_app;

-- ------------------------------------------------------------------ audited financial statements (Ryan 2026-11-19)
-- CIP-I legal name ("Cyber Innovation Partners, L.P."), held since CAT-WO-02, turned on by Ryan for the audited FS:
-- never when the name / folder has "II", "III" or a standalone "2" anywhere (those are CIP-II). Same priority / multi
-- as ENT-020 (CIP-II spelled out).
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT CASE applies_to WHEN 'name' THEN 'ENT-027' ELSE 'ENT-027P' END, 1, 'entity', applies_to,
       '(?i)^(?!.*(\yII\y|\yIII\y|(?<![0-9])2(?![0-9]))).*\yCyber[^A-Za-z0-9]*Innovation[^A-Za-z0-9]*Partners\y',
       'CIP-I', priority, true, 'CAT-WO-03.1 (Ryan 2026-11-19): CIP-I legal name, never with II / III / 2', multi, false
FROM ops.decomposition_rule WHERE rule_id IN ('ENT-020', 'ENT-020P') AND version = 1
ON CONFLICT (rule_id, version) DO NOTHING;

-- AUD-01 accepts ONLY audited_financial_statements (Ryan); financial statements / an audit opinion stay candidates
INSERT INTO ref.doc_subtype_kind (subtype_code, kind, role, qualifier, ruled)
VALUES ('AUD-01', 'audited_financial_statements', 'satisfying', NULL, 'CAT-WO-03.1 (Ryan) 2026-11-19')
ON CONFLICT (subtype_code, kind) DO UPDATE SET role = 'satisfying', ruled = EXCLUDED.ruled;
UPDATE ref.doc_subtype_kind SET role = 'candidate', qualifier = 'not the audited statements (CAT-WO-03.1: AUD-01 accepts only audited_financial_statements)',
       ruled = 'CAT-WO-03.1 (Ryan) 2026-11-19'
WHERE subtype_code = 'AUD-01' AND kind = 'financial_statements' AND role <> 'candidate';

-- AUDITED-FS v2: audited_financial_statements only, an ANNUAL period (fiscal year or none, never a quarter), Final / Issued
INSERT INTO ops.requirement_rule (rule_id, version, checklist, subtype_code, no_datum_subtype, satisfying_kinds, subject_type,
                                  entity_filter, partner_filter, period_from, satisfied_when, active, notes)
SELECT rule_id, 2, checklist, subtype_code, no_datum_subtype, ARRAY['audited_financial_statements'], subject_type, entity_filter,
       partner_filter, period_from, '{"status": ["final", "issued"], "annual": true}'::jsonb, true,
       'v2 2026-11-19 (Ryan, CAT-WO-03.1): audited_financial_statements only, annual period. v1 kept for history.'
FROM ops.requirement_rule WHERE rule_id = 'AUDITED-FS' AND version = 1
ON CONFLICT (rule_id, version) DO NOTHING;

COMMIT;
