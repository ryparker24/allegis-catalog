-- CAT-WO-06 · first-page reading (R-033 .. R-038). Run as the DB owner; re-runnable.
-- R-033: NO table or column here can hold page text, a name, an address, a TIN, an amount or a percentage. Every new
-- text column is a code with a CHECK on its shape (guard G-S1 tests the schema; G-S2 the stored values).
BEGIN;

-- ------------------------------------------------------------------ one row per document read (no text of any kind)
CREATE TABLE IF NOT EXISTS cat.doc_page_read (
  document_id        bigint PRIMARY KEY,
  md5                text NOT NULL CHECK (md5 ~ '^([0-9a-f]{32}|rev:[A-Za-z0-9_:.+ -]{1,80})$'),   -- md5, or the revision key of a Google Doc
  page_count         integer CHECK (page_count IS NULL OR page_count >= 0),
  pages_read         integer CHECK (pages_read IS NULL OR pages_read >= 0),
  text_layer         boolean,
  ocr_used           boolean NOT NULL DEFAULT false,
  extractor_version  text NOT NULL CHECK (extractor_version ~ '^cnt-[0-9]{1,4}$'),
  outcome            text NOT NULL CHECK (outcome IN ('ok', 'no_anchor', 'ocr_needed', 'ocr_partial', 'too_large', 'encrypted',
                                                      'download_error', 'open_error', 'skipped_format', 'no_file')),
  statements         integer NOT NULL DEFAULT 0 CHECK (statements >= 0),
  tin_present        boolean NOT NULL DEFAULT false,      -- R-037: presence only, never the value
  lp_pii             boolean NOT NULL DEFAULT false,      -- R-037: a roster partner was matched
  read_ms            integer,
  read_at            timestamptz NOT NULL DEFAULT now()
);

-- one row per partner candidate per statement (a package / bundle has many statements). Codes, pages and reasons only.
CREATE TABLE IF NOT EXISTS cat.doc_content_match (
  document_id     bigint   NOT NULL,
  seq             smallint NOT NULL CHECK (seq >= 1),                 -- statement number inside the document
  cand            smallint NOT NULL CHECK (cand >= 1),                -- candidate number inside the statement
  page_from       integer  NOT NULL CHECK (page_from >= 1),
  page_to         integer  NOT NULL CHECK (page_to >= page_from),
  anchor          text CHECK (anchor IS NULL OR anchor ~ '^[A-Z0-9]{1,6}(-[A-Z0-9]{1,8}){0,3}$'),
  rule_id         text CHECK (rule_id IS NULL OR rule_id ~ '^CNT-[A-Z0-9]{1,6}(-[A-Z0-9]{1,10}){1,3}$'),
  partner_code    text CHECK (partner_code IS NULL OR partner_code ~ '^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$'),
  roster_entity   text REFERENCES ref.entity (entity_code),
  content_entity  text REFERENCES ref.entity (entity_code),
  confidence      text NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'none')),
  reason          text CHECK (reason IS NULL OR reason IN ('NO_ROSTER_MATCH', 'NOT_IN_FUND', 'MULTIPLE', 'CONFLICT_PERSON', 'CONFLICT_PORTAL')),
  lane            boolean NOT NULL DEFAULT false,                     -- set by the Subject step: shows in Match subject
  PRIMARY KEY (document_id, seq, cand)
);
CREATE INDEX IF NOT EXISTS doc_content_match_partner ON cat.doc_content_match (partner_code);

