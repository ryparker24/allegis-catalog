-- CAT-WO-03.1 (Ryan 2026-11-19, amendment to ruling 1): ONE kind for the audited statements, named "Audited Financial
-- Statements" ("audit report" is only the auditor's opinion). The Drive Kind choice "Audit Report" is renamed in place
-- (same choice id 33143e5d03, published by Ryan in Label manager); the catalog code follows:
--   audit_report -> audited_financial_statements   (documents, kind rule KND-025, AUD-01)
-- Run AFTER Ryan's ruling on the proposed moves (emails / workbooks), and with labels_schema.json from --read-published.
-- Idempotent.
BEGIN;

-- documents: machine and person values (a person's "Audit Report" IS the renamed choice on the label)
UPDATE cat.document SET kind_auto = 'audited_financial_statements', updated_at = now() WHERE kind_auto = 'audit_report';
UPDATE cat.document SET kind_confirmed = 'audited_financial_statements', updated_at = now() WHERE kind_confirmed = 'audit_report';

-- the label read-back snapshot holds kind codes: rename there too, so the next read-back doesn't mistake the rename
-- for a person's edit (machine and live snapshots alike)
UPDATE ops.label_state SET machine = jsonb_set(machine, '{kind}', '"audited_financial_statements"')
 WHERE machine->>'kind' = 'audit_report';
UPDATE ops.label_state SET live = jsonb_set(live, '{kind}', '"audited_financial_statements"')
 WHERE live->>'kind' = 'audit_report';

-- kind rule: KND-025 v2 sets the renamed code (same pattern)
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT rule_id, 2, field, applies_to, pattern, 'audited_financial_statements', priority, true,
       'CAT-WO-03.1: audit_report renamed audited_financial_statements (Ryan)', multi, provisional
FROM ops.decomposition_rule WHERE rule_id = 'KND-025' AND version = 1
ON CONFLICT (rule_id, version) DO NOTHING;
UPDATE ops.decomposition_rule SET active = false WHERE rule_id = 'KND-025' AND version = 1 AND active;

-- AUD-01: the old candidate row goes (audited_financial_statements is already the one satisfying kind, from 006)
DELETE FROM ref.doc_subtype_kind WHERE subtype_code = 'AUD-01' AND kind = 'audit_report';

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM cat.document WHERE 'audit_report' IN (kind_auto, kind_confirmed)) THEN
    RAISE EXCEPTION 'audit_report still on a document';
  END IF;
END $$;
COMMIT;
