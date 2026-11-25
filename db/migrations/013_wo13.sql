-- CAT-WO-13 · PCAP cadence per fund (R-058, ruled by Ryan 2026-11-25: the proposed cadence).
-- ops.requirement_cadence says, per rule and entity, how often the rule expects a document:
--   quarterly  every quarter from first_period (yyyyq, e.g. 20254 = FY2025 Q4)
--   annual     Q4 only, from first_period's year
--   none       no rows at all
-- An entity with no row for a rule whose entity_filter names this table falls back to ANNUAL from the rule's first FY
-- (PCAP-Q: Q4 only, FY2025+). Codes only. Re-runnable.
BEGIN;

CREATE TABLE IF NOT EXISTS ops.requirement_cadence (
  rule_id      text NOT NULL,
  entity_code  text NOT NULL REFERENCES ref.entity (entity_code),
  cadence      text NOT NULL CHECK (cadence IN ('quarterly', 'annual', 'none')),
  first_period integer CHECK (first_period IS NULL OR (first_period BETWEEN 19901 AND 21004 AND first_period % 10 BETWEEN 1 AND 4)),
  note         text,
  ruled_by     text NOT NULL,
  ruled_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (rule_id, entity_code)
);
REVOKE ALL ON ops.requirement_cadence FROM PUBLIC;

-- R-058 seed (a re-run restores the ruled values)
INSERT INTO ops.requirement_cadence (rule_id, entity_code, cadence, first_period, note, ruled_by, ruled_at)
SELECT 'PCAP-Q', e, c, 20254, 'R-058 proposed cadence', 'Ryan R-058', '2026-11-25T00:00:00Z'::timestamptz
FROM (VALUES ('MTV-IV (A)', 'quarterly'), ('MTV-IV (B)', 'quarterly'), ('MTV-IV (Annex)', 'quarterly'),
             ('MTV-V (A)', 'quarterly'), ('MTV-V (B)', 'quarterly'), ('MTV-V (MTEF)', 'quarterly'),
             ('ACCSO', 'quarterly'), ('MTV-VI', 'quarterly'), ('LS-I', 'quarterly'), ('LS-II', 'quarterly'), ('ATTOTUDE', 'quarterly'),
             ('CIP-I', 'annual'), ('CIP-II', 'annual'), ('ASOF', 'annual'), ('CSOP', 'annual')) v(e, c)
ON CONFLICT (rule_id, entity_code) DO UPDATE
  SET cadence = EXCLUDED.cadence, first_period = EXCLUDED.first_period, note = EXCLUDED.note,
      ruled_by = EXCLUDED.ruled_by, ruled_at = EXCLUDED.ruled_at;

-- PCAP-Q v2: v1 plus entity_filter.cadence. v1 stays for history; the builder reads the highest active version.
INSERT INTO ops.requirement_rule (rule_id, version, checklist, subtype_code, no_datum_subtype, satisfying_kinds, subject_type,
                                  entity_filter, partner_filter, period_from, satisfied_when, active, notes)
SELECT rule_id, 2, checklist, subtype_code, no_datum_subtype, satisfying_kinds, subject_type,
       entity_filter || '{"cadence": "ops.requirement_cadence"}'::jsonb, partner_filter, period_from, satisfied_when, true,
       'v2 2026-11-25 (Ryan R-058, CAT-WO-13): per-entity cadence from ops.requirement_cadence (quarterly from first_period; '
       'annual = Q4 only; none = no rows); an entity with no cadence row = annual from FY' || period_from || '. v1 kept for history.'
FROM ops.requirement_rule WHERE rule_id = 'PCAP-Q' AND version = 1
ON CONFLICT (rule_id, version) DO NOTHING;

-- checklists: + cadence (appended; NULL for rules without a cadence filter)
CREATE OR REPLACE VIEW app.v_requirement WITH (security_barrier = true) AS
WITH ov AS (
  SELECT DISTINCT ON (req_key) req_key, override_id, action, file_id, note, by_email, created_at
  FROM app.requirement_override ORDER BY req_key, override_id DESC
), eff AS (
  SELECT r.*, ov.override_id AS ov_id, ov.action AS ov_action, ov.file_id AS ov_file_id, ov.note AS ov_note,
         ov.by_email AS ov_by, ov.created_at AS ov_at
  FROM ops.requirement r LEFT JOIN ov ON ov.req_key = r.req_key AND ov.action <> 'clear'
), cad_rules AS (
  SELECT DISTINCT ON (rule_id) rule_id, (entity_filter ? 'cadence') AS has_cadence
  FROM ops.requirement_rule WHERE active ORDER BY rule_id, version DESC
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
       CASE WHEN e.ov_action IS NULL AND bf.file_id IS NOT NULL THEN e.best_page END AS best_page,
       CASE WHEN cr.has_cadence THEN coalesce(rc.cadence, 'annual') END AS cadence
FROM eff e
LEFT JOIN app.v_find_x bf ON bf.file_id = e.best_file_id
LEFT JOIN app.v_find_x lf ON lf.file_id = e.ov_file_id
LEFT JOIN cad_rules cr ON cr.rule_id = e.rule_id
LEFT JOIN ops.requirement_cadence rc ON rc.rule_id = e.rule_id AND rc.entity_code = e.entity_code;

REVOKE ALL ON app.v_requirement FROM PUBLIC;
GRANT SELECT ON app.v_requirement TO catalog_app;
COMMIT;