-- content-derived FY / period / entity, set against the document's current values (codes / numbers / dates only)
ALTER TABLE cat.doc_content_check
  ADD COLUMN IF NOT EXISTS content_fiscal_year integer CHECK (content_fiscal_year IS NULL OR content_fiscal_year BETWEEN 1980 AND 2100),
  ADD COLUMN IF NOT EXISTS content_quarter     smallint CHECK (content_quarter IS NULL OR content_quarter BETWEEN 1 AND 4),
  ADD COLUMN IF NOT EXISTS content_period_end  date,
  ADD COLUMN IF NOT EXISTS content_entity      text REFERENCES ref.entity (entity_code),
  ADD COLUMN IF NOT EXISTS content_amended     boolean,
  ADD COLUMN IF NOT EXISTS content_read_at     timestamptz,
  ADD COLUMN IF NOT EXISTS content_disagrees   text[] CHECK (content_disagrees IS NULL OR content_disagrees <@ ARRAY['fiscal_year', 'period', 'entity']::text[]);

-- doc_party: page range, anchor, reason; method 'content'
ALTER TABLE cat.doc_party
  ADD COLUMN IF NOT EXISTS page_from integer CHECK (page_from IS NULL OR page_from >= 1),
  ADD COLUMN IF NOT EXISTS page_to   integer CHECK (page_to IS NULL OR page_to >= 1),
  ADD COLUMN IF NOT EXISTS anchor    text CHECK (anchor IS NULL OR anchor ~ '^[A-Z0-9]{1,6}(-[A-Z0-9]{1,8}){0,3}$'),
  ADD COLUMN IF NOT EXISTS reason    text CHECK (reason IS NULL OR reason IN ('NO_ROSTER_MATCH', 'NOT_IN_FUND', 'MULTIPLE', 'CONFLICT_PERSON', 'CONFLICT_PORTAL'));
ALTER TABLE cat.doc_party DROP CONSTRAINT IF EXISTS doc_party_method_check;
ALTER TABLE cat.doc_party ADD CONSTRAINT doc_party_method_check CHECK (method IN ('folder', 'name', 'label', 'person', 'parties', 'portal', 'content'));

-- R-037 presence flags for Handling Contains (codes only)
ALTER TABLE cat.document ADD COLUMN IF NOT EXISTS content_flags text[];
ALTER TABLE cat.document DROP CONSTRAINT IF EXISTS document_content_flags;
ALTER TABLE cat.document ADD CONSTRAINT document_content_flags CHECK (content_flags IS NULL OR content_flags <@ ARRAY['tax_id', 'lp_pii']::text[]);

-- R-038 rules as data
ALTER TABLE ops.decomposition_rule DROP CONSTRAINT IF EXISTS decomposition_rule_applies_to_check;
ALTER TABLE ops.decomposition_rule ADD CONSTRAINT decomposition_rule_applies_to_check
  CHECK (applies_to IN ('path_segment', 'folder_path', 'name', 'drive', 'mime', 'status', 'content'));

-- "Corrections stick": a name variant learned from a person's pick in the lane (DB only; never logged or labelled)
ALTER TABLE ref.party_alias DROP CONSTRAINT IF EXISTS party_alias_source_check;
ALTER TABLE ref.party_alias ADD CONSTRAINT party_alias_source_check CHECK (source IN ('datum', 'ryan', 'lane'));

-- checklists: the page of the best document inside a package / bundle
ALTER TABLE ops.requirement ADD COLUMN IF NOT EXISTS best_page integer;

REVOKE ALL ON cat.doc_page_read, cat.doc_content_match FROM PUBLIC;
COMMIT;

