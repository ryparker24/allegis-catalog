-- CAT-WO-03 · 005_wo03.sql   (run as the DB owner; idempotent; THROWAWAY BRANCH until release)
-- Checklists (R-025) and a document's Subject (R-026). Order of a release run:
--   1. this file (tables, entities, views, grants)
--   2. pipeline/roster_load_wo03.py        (crawl step `roster`: newest Datum CSV pair -> ref.party / ref.doc_subtype)
--   3. 005b_wo03_seed.sql                  (subtype -> kind mapping and the six ruled rules; they reference ref.doc_subtype)
--   4. pipeline/applicability_load_wo03.py (Ryan's filled-in workbook -> ops.requirement_applicability)
--   5. pipeline/subject_wo03.py --apply    (cat.doc_party, Subject codes / person, personnel handling)
--   6. pipeline/requirements_wo03.py --apply (ops.requirement)
-- LP names live ONLY in ref.party and ref.party_alias. catalog_app reads them only through app.v_party (display name
-- and codes), which no other role is granted. Nothing here logs or exports a name.

BEGIN;

-- ---------------------------------------------------------------- item 1 · Datum exports (from the prep, unchanged)
CREATE TABLE IF NOT EXISTS ref.datum_export (
  file_kind    text NOT NULL CHECK (file_kind IN ('partner_roster', 'doc_subtype')),
  export_date  date NOT NULL,
  file_name    text NOT NULL,
  sha256       text NOT NULL,
  row_count    integer NOT NULL,
  loaded_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (file_kind, export_date)
);

CREATE TABLE IF NOT EXISTS ref.party (
  datum_company_code  text NOT NULL,
  datum_company_kind  text NOT NULL CHECK (datum_company_kind IN ('fund', 'gp', 'spv')),
  datum_company_name  text NOT NULL,                        -- the fund / GP / SPV legal name (an entity, not an LP)
  entity_code         text REFERENCES ref.entity (entity_code), -- NULL = unmapped: reported, never guessed
  partner_code        text NOT NULL,
  relationship_code   text NOT NULL,
  display_name        text NOT NULL,                        -- LP name: never logged, labelled or exported
  legal_name          text NOT NULL,                        -- LP name: never logged, labelled or exported
  legal_name_status   text,
  interest_kind       text NOT NULL CHECK (interest_kind IN ('capital', 'carried_interest')),
  is_company_gp       boolean NOT NULL,                     -- partner name = a Datum GP company's name (the fund's own GP)
  commitment_date     date,
  active_from         date,
  active_to           date,
  active_from_basis   text,
  active_to_basis     text,
  export_date         date NOT NULL,
  PRIMARY KEY (datum_company_code, partner_code, relationship_code)
);
CREATE INDEX IF NOT EXISTS party_entity ON ref.party (entity_code);
CREATE INDEX IF NOT EXISTS party_partner ON ref.party (partner_code);
-- R-026: a roster code is the only thing that ever reaches a label. Datum codes: LP-0001, LP-0001-CI, GM-0001, GPM-01.
DO $$ BEGIN
  ALTER TABLE ref.party ADD CONSTRAINT party_code_shape CHECK (partner_code ~ '^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS ref.doc_subtype (
  subtype_code         text PRIMARY KEY,
  category_code        text NOT NULL,
  name                 text NOT NULL,
  app_fund             text NOT NULL CHECK (app_fund     IN ('required', 'conditional', 'not_applicable')),
  app_spv              text NOT NULL CHECK (app_spv      IN ('required', 'conditional', 'not_applicable')),
  app_gp               text NOT NULL CHECK (app_gp       IN ('required', 'conditional', 'not_applicable')),
  app_manco            text NOT NULL CHECK (app_manco    IN ('required', 'conditional', 'not_applicable')),
  app_blocker          text NOT NULL CHECK (app_blocker  IN ('required', 'conditional', 'not_applicable')),
  periodicity          text NOT NULL CHECK (periodicity  IN ('none', 'annual', 'quarterly')),
  multiplicity         text NOT NULL CHECK (multiplicity IN ('single', 'set')),
  active               boolean NOT NULL,
  datum_document_kind  text,
  export_date          date NOT NULL
);

-- name variants for matching partners to file / folder names. Seeded from display + legal name by the roster load
-- (source 'datum'); Ryan can add rows (source 'ryan'), which a reload never removes.
CREATE TABLE IF NOT EXISTS ref.party_alias (
  partner_code  text NOT NULL,
  alias         text NOT NULL,                              -- LP name variant: never logged, labelled or exported
  source        text NOT NULL CHECK (source IN ('datum', 'ryan')),
  added_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (partner_code, alias)
);

