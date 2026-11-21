-- CAT-WO-05 · portal postings -> Issued + Published To (R-030 / R-031), status rules as data (R-032).
-- Codes only: no partner name is ever stored. Portal partners are stored as the portal's own code (LP portal: the
-- LP-#### code; GP portal: 'M' + the member number) and, where it maps, the Datum roster code.
-- Re-runnable (IF NOT EXISTS / CREATE OR REPLACE / ON CONFLICT).
BEGIN;

-- ------------------------------------------------------------------ portal funds -> catalog entities (data; editable)
CREATE TABLE IF NOT EXISTS ref.portal_fund_map (
  portal       text NOT NULL CHECK (portal IN ('lp', 'gp')),
  fund_ref     text NOT NULL,               -- LP: FUND-####; GP: the portal's fund number
  entity_code  text,                        -- NULL = no catalog entity (postings load; no entity on them)
  note         text,
  PRIMARY KEY (portal, fund_ref)
);
INSERT INTO ref.portal_fund_map (portal, fund_ref, entity_code, note) VALUES
  ('lp', 'FUND-0008', 'MTV-IV (A)', NULL), ('lp', 'FUND-0009', 'MTV-IV (B)', NULL),
  ('lp', 'FUND-0010', 'MTV-V (A)', NULL),  ('lp', 'FUND-0011', 'MTV-V (B)', NULL),
  ('lp', 'FUND-0012', 'MTV-V (MTEF)', 'portal short name "MTV-V (EF)"'),
  ('lp', 'FUND-0013', 'MTV-III (PF)', NULL), ('lp', 'FUND-0014', 'MTV-IV (Annex)', NULL),
  ('lp', 'FUND-0108', 'LS-I', NULL), ('lp', 'FUND-0109', 'LS-II', NULL),
  ('lp', 'FUND-0111', 'FUNDAM', NULL), ('lp', 'FUND-0112', 'ATTOTUDE', NULL),
  ('lp', 'FUND-0113', NULL, 'LS-III: no catalog entity yet'), ('lp', 'FUND-0114', NULL, 'FP-2026: no catalog entity yet'),
  ('gp', '31', 'MTV-IV (GP)', NULL), ('gp', '32', 'MTV-IV (Annex) (GP)', NULL), ('gp', '33', 'MTV-V (GP)', NULL),
  ('gp', '34', 'MTV-III (PF) (GP)', NULL), ('gp', '35', 'ASOF (GP)', NULL), ('gp', '36', 'CIP-I (GP)', NULL),
  ('gp', '37', 'CIP-II (GP)', NULL), ('gp', '38', 'NL-I (GP)', NULL), ('gp', '39', 'X (GP)', NULL), ('gp', '40', 'NL-II (GP)', NULL)
ON CONFLICT (portal, fund_ref) DO NOTHING;