-- ------------------------------------------------------------------ views
BEGIN;
-- Match subject: + content candidates (lane = true, set nightly by the Subject step) with reason codes; appended columns
CREATE OR REPLACE VIEW app.v_subject_candidates WITH (security_barrier = true) AS
WITH old AS (
  SELECT dp.document_id, array_agg(dp.partner_code ORDER BY dp.partner_code) AS partner_codes,
         array_agg(DISTINCT dp.entity_code) FILTER (WHERE dp.entity_code IS NOT NULL) AS roster_entities,
         array_agg(DISTINCT dp.reason) FILTER (WHERE dp.reason IS NOT NULL) AS reasons
  FROM cat.doc_party dp JOIN cat.document d ON d.document_id = dp.document_id
  WHERE dp.confidence = 'low' AND d.subject_codes_confirmed IS NULL
    AND NOT EXISTS (SELECT 1 FROM cat.doc_party h WHERE h.document_id = dp.document_id AND h.confidence IN ('high', 'confirmed'))
  GROUP BY dp.document_id
), cnt AS (
  SELECT m.document_id, array_agg(DISTINCT m.partner_code) FILTER (WHERE m.partner_code IS NOT NULL) AS codes,
         array_agg(DISTINCT m.roster_entity) FILTER (WHERE m.roster_entity IS NOT NULL) AS ents,
         array_agg(DISTINCT coalesce(m.reason, 'MEDIUM')) AS reasons, min(m.page_from) AS page_from, max(m.page_to) AS page_to
  FROM cat.doc_content_match m WHERE m.lane GROUP BY m.document_id
)
SELECT coalesce(o.document_id, c.document_id) AS document_id,
       coalesce((SELECT array_agg(DISTINCT x ORDER BY x) FROM unnest(coalesce(o.partner_codes, '{}') || coalesce(c.codes, '{}')) x), '{}') AS partner_codes,
       (SELECT array_agg(DISTINCT x) FROM unnest(coalesce(o.roster_entities, '{}') || coalesce(c.ents, '{}')) x) AS roster_entities,
       (SELECT array_agg(DISTINCT x ORDER BY x) FROM unnest(coalesce(o.reasons, '{}') || coalesce(c.reasons, '{}')) x) AS reasons,
       c.document_id IS NOT NULL AS content_lane,
       c.page_from, c.page_to
FROM old o FULL JOIN cnt c ON c.document_id = o.document_id;

-- Review queue: content lanes. Appended columns: subject_reasons, content_disagrees. New queue reason 'content_disagrees'.
CREATE OR REPLACE VIEW app.v_review_queue WITH (security_barrier = true) AS
 SELECT q.file_id, q.document_id, q.web_view_link, q.mime_type, q.file_type_family, q.modified_time, q.tier, q.kind, q.fiscal_year,
    q.period, q.effective_date, q.workstream, q.issuer, q.requires_execution, q.stage, q.signed_date, q.pii_lp, q.entities, q.portcos,
    q.is_primary, q.confidence, q.stage_suggested, q.signals, q.reviewed, q.queue_reason,
        CASE q.queue_reason
            WHEN 'stage_unknown'::text THEN 1
            WHEN 'low_confidence_executed'::text THEN 2
            WHEN 'no_kind'::text THEN 3
            WHEN 'match_subject'::text THEN 4
            WHEN 'content_disagrees'::text THEN 5
            ELSE 6
        END AS queue_rank,
        CASE q.confidence
            WHEN 'none'::text THEN 0
            WHEN 'low'::text THEN 1
            WHEN 'medium'::text THEN 2
            WHEN 'high'::text THEN 3
            ELSE 4
        END AS confidence_rank,
    q.status, q.subject_candidates,
    array_to_string(COALESCE(dl.path_segments, fo.path_segments), ' › '::text) AS location,
    COALESCE(dl.folder_id, fo.parent_ids[1]) AS location_folder_id,
    GREATEST(COALESCE(dl.n_folders, 1) - 1, 0) AS other_locations,
    q.subject_reasons, q.content_disagrees
   FROM ( SELECT v.file_id, v.document_id, v.web_view_link, v.mime_type, v.file_type_family, v.modified_time, v.tier, v.kind,
            v.fiscal_year, v.period, v.effective_date, v.workstream, v.issuer, v.requires_execution, v.stage, v.signed_date, v.pii_lp,
            v.entities, v.portcos, v.is_primary, v.confidence, v.stage_suggested, v.signals, v.reviewed,
            COALESCE(d.status_confirmed, d.status_auto) AS status,
            sc.partner_codes AS subject_candidates, sc.reasons AS subject_reasons, cc.content_disagrees,
                CASE
                    WHEN NOT v.reviewed AND v.requires_execution AND v.stage = 'unknown'::text THEN 'stage_unknown'::text
                    WHEN NOT v.reviewed AND v.stage = 'fully_executed'::text AND v.confidence = 'low'::text THEN 'low_confidence_executed'::text
                    WHEN NOT v.reviewed AND v.kind IS NULL THEN 'no_kind'::text
                    -- content lane rows are already "open" (the Subject step drops them once a person decides after the read)
                    WHEN sc.document_id IS NOT NULL AND (sc.content_lane OR NOT (EXISTS ( SELECT 1
                       FROM app.review_event m
                      WHERE m.document_id = v.document_id AND m.source = 'match_subject'::text))) THEN 'match_subject'::text
                    WHEN cc.content_disagrees IS NOT NULL AND NOT (EXISTS ( SELECT 1 FROM app.review_event m
                      WHERE m.document_id = v.document_id AND m.created_at > cc.content_read_at)) THEN 'content_disagrees'::text   -- any review / edit after the read closes it
                    WHEN NOT v.reviewed AND NOT COALESCE(v.requires_execution, false) AND COALESCE(d.status_confirmed, d.status_auto) IS NULL THEN 'status_unknown'::text
                    ELSE NULL::text
                END AS queue_reason
           FROM app.v_find v
             LEFT JOIN cat.document d ON d.document_id = v.document_id
             LEFT JOIN app.v_subject_candidates sc ON sc.document_id = v.document_id
             LEFT JOIN cat.doc_content_check cc ON cc.document_id = v.document_id AND cc.content_disagrees IS NOT NULL
          WHERE NOT v.reviewed OR sc.document_id IS NOT NULL OR cc.document_id IS NOT NULL) q
     LEFT JOIN cat.document_location dl ON dl.document_id = q.document_id
     LEFT JOIN cat.file fo ON fo.file_id = q.file_id
  WHERE q.queue_reason IS NOT NULL;

