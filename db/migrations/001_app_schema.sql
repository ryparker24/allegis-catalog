-- CAT-WO-01 · 001_app_schema.sql
-- Schema `app` in the catalog DB (Neon curly-sunset-06555843, db "catalog").
-- Views over cat.* that EXCLUDE SECRET TIER IN THE VIEW ITSELF (R-010), plus app tables.
-- Idempotent: safe to re-run. Run as the DB owner (catalog_owner). Role grants are in 002_catalog_app_role.sql.

BEGIN;

CREATE SCHEMA IF NOT EXISTS app;
REVOKE ALL ON SCHEMA app FROM PUBLIC;

-- ---------------------------------------------------------------- tables
-- Which files carry the "Allegis Document" label (Decision 1 default: labelled files only).
-- The catalog DB has no other record of this (cat.file.drive_labels is empty until CAT-WO-02's read-back);
-- it is loaded from the labelling run's resume list (file IDs only) by db/load_labelled.py.
CREATE TABLE IF NOT EXISTS app.labelled_file (
    file_id    text PRIMARY KEY,
    source     text        NOT NULL DEFAULT 'labels_done.txt',
    loaded_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.saved_view (
    view_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_email text        NOT NULL CHECK (owner_email = lower(owner_email)),
    name        text        NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    spec        jsonb       NOT NULL,
    is_seed     boolean     NOT NULL DEFAULT false,
    sort        smallint    NOT NULL DEFAULT 100,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_email, name)
);

-- Append-only log of Review-queue writes (one row per "Confirm and next").
CREATE TABLE IF NOT EXISTS app.review_event (
    event_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id        text        NOT NULL,
    document_id    bigint,
    reviewer_email text        NOT NULL,
    status         text        NOT NULL CHECK (status IN ('confirmed', 'wrong')),
    stage          text        CHECK (stage IN ('draft','final_unexecuted','partially_executed','fully_executed','n_a')),
    executed_date  date,
    note           text        CHECK (length(note) <= 2000),
    queue_reason   text,
    labels_written text[]      NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS review_event_file_idx ON app.review_event (file_id);

CREATE OR REPLACE FUNCTION app.tg_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'app.review_event is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END $$;
DROP TRIGGER IF EXISTS review_event_append_only ON app.review_event;
CREATE TRIGGER review_event_append_only BEFORE UPDATE OR DELETE ON app.review_event
    FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
DROP TRIGGER IF EXISTS review_event_no_truncate ON app.review_event;
CREATE TRIGGER review_event_no_truncate BEFORE TRUNCATE ON app.review_event
    FOR EACH STATEMENT EXECUTE FUNCTION app.tg_append_only();

-- ---------------------------------------------------------------- views
-- Every view reads cat.* only through app.v_find, and v_find refuses secret tier itself.
-- coalesce(handling,'secret') makes an UNKNOWN tier fail closed (hidden), not open.
-- No file NAME column anywhere in app.*: names come only from the live Drive call, as the user.
CREATE OR REPLACE VIEW app.v_find WITH (security_barrier = true) AS
SELECT f.file_id,
       d.document_id,
       f.web_view_link,
       f.mime_type,
       f.file_type_family,
       f.modified_time,
       f.handling                                                          AS tier,
       coalesce(d.kind_confirmed, d.kind_auto)                             AS kind,
       coalesce(d.fiscal_year_confirmed, d.fiscal_year_auto)               AS fiscal_year,
       CASE WHEN coalesce(d.fiscal_quarter_confirmed, d.fiscal_quarter_auto) IS NOT NULL
                THEN 'q' || coalesce(d.fiscal_quarter_confirmed, d.fiscal_quarter_auto)
            WHEN coalesce(d.fye_flag_confirmed, d.fye_flag_auto) THEN 'fy' END AS period,
       coalesce(d.effective_date_confirmed, d.effective_date_auto)         AS effective_date,
       coalesce(d.workstream_confirmed, d.workstream_auto)                 AS workstream,
       coalesce(d.issuer_confirmed, d.issuer_auto)                         AS issuer,
       coalesce(d.requires_execution_confirmed, d.requires_execution_auto) AS requires_execution,
       coalesce(d.execution_stage_confirmed, d.execution_stage_auto)       AS stage,
       coalesce(d.signed_date_confirmed, d.signed_date_auto)               AS signed_date,
       coalesce(d.pii_lp_flag_confirmed, d.pii_lp_flag_auto)               AS pii_lp,
       coalesce(ent.codes, '{}'::text[])                                   AS entities,
       coalesce(pco.codes, '{}'::text[])                                   AS portcos,
       (fd.file_role = 'primary')                                          AS is_primary,
       chk.confidence,
       chk.stage_suggested,
       coalesce(chk.signals, '{}'::text[])                                 AS signals,
       EXISTS (SELECT 1 FROM app.review_event r WHERE r.file_id = f.file_id) AS reviewed
FROM app.labelled_file lf
JOIN cat.file f              ON f.file_id = lf.file_id
LEFT JOIN cat.file_document fd ON fd.file_id = f.file_id
LEFT JOIN cat.document d     ON d.document_id = fd.document_id
-- set-based pre-aggregation (a per-row LATERAL over cat.v_file_entity re-plans the view per row: minutes)
LEFT JOIN (SELECT e.file_id, array_agg(DISTINCT e.entity_code ORDER BY e.entity_code) AS codes
           FROM cat.v_file_entity e JOIN app.labelled_file l2 ON l2.file_id = e.file_id
           GROUP BY e.file_id) ent ON ent.file_id = f.file_id
LEFT JOIN (SELECT p.file_id, array_agg(DISTINCT p.portco_code ORDER BY p.portco_code) AS codes
           FROM cat.v_file_portco p JOIN app.labelled_file l3 ON l3.file_id = p.file_id
           GROUP BY p.file_id) pco ON pco.file_id = f.file_id
LEFT JOIN cat.doc_content_check chk ON chk.document_id = d.document_id   -- PK document_id: one row per document
WHERE coalesce(f.handling, 'secret') <> 'secret'
  AND f.removed_run IS NULL
  AND f.trashed IS NOT TRUE
  AND f.is_shortcut IS NOT TRUE;

-- Review queue: stage unknown first, then lowest-confidence guesses, then no kind.
-- A file with a review event leaves the queue (until CAT-WO-02's read-back takes over).
CREATE OR REPLACE VIEW app.v_review_queue WITH (security_barrier = true) AS
SELECT q.*,
       CASE q.queue_reason WHEN 'stage_unknown' THEN 1 WHEN 'low_confidence_executed' THEN 2 ELSE 3 END AS queue_rank,
       CASE q.confidence WHEN 'none' THEN 0 WHEN 'low' THEN 1 WHEN 'medium' THEN 2 WHEN 'high' THEN 3 ELSE 4 END AS confidence_rank
FROM (SELECT v.*,
             CASE WHEN v.requires_execution AND v.stage = 'unknown'      THEN 'stage_unknown'
                  WHEN v.stage = 'fully_executed' AND v.confidence = 'low' THEN 'low_confidence_executed'
                  WHEN v.kind IS NULL                                   THEN 'no_kind' END AS queue_reason
      FROM app.v_find v
      WHERE NOT v.reviewed) q
WHERE q.queue_reason IS NOT NULL;

DROP VIEW IF EXISTS app.v_review_counts;
CREATE VIEW app.v_review_counts WITH (security_barrier = true) AS
SELECT (SELECT count(*)::int FROM app.v_review_queue WHERE queue_reason = 'stage_unknown')           AS stage_unknown,
       (SELECT count(*)::int FROM app.v_review_queue WHERE queue_reason = 'low_confidence_executed') AS low_confidence_executed,
       (SELECT count(*)::int FROM app.v_review_queue WHERE queue_reason = 'no_kind')                 AS no_kind,
       (SELECT count(*)::int FROM app.v_review_queue)                                               AS open_total,
       (SELECT count(*)::int FROM app.review_event r JOIN app.v_find v USING (file_id)
         WHERE r.created_at >= date_trunc('day', now()))                                       AS reviewed_today,
       (SELECT count(DISTINCT r.file_id)::int FROM app.review_event r JOIN app.v_find v USING (file_id)) AS reviewed_total;

-- Display names for filter choices (company/entity names only - no LP or individual names).
CREATE OR REPLACE VIEW app.v_portco WITH (security_barrier = true) AS
SELECT portco_code, coalesce(street_name, name) AS display_name FROM ref.portco;

CREATE OR REPLACE VIEW app.v_entity WITH (security_barrier = true) AS
SELECT entity_code, entity_code AS display_name FROM ref.entity;

COMMIT;