-- ------------------------------------------------------------------ postings (codes only), replaced on each load
CREATE TABLE IF NOT EXISTS ref.portal_posting (
  posting_id      text PRIMARY KEY CHECK (posting_id ~ '^(LPD|GPD)-[0-9]{1,12}$'),
  portal          text NOT NULL CHECK (portal IN ('lp', 'gp')),
  file_id         text NOT NULL CHECK (file_id ~ '^[A-Za-z0-9_-]{10,80}$'),
  portal_partner  text CHECK (portal_partner IS NULL OR portal_partner ~ '^(LP-[0-9]{2,6}(-[A-Z]{1,4})?|M[0-9]{1,9})$'),
  partner_code    text CHECK (partner_code IS NULL OR partner_code ~ '^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$'),
  partner_map     text NOT NULL CHECK (partner_map IN ('exact', 'crosswalk', 'unmapped', 'ambiguous', 'fund_level')),
  -- ambiguous: the roster codes the member's name hash matched (one person, a code per relationship); resolved per
  -- document against the document's own entity (doc_partners), never guessed
  partner_candidates text[] CHECK (partner_candidates IS NULL OR array_to_string(partner_candidates, ',') ~ '^((LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?)(,(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?)*$'),
  fund_ref        text,
  entity_code     text,
  doc_type        text NOT NULL CHECK (doc_type ~ '^[A-Z0-9]{1,6}$'),
  expected_kind   text,
  fiscal_year     smallint,
  fiscal_quarter  smallint CHECK (fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4),
  posted_date     date,
  export_date     date NOT NULL,
  loaded_at       timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE ref.portal_posting ADD COLUMN IF NOT EXISTS partner_candidates text[];
CREATE INDEX IF NOT EXISTS portal_posting_file ON ref.portal_posting (file_id);

CREATE TABLE IF NOT EXISTS ref.portal_export (
  portal       text NOT NULL,
  file_kind    text NOT NULL,
  export_date  date NOT NULL,
  file_name    text NOT NULL,
  sha256       text NOT NULL,
  row_count    integer NOT NULL,
  loaded_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (portal, file_kind, export_date)
);

-- catalog document <-> posting (by file ID, then by md5 for copies); rebuilt by every derive
CREATE TABLE IF NOT EXISTS cat.doc_posting (
  document_id  bigint NOT NULL,
  posting_id   text NOT NULL,
  match        text NOT NULL CHECK (match IN ('file_id', 'md5')),
  PRIMARY KEY (document_id, posting_id)
);
CREATE INDEX IF NOT EXISTS doc_posting_posting ON cat.doc_posting (posting_id);

-- the Review list "Portal kind conflict": the posting's document type disagrees with the catalog's kind (kind unchanged)
CREATE TABLE IF NOT EXISTS ops.portal_kind_conflict (
  document_id  bigint NOT NULL,
  posting_id   text NOT NULL,
  doc_kind     text NOT NULL,
  posted_kind  text NOT NULL,
  built_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (document_id, posting_id)
);

-- ------------------------------------------------------------------ L10 Published To on the document (machine-set)
ALTER TABLE cat.document
  ADD COLUMN IF NOT EXISTS published_channels_auto  text[],
  ADD COLUMN IF NOT EXISTS published_date_auto      date,
  ADD COLUMN IF NOT EXISTS published_ids_auto       text[],
  ADD COLUMN IF NOT EXISTS published_rule           text;
ALTER TABLE cat.document DROP CONSTRAINT IF EXISTS document_published_to;
DO $$ BEGIN
  ALTER TABLE cat.document ADD CONSTRAINT document_published_to CHECK (
    coalesce(published_channels_auto, '{}') <@ ARRAY['lp_portal', 'gp_portal', 'datum', 'email']::text[] AND
    (cardinality(coalesce(published_ids_auto, '{}')) = 0 OR
     array_to_string(published_ids_auto, ',') ~ '^(LPD|GPD)-[0-9]{1,12}(,(LPD|GPD)-[0-9]{1,12})*$')) NOT VALID;
END $$;
ALTER TABLE cat.document VALIDATE CONSTRAINT document_published_to;

-- portal partner matches feed Subject + checklists like any other method
ALTER TABLE cat.doc_party DROP CONSTRAINT IF EXISTS doc_party_method_check;
ALTER TABLE cat.doc_party ADD CONSTRAINT doc_party_method_check CHECK (method IN ('folder', 'name', 'label', 'person', 'parties', 'portal'));

-- ------------------------------------------------------------------ R-032 status rules as data (proposals)
ALTER TABLE ops.decomposition_rule DROP CONSTRAINT IF EXISTS decomposition_rule_applies_to_check;
ALTER TABLE ops.decomposition_rule ADD CONSTRAINT decomposition_rule_applies_to_check
  CHECK (applies_to IN ('path_segment', 'folder_path', 'name', 'drive', 'mime', 'status'));
-- the rules themselves are seeded by pipeline/portals_wo05.py --seed-rules (JSON via json.dumps; provisional rows only)

-- ------------------------------------------------------------------ views
-- Find: + Published To (channels, first posted date, posting IDs). Appended columns only (CREATE OR REPLACE).
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
    CASE WHEN fam.confidence IN ('high', 'person') THEN fam.n_members END AS versions,
    COALESCE(d.published_channels_auto, '{}'::text[]) AS published_channels,
    d.published_date_auto AS published_date,
    COALESCE(d.published_ids_auto, '{}'::text[]) AS published_ids
   FROM app.v_find v
     LEFT JOIN cat.document d ON d.document_id = v.document_id
     LEFT JOIN cat.document_location dl ON dl.document_id = v.document_id
     LEFT JOIN cat.file fo ON fo.file_id = v.file_id
     LEFT JOIN cat.doc_family_member fm ON fm.document_id = v.document_id
     LEFT JOIN cat.doc_family fam ON fam.family_id = fm.family_id;

-- the side panel's postings for a document: channel, date, posting ID, document type, period. No partner (no names,
-- no codes): the partner shows as the document's Subject code(s), which the app already gates.
CREATE OR REPLACE VIEW app.v_doc_posting WITH (security_barrier = true) AS
 SELECT dp.document_id, p.posting_id, CASE p.portal WHEN 'lp' THEN 'lp_portal' ELSE 'gp_portal' END AS channel,
        p.posted_date, p.doc_type, p.fiscal_year, p.fiscal_quarter, dp.match
   FROM cat.doc_posting dp JOIN ref.portal_posting p ON p.posting_id = dp.posting_id;

CREATE OR REPLACE VIEW app.v_portal_kind_conflict WITH (security_barrier = true) AS
 SELECT c.document_id, c.posting_id, c.doc_kind, c.posted_kind, c.built_at FROM ops.portal_kind_conflict c;

REVOKE ALL ON ref.portal_fund_map, ref.portal_posting, ref.portal_export, cat.doc_posting, ops.portal_kind_conflict FROM PUBLIC;
REVOKE ALL ON app.v_doc_posting, app.v_portal_kind_conflict FROM PUBLIC;
GRANT SELECT ON app.v_find_x, app.v_doc_posting, app.v_portal_kind_conflict TO catalog_app;
COMMIT;