CREATE OR REPLACE VIEW app.v_review_counts WITH (security_barrier = true) AS
 SELECT ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'stage_unknown'::text) AS stage_unknown,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'low_confidence_executed'::text) AS low_confidence_executed,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'no_kind'::text) AS no_kind,
    ( SELECT count(*)::integer FROM app.v_review_queue) AS open_total,
    ( SELECT count(*)::integer FROM app.review_event r JOIN app.v_find v USING (file_id)
       WHERE r.created_at >= date_trunc('day'::text, now()) AND r.status = ANY (ARRAY['confirmed'::text, 'wrong'::text])) AS reviewed_today,
    ( SELECT count(DISTINCT r.file_id)::integer FROM app.review_event r JOIN app.v_find v USING (file_id)
       WHERE r.status = ANY (ARRAY['confirmed'::text, 'wrong'::text])) AS reviewed_total,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'status_unknown'::text) AS status_unknown,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'match_subject'::text) AS match_subject,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'content_disagrees'::text) AS content_disagrees;

-- the side panel: "Matched from content, p. N–M" (codes, pages, anchor, confidence, reason; no text)
CREATE OR REPLACE VIEW app.v_doc_content WITH (security_barrier = true) AS
 SELECT m.document_id, m.seq, m.page_from, m.page_to, m.partner_code, m.confidence, m.anchor, m.reason, m.lane,
        r.page_count, r.outcome, r.ocr_used, r.read_at,
        cc.content_fiscal_year, cc.content_quarter, cc.content_entity, cc.content_disagrees
   FROM cat.doc_content_match m
   JOIN cat.doc_page_read r ON r.document_id = m.document_id
   LEFT JOIN cat.doc_content_check cc ON cc.document_id = m.document_id;

