-- CAT-WO-03 ruling (b), Ryan 2026-11-17: Datum document subtype -> catalog kind, approved as proposed.
-- role 'satisfying' = can satisfy a requirement; 'candidate' = shown as a candidate only.
-- The same mapping is to be ruled on the Datum side (WO-203) so both systems agree.
CREATE TABLE IF NOT EXISTS ref.doc_subtype_kind (
  subtype_code text NOT NULL REFERENCES ref.doc_subtype (subtype_code),
  kind         text NOT NULL,
  role         text NOT NULL DEFAULT 'satisfying' CHECK (role IN ('satisfying', 'candidate')),
  qualifier    text,          -- extra condition, e.g. 'issued K-1s only (matched to a roster partner)'
  ruled        text NOT NULL,
  PRIMARY KEY (subtype_code, kind)
);
REVOKE ALL ON ref.doc_subtype_kind FROM PUBLIC;

INSERT INTO ref.doc_subtype_kind (subtype_code, kind, role, qualifier, ruled) VALUES
  -- checklist subtypes
  ('OFF-03', 'subscription_agreement', 'satisfying', NULL,                                                    'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-05', 'side_letter',            'satisfying', NULL,                                                    'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-04', 'subscription_agreement', 'satisfying', 'matched to the fund''s own GP partner row',             'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-01', 'financial_statements',   'satisfying', NULL,                                                    'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-01', 'audit_report',           'candidate',  'the opinion alone does not satisfy',                    'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-03', 'k1',                     'satisfying', 'issued K-1s only: matched to a roster partner of the entity', 'CAT-WO-03 (b) 2026-11-17'),
  -- other subtypes (agreed mapping; no checklist yet)
  ('AUD-02', 'tax_return',        'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-04', 'quarterly_report',  'satisfying', 'annual LP report/letter','CAT-WO-03 (b) 2026-11-17'),
  ('FORM-01', 'formation_filing', 'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-06', 'formation_filing', 'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-07', 'formation_filing', 'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-02', 'lpa',              'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-03', 'lpa_amendment',    'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-04', 'lpa',              'satisfying', 'operating agreement',    'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-04', 'legal_agreement',  'candidate',  'operating agreement',    'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-05', 'lpa_amendment',    'satisfying', 'operating agreement amendment', 'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-05', 'legal_agreement',  'candidate',  'operating agreement amendment', 'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-01', 'ppm',               'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-02', 'regulatory_filing', 'satisfying', 'Form D',                 'CAT-WO-03 (b) 2026-11-17'),
  ('POL-04', 'regulatory_filing', 'satisfying', 'Form ADV',               'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-07', 'w9_w8',             'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('FIN-01', 'loc_agreement',     'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('GOV-02', 'minutes',           'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('GOV-02', 'board_consent',     'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('POL-01', 'policy',            'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('POL-02', 'policy',            'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17'),
  ('POL-03', 'policy',            'satisfying', NULL,                     'CAT-WO-03 (b) 2026-11-17')
ON CONFLICT (subtype_code, kind) DO UPDATE SET role = EXCLUDED.role, qualifier = EXCLUDED.qualifier, ruled = EXCLUDED.ruled;
-- PCAP stays catalog-only (capital_statement, rule PCAP-Q flagged no_datum_subtype) until Datum adds a subtype.