-- ---------------------------------------------------------------- ruling (a) · entities (Ryan, 2026-11-17 / 11-18)
-- 11 new entities (CIP-II (GP) is its own GP, NOT CIP2A; MTV-III (PF) is its own fund, the Pledge Fund).
-- Each needs label choices: pipeline/labels_setup_wo03.py (drafts; Ryan publishes in Label manager).
INSERT INTO ref.entity (entity_code, name, entity_type, family, active, provisional, notes) VALUES
  ('MTV-III (PF)',      'MTV-III (PF)',      'fund', 'MTV',  true, false, 'CAT-WO-03 (a); Datum MTV-III (PF); the Pledge Fund, its own entity'),
  ('MTV-III (PF) (GP)', 'MTV-III (PF) (GP)', 'gp',   'MTV',  true, false, 'CAT-WO-03 (a); Datum MTV-III (PF) (GP)'),
  ('ASOF (GP)',         'ASOF (GP)',         'gp',   'ASOF', true, false, 'CAT-WO-03 (a); Datum ASOF (GP)'),
  ('X (GP)',            'X (GP)',            'gp',   'X',    true, false, 'CAT-WO-03 (a); Datum Allegis X (GP)'),
  ('CIP-II (GP)',       'CIP-II (GP)',       'gp',   'CIP',  true, false, 'CAT-WO-03 (a); Datum CIP-II (GP); NOT CIP2A (the CIP-II Admin manco)'),
  ('NL-I (GP)',         'NL-I (GP)',         'gp',   'NL',   true, false, 'CAT-WO-03 (a); Datum NL-I (GP)'),
  ('NL-II (GP)',        'NL-II (GP)',        'gp',   'NL',   true, false, 'CAT-WO-03 (a); Datum NL-II (GP)'),
  ('FUNDAM',            'FUNDAM',            'spv',  NULL,   true, false, 'CAT-WO-03 (a); Datum Fundam (SPV)'),
  ('LS-I',              'LS-I',              'spv',  NULL,   true, false, 'CAT-WO-03 (a); Datum Lightship I (SPV)'),
  ('LS-II',             'LS-II',             'spv',  NULL,   true, false, 'CAT-WO-03 (a); Datum Lightship II (SPV)'),
  ('ATTOTUDE',          'ATTOTUDE',          'spv',  NULL,   true, false, 'CAT-WO-03 (a); Datum Attotude (SPV)')
ON CONFLICT (entity_code) DO UPDATE SET entity_type = EXCLUDED.entity_type, family = EXCLUDED.family,
  provisional = false, notes = EXCLUDED.notes;

-- the 10 Datum-code aliases (identical codes map exactly and need none)
INSERT INTO ref.entity_alias (alias, entity_code, source, generic) VALUES
  ('Allegis X',          'X',        'datum cat-wo-03 2026-11-17', false),
  ('Dragos (SPV)',       'ACCSO',    'datum cat-wo-03 2026-11-17', false),
  ('Shape MTV-VI (SPV)', 'MTV-VI',   'datum cat-wo-03 2026-11-17', false),
  ('Allegis IVY (SPV)',  'IVY',      'datum cat-wo-03 2026-11-17', false),
  ('Allegis TM (SPV)',   'TM',       'datum cat-wo-03 2026-11-17', false),
  ('Allegis X (GP)',     'X (GP)',   'datum cat-wo-03 2026-11-17', false),
  ('Fundam (SPV)',       'FUNDAM',   'datum cat-wo-03 2026-11-17', false),
  ('Lightship I (SPV)',  'LS-I',     'datum cat-wo-03 2026-11-17', false),
  ('Lightship II (SPV)', 'LS-II',    'datum cat-wo-03 2026-11-17', false),
  ('Attotude (SPV)',     'ATTOTUDE', 'datum cat-wo-03 2026-11-17', false)
ON CONFLICT DO NOTHING;

-- types ruled (Ryan, 2026-11-18): X, NL-I, NL-II, XI = fund; TM = spv. CYBER-II stays as retired in Part 2.
UPDATE ref.entity SET entity_type = 'fund' WHERE entity_code IN ('X', 'NL-I', 'NL-II', 'XI') AND entity_type IS NULL;
UPDATE ref.entity SET entity_type = 'spv'  WHERE entity_code = 'TM' AND entity_type IS NULL;