-- checklists: + best_page (appended)
CREATE OR REPLACE VIEW app.v_requirement WITH (security_barrier = true) AS
WITH ov AS (
  SELECT DISTINCT ON (req_key) req_key, override_id, action, file_id, note, by_email, created_at
  FROM app.requirement_override ORDER BY req_key, override_id DESC
), eff AS (
  SELECT r.*, ov.override_id AS ov_id, ov.action AS ov_action, ov.file_id AS ov_file_id, ov.note AS ov_note,
         ov.by_email AS ov_by, ov.created_at AS ov_at
  FROM ops.requirement r LEFT JOIN ov ON ov.req_key = r.req_key AND ov.action <> 'clear'
)
SELECT e.req_key, e.rule_id, e.checklist, e.subtype_code, e.subject_type, e.entity_code, e.partner_code, e.fiscal_year, e.fiscal_quarter,
       CASE e.ov_action WHEN 'not_required' THEN 'not_required' WHEN 'link' THEN 'met' ELSE e.result END AS result,
       CASE WHEN e.ov_action IS NOT NULL THEN NULL ELSE e.sub_status END AS sub_status,
       CASE e.ov_action WHEN 'not_required' THEN 7 WHEN 'link' THEN 6 ELSE e.urgency::integer END AS urgency,
       CASE WHEN e.ov_action = 'link' THEN lf.file_id ELSE bf.file_id END AS best_file_id,
       CASE WHEN e.ov_action = 'link' THEN lf.kind WHEN bf.file_id IS NULL THEN NULL ELSE e.best_kind END AS best_kind,
       CASE WHEN e.ov_action = 'link' THEN lf.stage WHEN bf.file_id IS NULL THEN NULL ELSE e.best_stage END AS best_stage,
       CASE WHEN e.ov_action = 'link' THEN lf.status WHEN bf.file_id IS NULL THEN NULL ELSE e.best_status END AS best_status,
       CASE WHEN e.ov_action = 'link' THEN coalesce(lf.signed_date, lf.issued_date, lf.effective_date) WHEN bf.file_id IS NULL THEN NULL ELSE e.best_date END AS best_date,
       CASE WHEN e.ov_action = 'link' THEN 'linked by a person' WHEN e.ov_action = 'not_required' THEN 'not required (person)'
            WHEN e.best_file_id IS NOT NULL AND bf.file_id IS NULL THEN 'best document is outside the catalog''s scope' ELSE e.best_reason END AS best_reason,
       CASE WHEN e.ov_action IS NOT NULL THEN 'person' ELSE e.best_source END AS best_source,
       (e.ov_action = 'link' AND lf.file_id IS NULL) OR (e.ov_action IS NULL AND e.best_file_id IS NOT NULL AND bf.file_id IS NULL) AS best_out_of_scope,
       e.candidates, e.n_candidates,
       e.ov_id AS override_id, e.ov_action AS override_action, e.ov_note AS override_note, e.ov_by AS override_by, e.ov_at AS override_at,
       e.built_at,
       CASE WHEN e.ov_action IS NULL AND bf.file_id IS NOT NULL THEN e.best_page END AS best_page
FROM eff e
LEFT JOIN app.v_find_x bf ON bf.file_id = e.best_file_id
LEFT JOIN app.v_find_x lf ON lf.file_id = e.ov_file_id;

-- the Content disagrees lane's decisions are review events (codes only)
ALTER TABLE app.review_event DROP CONSTRAINT IF EXISTS review_event_source;
ALTER TABLE app.review_event ADD CONSTRAINT review_event_source CHECK (source IN ('review', 'find_single', 'find_bulk', 'review_edit', 'match_subject', 'checklist_link', 'version_link', 'content_disagrees'));

REVOKE ALL ON app.v_doc_content FROM PUBLIC;
GRANT SELECT ON app.v_review_queue, app.v_review_counts, app.v_requirement, app.v_doc_content TO catalog_app;
COMMIT;
