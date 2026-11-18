-- CAT-WO-03 PREP (items 1-2). Applied to a THROWAWAY branch only; not a release migration yet.
-- LP names live only in ref.party (and later ref.party_alias). No grant to catalog_app: the app will read them
-- through a dedicated view in the build phase (item 6 guard: "catalog_app reads ref.party only through its view").

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
  datum_company_name  text NOT NULL,                       -- the fund / GP / SPV legal name (an entity, not an LP)
  entity_code         text REFERENCES ref.entity (entity_code), -- NULL = unmapped: reported, never guessed
  partner_code        text NOT NULL,
  relationship_code   text NOT NULL,
  display_name        text NOT NULL,                       -- LP name: never logged, labelled or exported
  legal_name          text NOT NULL,                       -- LP name: never logged, labelled or exported
  legal_name_status   text,
  interest_kind       text NOT NULL CHECK (interest_kind IN ('capital', 'carried_interest')),
  is_company_gp       boolean NOT NULL,                    -- partner legal name = a Datum GP company's name (the fund's own GP)
  commitment_date     date,
  active_from         date,
  active_to           date,
  active_from_basis   text,
  active_to_basis     text,
  export_date         date NOT NULL,
  PRIMARY KEY (datum_company_code, partner_code, relationship_code)
);
CREATE INDEX IF NOT EXISTS party_entity ON ref.party (entity_code);

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
  datum_document_kind  text,                                -- Datum's own mapping (blank until WO-203 is ruled)
  export_date          date NOT NULL
);

-- Item 2 (proposed, empty until Ryan rules): per-entity answers for Datum's "conditional" applicability.
CREATE TABLE IF NOT EXISTS ops.requirement_applicability (
  entity_code   text NOT NULL REFERENCES ref.entity (entity_code),
  subtype_code  text NOT NULL REFERENCES ref.doc_subtype (subtype_code),
  required      boolean NOT NULL,
  note          text,
  ruled_by      text NOT NULL,
  ruled_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_code, subtype_code)
);

-- Item 2 (proposed rows go in for Ryan's ruling with active = false; nothing applies until ruled).
CREATE TABLE IF NOT EXISTS ops.requirement_rule (
  rule_id          text NOT NULL,
  version          integer NOT NULL,
  checklist        text NOT NULL CHECK (checklist IN ('lp_subscriptions', 'fund_level')),
  subtype_code     text REFERENCES ref.doc_subtype (subtype_code),   -- NULL only for the flagged catalog-only PCAP rule
  no_datum_subtype boolean NOT NULL DEFAULT false,
  satisfying_kinds text[] NOT NULL,
  subject_type     text NOT NULL CHECK (subject_type IN ('entity_fy', 'entity_quarter', 'entity_partner', 'entity_partner_fy')),
  entity_filter    jsonb NOT NULL,          -- e.g. {"company_kind": ["fund","spv"]} or {"entity_codes": [...]}
  partner_filter   jsonb,                   -- e.g. {"interest_kind": "capital", "is_company_gp": false}
  period_from      integer,                 -- first fiscal year checked (K-1 v1: 2025)
  satisfied_when   jsonb NOT NULL,          -- {"stage": ["fully_executed"]} or {"status": ["final","issued"]}
  active           boolean NOT NULL DEFAULT false,
  notes            text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (rule_id, version),
  CHECK (subtype_code IS NOT NULL OR no_datum_subtype)
);

REVOKE ALL ON ref.datum_export, ref.party, ref.doc_subtype, ops.requirement_applicability, ops.requirement_rule FROM PUBLIC;
