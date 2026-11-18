-- CAT-WO-02 Part 2 · 004_wo02_part2.sql   (run as the DB owner; idempotent; THROWAWAY BRANCH until release)
-- R-021 Parties, R-022 Status, item 7 read-back / re-sync state, item 8 app edits.
-- Codes only. Nothing here reads ref.lp or ref.person. LP-level receiving codes beyond 'LP' need Ryan's list.

BEGIN;

-- ---------------------------------------------------------------- document fields (auto = rules, confirmed = a person)
ALTER TABLE cat.document
    ADD COLUMN IF NOT EXISTS issuing_entity_auto          text,
    ADD COLUMN IF NOT EXISTS issuing_entity_confirmed     text,
    ADD COLUMN IF NOT EXISTS receiving_entities_auto      text[],
    ADD COLUMN IF NOT EXISTS receiving_entities_confirmed text[],
    ADD COLUMN IF NOT EXISTS parties_rule                 text,
    ADD COLUMN IF NOT EXISTS status_auto                  text,
    ADD COLUMN IF NOT EXISTS status_confirmed             text,
    ADD COLUMN IF NOT EXISTS status_rule                  text,
    ADD COLUMN IF NOT EXISTS issued_date_auto             date,
    ADD COLUMN IF NOT EXISTS issued_date_confirmed        date,
    ADD COLUMN IF NOT EXISTS entities_confirmed           text[],
    ADD COLUMN IF NOT EXISTS portcos_confirmed            text[];

-- NOT VALID + VALIDATE: the scan of ~200k rows runs without holding the table's exclusive lock (coder review)
DO $$ BEGIN
    ALTER TABLE cat.document ADD CONSTRAINT document_status_codes CHECK (
        coalesce(status_auto, 'draft') IN ('draft','in_review','final','issued','superseded') AND
        coalesce(status_confirmed, 'draft') IN ('draft','in_review','final','issued','superseded')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- R-021: Parties hold CODES only (entity / portco codes, 'LP', 'EXTERNAL'), never a name (CISO review)
DO $$ BEGIN
    ALTER TABLE cat.document ADD CONSTRAINT document_parties_codes CHECK (
        coalesce(issuing_entity_auto, 'X') ~ '^[A-Za-z0-9()_ -]{1,40}$' AND
        coalesce(issuing_entity_confirmed, 'X') ~ '^[A-Za-z0-9()_ -]{1,40}$' AND
        coalesce(array_to_string(receiving_entities_auto, ','), 'X') ~ '^[A-Za-z0-9()_ ,-]+$' AND
        coalesce(array_to_string(receiving_entities_confirmed, ','), 'X') ~ '^[A-Za-z0-9()_ ,-]+$' AND
        length(coalesce(array_to_string(receiving_entities_auto, ','), '')) <= 400 AND
        length(coalesce(array_to_string(receiving_entities_confirmed, ','), '')) <= 400) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE cat.document VALIDATE CONSTRAINT document_status_codes;
ALTER TABLE cat.document VALIDATE CONSTRAINT document_parties_codes;

-- ---------------------------------------------------------------- item 7 · label state per file (the read-back's memory)
-- machine = the values the machine last wrote. On first sight of a file it is seeded from the LIVE labels (the bulk
-- run wrote them; item 0.3 measured 0 drift), so stale catalog values are never mistaken for a person's edit.
-- live = what the last read-back saw on the file.
-- person_fields = fields a person owns (Catalog Review = Confirmed, or live differs from the machine write):
-- the re-sync never overwrites them.
CREATE TABLE IF NOT EXISTS ops.label_state (
    file_id         text PRIMARY KEY,
    machine         jsonb,
    machine_at      timestamptz,
    live            jsonb,
    live_at         timestamptz,
    review_status   text,
    reviewed_by_set boolean NOT NULL DEFAULT false,
    person_fields   text[]  NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ops.label_sync_run (
    run_id              text PRIMARY KEY,
    mode                text NOT NULL CHECK (mode IN ('readback', 'resync')),
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    applied             boolean NOT NULL DEFAULT false,
    files_read          integer NOT NULL DEFAULT 0,
    confirmed_by_person integer NOT NULL DEFAULT 0,
    resynced            integer NOT NULL DEFAULT 0,
    skipped_person      integer NOT NULL DEFAULT 0,
    errors              integer NOT NULL DEFAULT 0,
    by_field            jsonb,
    notes               text
);

-- ---------------------------------------------------------------- item 8 · app edits are recorded in the review log
ALTER TABLE app.review_event ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'review';
ALTER TABLE app.review_event ADD COLUMN IF NOT EXISTS edits  jsonb;
DO $$ BEGIN
    ALTER TABLE app.review_event ADD CONSTRAINT review_event_source CHECK (source IN ('review', 'find_single', 'find_bulk', 'review_edit'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- A bulk edit is 'edited': a person changed a field but did not review the file, so it must not take the file out
-- of the Review queue (only 'confirmed' / 'wrong' do; the queue view is updated after the CAT-WO-01.1 rebase).
ALTER TABLE app.review_event DROP CONSTRAINT IF EXISTS review_event_status_check;
ALTER TABLE app.review_event ADD CONSTRAINT review_event_status_check CHECK (status IN ('confirmed', 'wrong', 'edited'));
DO $$ BEGIN
    ALTER TABLE app.review_event ADD CONSTRAINT review_event_edits_size CHECK (edits IS NULL OR octet_length(edits::text) <= 4000);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------- Find over v_find + the WO-02 fields (v_find itself unchanged)
CREATE OR REPLACE VIEW app.v_find_x WITH (security_barrier = true) AS
SELECT v.file_id, v.document_id, v.web_view_link, v.mime_type, v.file_type_family, v.modified_time, v.tier,
       v.kind, v.fiscal_year, v.period, v.effective_date, v.workstream, v.issuer, v.requires_execution, v.stage,
       v.signed_date, v.pii_lp,
       coalesce(d.entities_confirmed, v.entities)                           AS entities,
       coalesce(d.portcos_confirmed, v.portcos)                             AS portcos,
       v.is_primary, v.confidence, v.stage_suggested, v.signals, v.reviewed,
       coalesce(d.issuing_entity_confirmed, d.issuing_entity_auto)          AS issuing_entity,
       coalesce(d.receiving_entities_confirmed, d.receiving_entities_auto, '{}'::text[]) AS receiving_entities,
       coalesce(d.status_confirmed, d.status_auto)                          AS status,
       coalesce(d.issued_date_confirmed, d.issued_date_auto)                AS issued_date
FROM app.v_find v                       -- secret tier already excluded in v_find
LEFT JOIN cat.document d ON d.document_id = v.document_id;

COMMIT;

BEGIN;
GRANT SELECT ON app.v_find_x TO catalog_app;
COMMIT;
