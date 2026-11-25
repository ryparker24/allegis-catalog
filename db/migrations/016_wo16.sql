-- CAT-WO-16 · bank statement entity from the account's last 4 digits (rule BANK-L4).
-- ref.bank_account is loaded from Ryan's map by `pipeline/bank_wo16.py --load-map <csv>` (the digits stay out of the repo).
-- BANK-L4 signals (cat.file_signal source 'bank', field entity) are re-added after every derive (apply_derive_wo02); a
-- last-4 that contradicts an existing machine entity is never written as an entity: it is recorded as the document's
-- content entity, so the Content disagrees lane shows it. A person's entity is never touched. Re-runnable.
BEGIN;
CREATE TABLE IF NOT EXISTS ref.bank_account (
  last4        text NOT NULL CHECK (last4 ~ '^[0-9]{4}$'),
  entity_code  text NOT NULL REFERENCES ref.entity (entity_code),
  ryan_label   text,
  source       text NOT NULL DEFAULT 'Ryan 2026-11-24',
  note         text,
  loaded_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (last4, entity_code)
);
REVOKE ALL ON ref.bank_account FROM PUBLIC;

-- first-page reads for BANK-L4 (codes only: the entity found, never the page text or the digits)
CREATE TABLE IF NOT EXISTS ops.bank_page_read (
  document_id  bigint PRIMARY KEY REFERENCES cat.document (document_id) ON DELETE CASCADE,
  version_key  text,
  outcome      text NOT NULL,          -- ok | no_match | multi | download_error | open_error | too_large | skipped_format
  codes        text[],                 -- entity codes found on page 1 (from ref.bank_account), never digits
  read_at      timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON ops.bank_page_read FROM PUBLIC;

ALTER TABLE cat.file_signal DROP CONSTRAINT IF EXISTS file_signal_source_check;
ALTER TABLE cat.file_signal ADD CONSTRAINT file_signal_source_check CHECK (source = ANY (ARRAY['name'::text, 'path'::text, 'drive'::text, 'mime'::text, 'bank'::text]));

-- the codes in the map that had no self alias on main (v_file_entity resolves signal values through ref.entity_alias)
INSERT INTO ref.entity_alias (alias, entity_code, source, generic)
SELECT upper(entity_code), entity_code, 'cat-wo-16 code', false FROM ref.entity
WHERE entity_code IN ('MTV-III (PF)', 'MTV-IV (Annex)')
ON CONFLICT DO NOTHING;

INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
VALUES ('BANK-L4', 1, 'entity', 'content',
        '{"kinds": ["bank_stmt", "wire_confirmation"], "no_kind_folder": "03-Cash", "order": ["name", "path", "page1"], "mode": "apply"}',
        'BANK-L4', 5, true,
        'CAT-WO-16: the account''s last 4 digits (ref.bank_account) as a whole 4-digit token after an account cue (x1234, ****1234, '
        '"ending 1234", acct...1234) -> entity; file name, then folder path, then page 1. A person''s entity is never touched; a '
        'contradiction with a machine entity goes to Content disagrees.', true, false)   -- not provisional: pages --seed-rules never removes it
ON CONFLICT (rule_id, version) DO NOTHING;
COMMIT;
