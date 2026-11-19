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

COMMIT;
