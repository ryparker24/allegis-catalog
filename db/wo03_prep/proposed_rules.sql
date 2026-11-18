-- CAT-WO-03 ruling (d), Ryan 2026-11-17: the six requirement rules, approved with amendments:
--   * K-1 counts only when matched to a partner on that entity's roster (keeps K-1s RECEIVED from portfolio companies out);
--   * side-letter rows with no candidate read "none found (not tracked in Datum)" instead of Missing;
--   * PCAP-Q is per partner per quarter, FY2025 forward.
-- Subject filters use ref.party (datum_company_kind, interest_kind, is_company_gp). Status-based "satisfied_when"
-- needs the CAT-WO-02 Part 2 Status field; until then the interim test applies (row shows "On file, not final").
ALTER TABLE ops.requirement_rule DROP CONSTRAINT IF EXISTS requirement_rule_subject_type_check;
ALTER TABLE ops.requirement_rule ADD CONSTRAINT requirement_rule_subject_type_check
  CHECK (subject_type IN ('entity_fy', 'entity_quarter', 'entity_partner', 'entity_partner_fy', 'entity_partner_quarter'));

DELETE FROM ops.requirement_rule WHERE version = 1 AND rule_id IN ('LP-SUB', 'LP-SIDE', 'GP-COMMIT', 'AUDITED-FS', 'K1-SET', 'PCAP-Q');
INSERT INTO ops.requirement_rule (rule_id, version, checklist, subtype_code, no_datum_subtype, satisfying_kinds, subject_type,
                                  entity_filter, partner_filter, period_from, satisfied_when, active, notes) VALUES
('LP-SUB', 1, 'lp_subscriptions', 'OFF-03', false, ARRAY['subscription_agreement'], 'entity_partner',
 '{"company_kind": ["fund", "spv"]}', '{"interest_kind": ["capital"], "is_company_gp": false, "match": "roster_partner"}', NULL,
 '{"stage": ["fully_executed"]}', true,
 'Ruled 2026-11-17. One GP-accepted subscription per LP per fund/SPV. Datum: required for fund and spv.'),
('LP-SIDE', 1, 'lp_subscriptions', 'OFF-05', false, ARRAY['side_letter'], 'entity_partner',
 '{"company_kind": ["fund", "spv"], "applicability": "required"}', '{"interest_kind": ["capital"], "is_company_gp": false, "match": "roster_partner"}', NULL,
 '{"stage": ["fully_executed"], "no_candidate_result": "none found (not tracked in Datum)"}', true,
 'Ruled 2026-11-17. Only entities marked Required=Yes in ops.requirement_applicability. A partner with no candidate reads "none found (not tracked in Datum)", never Missing.'),
('GP-COMMIT', 1, 'lp_subscriptions', 'OFF-04', false, ARRAY['subscription_agreement'], 'entity_partner',
 '{"company_kind": ["fund"], "plus_applicability": {"spv": "required"}}', '{"is_company_gp": true, "match": "roster_partner"}', NULL,
 '{"stage": ["fully_executed"]}', true,
 'Ruled 2026-11-17. The fund''s own GP row (legal or display name = a Datum GP company). Datum: fund required, spv conditional.'),
('AUDITED-FS', 1, 'fund_level', 'AUD-01', false, ARRAY['financial_statements'], 'entity_fy',
 '{"company_kind": ["fund", "spv"], "applicability": "required"}', NULL, 2022,
 '{"status": ["final", "issued"], "interim": "primary copy, not Wrong"}', true,
 'Ruled 2026-11-17. Datum: conditional for fund and spv (see the applicability workbook). audit_report is a candidate only.'),
('K1-SET', 1, 'fund_level', 'AUD-03', false, ARRAY['k1'], 'entity_partner_fy',
 '{"company_kind": ["fund", "spv", "gp"]}', '{"interest_kind": ["capital", "carried_interest"], "match": "roster_partner_required"}', 2025,
 '{"status": ["issued"], "interim": "primary copy, not Wrong"}', true,
 'Ruled 2026-11-17. FY2025 forward. A K-1 counts ONLY when matched to a partner on that entity''s roster (K-1s received from portfolio companies never match). Mancos: "no roster in Datum".'),
('PCAP-Q', 1, 'fund_level', NULL, true, ARRAY['capital_statement'], 'entity_partner_quarter',
 '{"company_kind": ["fund", "spv"]}', '{"interest_kind": ["capital", "carried_interest"], "match": "roster_partner"}', 2025,
 '{"status": ["final", "issued"], "interim": "primary copy, not Wrong"}', true,
 'Ruled 2026-11-17. Per partner per quarter, FY2025 forward. Catalog-only (no Datum subtype) until Datum adds one, e.g. AUD-05.');