-- ---------------------------------------------------------------- item 2 · rules, applicability (seed rows: 005b)
CREATE TABLE IF NOT EXISTS ref.doc_subtype_kind (
  subtype_code text NOT NULL REFERENCES ref.doc_subtype (subtype_code),
  kind         text NOT NULL,
  role         text NOT NULL DEFAULT 'satisfying' CHECK (role IN ('satisfying', 'candidate')),
  qualifier    text,
  ruled        text NOT NULL,
  PRIMARY KEY (subtype_code, kind)
);

CREATE TABLE IF NOT EXISTS ops.requirement_applicability (
  entity_code   text NOT NULL REFERENCES ref.entity (entity_code),
  subtype_code  text NOT NULL REFERENCES ref.doc_subtype (subtype_code),
  required      boolean NOT NULL,
  note          text,
  ruled_by      text NOT NULL,
  ruled_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_code, subtype_code)
);

CREATE TABLE IF NOT EXISTS ops.requirement_rule (
  rule_id          text NOT NULL,
  version          integer NOT NULL,
  checklist        text NOT NULL CHECK (checklist IN ('lp_subscriptions', 'fund_level')),
  subtype_code     text REFERENCES ref.doc_subtype (subtype_code),
  no_datum_subtype boolean NOT NULL DEFAULT false,
  satisfying_kinds text[] NOT NULL,
  subject_type     text NOT NULL CHECK (subject_type IN ('entity_fy', 'entity_quarter', 'entity_partner', 'entity_partner_fy', 'entity_partner_quarter')),
  entity_filter    jsonb NOT NULL,
  partner_filter   jsonb,
  period_from      integer,
  satisfied_when   jsonb NOT NULL,
  active           boolean NOT NULL DEFAULT false,
  notes            text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (rule_id, version),
  CHECK (subtype_code IS NOT NULL OR no_datum_subtype)
);

-- ---------------------------------------------------------------- item 3 · Subject (R-026)
-- codes only: roster codes in subject_codes_*, a staff Workspace account (lower-case @allegiscapital.com) in subject_person_*
ALTER TABLE cat.document
    ADD COLUMN IF NOT EXISTS subject_codes_auto        text[],
    ADD COLUMN IF NOT EXISTS subject_codes_confirmed   text[],
    ADD COLUMN IF NOT EXISTS subject_person_auto       text,
    ADD COLUMN IF NOT EXISTS subject_person_confirmed  text,
    ADD COLUMN IF NOT EXISTS subject_rule              text,
    ADD COLUMN IF NOT EXISTS personnel_auto            boolean;
ALTER TABLE cat.document DROP CONSTRAINT IF EXISTS document_subject_codes;
DO $$ BEGIN
  ALTER TABLE cat.document ADD CONSTRAINT document_subject_codes CHECK (
    -- '{}' = a person's "none" (CISO review: array_to_string('{}') is '' and failed the regex)
    (cardinality(coalesce(subject_codes_auto, '{}')) = 0 OR array_to_string(subject_codes_auto, ',') ~ '^((LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?)(,(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?)*$') AND
    (cardinality(coalesce(subject_codes_confirmed, '{}')) = 0 OR array_to_string(subject_codes_confirmed, ',') ~ '^((LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?)(,(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?)*$') AND
    cardinality(coalesce(subject_codes_confirmed, '{}')) <= 20 AND cardinality(coalesce(subject_codes_auto, '{}')) <= 20 AND
    coalesce(subject_person_auto, 'x@allegiscapital.com') ~ '^[a-z0-9._%+-]{1,64}@allegiscapital\.com$' AND
    coalesce(subject_person_confirmed, 'x@allegiscapital.com') ~ '^[a-z0-9._%+-]{1,64}@allegiscapital\.com$') NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE cat.document VALIDATE CONSTRAINT document_subject_codes;
