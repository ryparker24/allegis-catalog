-- CAT-WO-03 · 005b_wo03_seed.sql  (run as the DB owner AFTER pipeline/roster_load_wo03.py; idempotent)
-- Ruling (b): Datum subtype -> catalog kind. Ruling (d): the six requirement rules, active, version 1.
-- Refuses to run if the doc-subtype export has not been loaded (the rows reference ref.doc_subtype).
BEGIN;
DO $$
BEGIN
  IF (SELECT count(*) FROM ref.doc_subtype WHERE subtype_code IN ('OFF-03', 'OFF-04', 'OFF-05', 'AUD-01', 'AUD-03')) < 5 THEN
    RAISE EXCEPTION 'ref.doc_subtype is not loaded (OFF-03/04/05, AUD-01/03 missing): run pipeline/roster_load_wo03.py first';
  END IF;
END $$;

-- (b) role 'satisfying' = can satisfy a requirement; 'candidate' = shown as a candidate only.
-- FORM-04 / FORM-05 -> operating_agreement / operating_agreement_amendment (CAT-WO-02 RK2 ruling; supersedes the prep's
-- lpa / legal_agreement suggestion). The same mapping is to be ruled on the Datum side (WO-203).
DELETE FROM ref.doc_subtype_kind WHERE subtype_code IN ('FORM-04', 'FORM-05') AND kind IN ('lpa', 'lpa_amendment', 'legal_agreement');
INSERT INTO ref.doc_subtype_kind (subtype_code, kind, role, qualifier, ruled) VALUES
  ('OFF-03', 'subscription_agreement', 'satisfying', NULL,                                                         'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-05', 'side_letter',            'satisfying', NULL,                                                         'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-04', 'subscription_agreement', 'satisfying', 'matched to the fund''s own GP partner row',                  'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-01', 'financial_statements',   'satisfying', NULL,                                                         'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-01', 'audit_report',           'candidate',  'the opinion alone does not satisfy',                         'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-03', 'k1',                     'satisfying', 'issued K-1s only: matched to a roster partner of the entity', 'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-02', 'tax_return',        'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('AUD-04', 'quarterly_report',  'satisfying', 'annual LP report/letter',         'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-01', 'formation_filing', 'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-06', 'formation_filing', 'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-07', 'formation_filing', 'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-02', 'lpa',              'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-03', 'lpa_amendment',    'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('FORM-04', 'operating_agreement',           'satisfying', NULL,                 'CAT-WO-02 RK2 2026-11-17'),
  ('FORM-05', 'operating_agreement_amendment', 'satisfying', NULL,                 'CAT-WO-02 RK2 2026-11-17'),
  ('OFF-01', 'ppm',               'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-02', 'regulatory_filing', 'satisfying', 'Form D',                          'CAT-WO-03 (b) 2026-11-17'),
  ('POL-04', 'regulatory_filing', 'satisfying', 'Form ADV',                        'CAT-WO-03 (b) 2026-11-17'),
  ('OFF-07', 'w9_w8',             'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('FIN-01', 'loc_agreement',     'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('GOV-02', 'minutes',           'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('GOV-02', 'board_consent',     'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('POL-01', 'policy',            'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('POL-02', 'policy',            'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17'),
  ('POL-03', 'policy',            'satisfying', NULL,                              'CAT-WO-03 (b) 2026-11-17')
ON CONFLICT (subtype_code, kind) DO UPDATE SET role = EXCLUDED.role, qualifier = EXCLUDED.qualifier, ruled = EXCLUDED.ruled;

-- (d) the six rules, ruled 2026-11-17 with three amendments (K-1 only when matched to the entity's roster; side letters
-- "none found (not tracked in Datum)"; PCAP per partner per quarter from FY2025). Inserted once; a later change is a
-- new version, never an edit of version 1.
INSERT INTO ops.requirement_rule (rule_id, version, checklist, subtype_code, no_datum_subtype, satisfying_kinds, subject_type,
                                  entity_filter, partner_filter, period_from, satisfied_when, active, notes) VALUES
('LP-SUB', 1, 'lp_subscriptions', 'OFF-03', false, ARRAY['subscription_agreement'], 'entity_partner',
 '{"company_kind": ["fund", "spv"]}', '{"interest_kind": ["capital"], "is_company_gp": false}', NULL,
 '{"stage": ["fully_executed"]}', true,
 'Ruled 2026-11-17. One GP-accepted subscription per LP per fund/SPV. Datum: required for fund and spv.'),
('LP-SIDE', 1, 'lp_subscriptions', 'OFF-05', false, ARRAY['side_letter'], 'entity_partner',
 '{"company_kind": ["fund", "spv"], "applicability": "required"}', '{"interest_kind": ["capital"], "is_company_gp": false}', NULL,
 '{"stage": ["fully_executed"], "no_candidate_result": "none_found"}', true,
 'Ruled 2026-11-17. Entities with Required = Yes only. No candidate reads "none found (not tracked in Datum)", never Missing.'),
('GP-COMMIT', 1, 'lp_subscriptions', 'OFF-04', false, ARRAY['subscription_agreement'], 'entity_partner',
 '{"company_kind": ["fund"], "plus_applicability": ["spv"]}', '{"is_company_gp": true}', NULL,
 '{"stage": ["fully_executed"]}', true,
 'Ruled 2026-11-17. The fund''s own GP row. Datum: fund required, spv conditional (applicability).'),
('AUDITED-FS', 1, 'fund_level', 'AUD-01', false, ARRAY['financial_statements'], 'entity_fy',
 '{"company_kind": ["fund", "spv"], "applicability": "required"}', NULL, 2022,
 '{"status": ["final", "issued"]}', true,
 'Ruled 2026-11-17. Entities with Required = Yes. audit_report is a candidate only.'),
('K1-SET', 1, 'fund_level', 'AUD-03', false, ARRAY['k1'], 'entity_partner_fy',
 '{"company_kind": ["fund", "spv", "gp"]}', '{"interest_kind": ["capital", "carried_interest"]}', 2025,
 '{"status": ["issued"]}', true,
 'Ruled 2026-11-17. FY2025 forward. A K-1 counts ONLY when matched to a partner on that entity''s roster.'),
('PCAP-Q', 1, 'fund_level', NULL, true, ARRAY['capital_statement'], 'entity_partner_quarter',
 '{"company_kind": ["fund", "spv"]}', '{"interest_kind": ["capital", "carried_interest"]}', 2025,
 '{"status": ["final", "issued"]}', true,
 'Ruled 2026-11-17. Per partner per quarter, FY2025 forward. Catalog-only (no Datum subtype) until Datum adds one.')
ON CONFLICT (rule_id, version) DO NOTHING;
COMMIT;