-- '{}' confirmed = a person said "none" (the Match subject lane's "none"): never re-filled by a machine match

-- document <-> roster partner. Rebuilt by pipeline/subject_wo03.py except person rows (method 'person'), which only a
-- person's decision writes (the Match subject lane / the Subject code(s) label read back).
CREATE TABLE IF NOT EXISTS cat.doc_party (
  document_id   bigint NOT NULL,
  partner_code  text   NOT NULL CHECK (partner_code ~ '^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$'),
  entity_code   text,                       -- the roster (entity) the match was made against
  method        text   NOT NULL,
  confidence    text   NOT NULL CHECK (confidence IN ('high', 'low', 'confirmed')),
  rule          text,
  built_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (document_id, partner_code)
);
-- 'parties' = from CAT-WO-02 Parties (a K-1 issued by the fund and received by its own GP entity = the fund's GP row)
ALTER TABLE cat.doc_party DROP CONSTRAINT IF EXISTS doc_party_method_check;
ALTER TABLE cat.doc_party ADD CONSTRAINT doc_party_method_check CHECK (method IN ('folder', 'name', 'label', 'person', 'parties'));
CREATE INDEX IF NOT EXISTS doc_party_partner ON cat.doc_party (partner_code);

-- ---------------------------------------------------------------- item 4 · requirements (rebuilt nightly by derive)
CREATE TABLE IF NOT EXISTS ops.requirement (
  req_key          text PRIMARY KEY CHECK (length(req_key) <= 200),
  rule_id          text NOT NULL,
  rule_version     integer NOT NULL,
  checklist        text NOT NULL,
  subtype_code     text,
  subject_type     text NOT NULL,
  entity_code      text NOT NULL,
  partner_code     text,
  fiscal_year      integer,
  fiscal_quarter   smallint,
  result           text NOT NULL CHECK (result IN ('met', 'on_file', 'missing', 'not_required', 'none_found', 'no_roster')),
  sub_status       text,        -- on_file: unknown / draft / final_unexecuted / partially_executed / not_satisfying
  urgency          smallint NOT NULL,
  best_document_id bigint,
  best_file_id     text,
  best_kind        text,
  best_stage       text,
  best_status      text,
  best_date        date,
  best_reason      text,        -- codes / plain words, never a name
  best_source      text CHECK (best_source IN ('auto', 'person')),
  candidates       jsonb NOT NULL DEFAULT '[]',
  n_candidates     integer NOT NULL DEFAULT 0,
  override_id      bigint,
  built_run        text NOT NULL,
  built_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS requirement_rule_entity ON ops.requirement (rule_id, entity_code);
ALTER TABLE ops.requirement DROP CONSTRAINT IF EXISTS requirement_result_check;
ALTER TABLE ops.requirement ADD CONSTRAINT requirement_result_check
  CHECK (result IN ('met', 'on_file', 'missing', 'not_required', 'none_found', 'no_roster', 'applicability_not_set'));

-- ---------------------------------------------------------------- the app's overrides: append-only, never rebuilt away
-- The effective override for a requirement is its LATEST row; "clear" ends any earlier one.
CREATE TABLE IF NOT EXISTS app.requirement_override (
  override_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  req_key      text NOT NULL CHECK (length(req_key) <= 200),
  action       text NOT NULL CHECK (action IN ('link', 'not_required', 'clear')),
  file_id      text CHECK (file_id ~ '^[A-Za-z0-9_-]{10,128}$'),
  document_id  bigint,
  note         text CHECK (length(note) <= 2000),
  by_email     text NOT NULL CHECK (by_email = lower(by_email)),
  created_at   timestamptz NOT NULL DEFAULT now(),
  CHECK (action <> 'link' OR file_id IS NOT NULL),
  CHECK (action <> 'not_required' OR length(btrim(coalesce(note, ''))) > 0)
);
CREATE INDEX IF NOT EXISTS requirement_override_key ON app.requirement_override (req_key, override_id DESC);
DROP TRIGGER IF EXISTS requirement_override_append_only ON app.requirement_override;
CREATE TRIGGER requirement_override_append_only BEFORE UPDATE OR DELETE ON app.requirement_override
    FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
DROP TRIGGER IF EXISTS requirement_override_no_truncate ON app.requirement_override;
CREATE TRIGGER requirement_override_no_truncate BEFORE TRUNCATE ON app.requirement_override
    FOR EACH STATEMENT EXECUTE FUNCTION app.tg_append_only();
-- the shared trigger function names review_event in its message; make it name the table it fires on
CREATE OR REPLACE FUNCTION app.tg_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '%.% is append-only (% refused)', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP USING ERRCODE = 'insufficient_privilege';
END $$;

-- the Match subject lane's decisions are review events (codes only in edits)
ALTER TABLE app.review_event DROP CONSTRAINT IF EXISTS review_event_source;
ALTER TABLE app.review_event ADD CONSTRAINT review_event_source CHECK (source IN ('review', 'find_single', 'find_bulk', 'review_edit', 'match_subject'));

COMMIT;

-- ---------------------------------------------------------------- app views
BEGIN;
-- LP names reach the app ONLY here (R-025): codes + display name of MAPPED roster rows. Granted to catalog_app alone.
CREATE OR REPLACE VIEW app.v_party WITH (security_barrier = true) AS
SELECT DISTINCT ON (p.entity_code, p.partner_code)
       p.entity_code, p.partner_code, p.display_name, p.interest_kind, p.is_company_gp, p.datum_company_kind
FROM ref.party p
WHERE p.entity_code IS NOT NULL
ORDER BY p.entity_code, p.partner_code, p.relationship_code;

-- Find + Subject fields. v_find_x as in 004 plus subject_codes / subject_person (codes and a staff account only).
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
       coalesce(d.issued_date_confirmed, d.issued_date_auto)                AS issued_date,
       coalesce(d.subject_codes_confirmed, d.subject_codes_auto, '{}'::text[]) AS subject_codes,
       coalesce(d.subject_person_confirmed, d.subject_person_auto)          AS subject_person
FROM app.v_find v                       -- secret tier already excluded in v_find
LEFT JOIN cat.document d ON d.document_id = v.document_id;

-- The Match subject lane: a document with only LOW-confidence partner matches and no person decision yet.
-- One row per labelled file of such a document; candidate partner CODES only (names come from v_party in the app).
CREATE OR REPLACE VIEW app.v_subject_candidates WITH (security_barrier = true) AS
SELECT dp.document_id, array_agg(dp.partner_code ORDER BY dp.partner_code) AS partner_codes,
       array_agg(DISTINCT dp.entity_code) FILTER (WHERE dp.entity_code IS NOT NULL) AS roster_entities
FROM cat.doc_party dp
JOIN cat.document d ON d.document_id = dp.document_id
WHERE dp.confidence = 'low'
  AND d.subject_codes_confirmed IS NULL
  AND NOT EXISTS (SELECT 1 FROM cat.doc_party h WHERE h.document_id = dp.document_id AND h.confidence IN ('high', 'confirmed'))
GROUP BY dp.document_id;

-- Review queue: + 'match_subject' (before Status unknown, which would otherwise swallow it). A Match subject decision
-- (review_event source = match_subject) takes the file out of that lane at once, before the nightly rebuild.
CREATE OR REPLACE VIEW app.v_review_queue WITH (security_barrier = true) AS
 SELECT file_id, document_id, web_view_link, mime_type, file_type_family, modified_time, tier, kind, fiscal_year, period,
    effective_date, workstream, issuer, requires_execution, stage, signed_date, pii_lp, entities, portcos, is_primary,
    confidence, stage_suggested, signals, reviewed, queue_reason,
        CASE queue_reason
            WHEN 'stage_unknown'::text THEN 1
            WHEN 'low_confidence_executed'::text THEN 2
            WHEN 'no_kind'::text THEN 3
            WHEN 'match_subject'::text THEN 4
            ELSE 5
        END AS queue_rank,
        CASE confidence
            WHEN 'none'::text THEN 0
            WHEN 'low'::text THEN 1
            WHEN 'medium'::text THEN 2
            WHEN 'high'::text THEN 3
            ELSE 4
        END AS confidence_rank,
    status, subject_candidates
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
  WHERE (queue_reason IS NOT NULL);

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
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'match_subject'::text) AS match_subject;

-- Checklists: the nightly result with the LATEST person override applied at read time (an override shows at once and
-- the rebuild never undoes it). A best file that has left the app's scope (secret tier, removed, unlabelled) is
-- dropped here: the row keeps its result but shows no file.
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
       CASE e.ov_action WHEN 'not_required' THEN 7 WHEN 'link' THEN 6 ELSE e.urgency END AS urgency,
       CASE WHEN e.ov_action = 'link' THEN lf.file_id ELSE bf.file_id END AS best_file_id,
       -- a best document that left the app's scope (e.g. now secret tier) shows NOTHING about itself (CISO review)
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
       e.built_at
FROM eff e
LEFT JOIN app.v_find_x bf ON bf.file_id = e.best_file_id
LEFT JOIN app.v_find_x lf ON lf.file_id = e.ov_file_id;

COMMIT;

BEGIN;
REVOKE ALL ON ref.datum_export, ref.party, ref.party_alias, ref.doc_subtype, ref.doc_subtype_kind,
              ops.requirement_applicability, ops.requirement_rule, ops.requirement, cat.doc_party FROM PUBLIC;
REVOKE ALL ON app.v_party, app.v_subject_candidates, app.v_requirement, app.requirement_override FROM PUBLIC;
GRANT SELECT ON app.v_find_x, app.v_review_queue, app.v_review_counts, app.v_requirement, app.v_party TO catalog_app;
GRANT INSERT ON app.requirement_override TO catalog_app;
-- (no SELECT on app.requirement_override: the app reads overrides only through v_requirement; no grant on
--  v_subject_candidates: the queue view carries the candidate codes)
COMMIT;
