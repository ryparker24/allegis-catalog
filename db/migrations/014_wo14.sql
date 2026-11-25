-- CAT-WO-14 · Partner Portal + LP Portal (Published Docs) folders in My Drive / "Confidential - RYAN and CECILIA only".
-- (1) label scope as data: the approved drive (R-019) plus two My Drive subtrees; "0_Empty Partner Folders" never.
-- (2) versioned folder rules (provisional) for the subtrees: kind, FY / quarter / tax year, entity, LP PII.
-- (3) R-059 switch (Ryan 2026-11-25: option A = Issued + checklist candidates; B = reference copy, not a candidate).
-- The crawl already lists all of My Drive (R-001); HND-003 already makes the Confidential folder Restricted.
-- Codes only (no partner / person names; folder names here are structural). Re-runnable.
BEGIN;

-- ---------------------------------------------------------------- (1) label scope
CREATE TABLE IF NOT EXISTS ops.label_scope (
  scope_id        text PRIMARY KEY,
  drive_name      text,                 -- a whole shared drive, or
  path_prefix     text,                 -- a My Drive subtree: folder_path equal to it or under it
  exclude_segment text,                 -- a folder name (case-insensitive) that is never in scope under this prefix
  portal_copy     boolean NOT NULL DEFAULT false,   -- R-059: files published to partners (portal copies)
  active          boolean NOT NULL DEFAULT true,
  note            text,
  ruled_by        text NOT NULL,
  CHECK ((drive_name IS NULL) <> (path_prefix IS NULL))
);
REVOKE ALL ON ops.label_scope FROM PUBLIC;
INSERT INTO ops.label_scope (scope_id, drive_name, path_prefix, exclude_segment, portal_copy, note, ruled_by) VALUES
  ('FIN', 'LIMITED - Finance', NULL, NULL, false, 'R-019: all of LIMITED - Finance', 'Ryan R-019'),
  ('PP', NULL, 'My Drive/Confidential - RYAN and CECILIA only/Partner Portal', '0_Empty Partner Folders', true,
   'CAT-WO-14: Partner Portal (Partner Documents, Fund Documents)', 'CAT-WO-14 brief 2026-11-25'),
  ('LPP', NULL, 'My Drive/Confidential - RYAN and CECILIA only/LP Portal (Published Docs)', '0_Empty Partner Folders', true,
   'CAT-WO-14: LP Portal (Published Docs)', 'CAT-WO-14 brief 2026-11-25')
ON CONFLICT (scope_id) DO UPDATE SET drive_name = EXCLUDED.drive_name, path_prefix = EXCLUDED.path_prefix,
  exclude_segment = EXCLUDED.exclude_segment, portal_copy = EXCLUDED.portal_copy, note = EXCLUDED.note, ruled_by = EXCLUDED.ruled_by;

-- folder_path is the file's folder ('My Drive/...'); a file directly in the prefix folder counts too
CREATE OR REPLACE FUNCTION ops.in_label_scope(p_drive text, p_folder text, p_portal_only boolean DEFAULT false)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM ops.label_scope s
    WHERE s.active AND (NOT p_portal_only OR s.portal_copy)
      AND ((s.drive_name IS NOT NULL AND p_drive = s.drive_name)
        OR (s.path_prefix IS NOT NULL AND (p_folder = s.path_prefix OR left(p_folder, length(s.path_prefix) + 1) = s.path_prefix || '/')
            AND (s.exclude_segment IS NULL OR NOT (lower(s.exclude_segment) = ANY (
                 SELECT lower(x) FROM unnest(string_to_array(substr(p_folder, length(s.path_prefix) + 2), '/')) x))))))
$$;

-- ---------------------------------------------------------------- (3) R-059 switch
CREATE TABLE IF NOT EXISTS ops.catalog_setting (
  key       text PRIMARY KEY,
  value     text NOT NULL,
  note      text,
  ruled_by  text NOT NULL,
  ruled_at  timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON ops.catalog_setting FROM PUBLIC;
ALTER TABLE ops.catalog_setting DROP CONSTRAINT IF EXISTS catalog_setting_r059;
ALTER TABLE ops.catalog_setting ADD CONSTRAINT catalog_setting_r059 CHECK (key <> 'R-059' OR value IN ('A', 'B'));
INSERT INTO ops.catalog_setting (key, value, note, ruled_by, ruled_at)
VALUES ('R-059', 'A', 'Portal copies: A = status Issued and checklist candidates; B = reference copies, not checklist candidates',
        'Ryan R-059', '2026-11-25T00:00:00Z')
ON CONFLICT (key) DO NOTHING;      -- a re-run never flips a setting someone changed

-- ---------------------------------------------------------------- (2) entity aliases (the code itself, upper-cased)
INSERT INTO ref.entity_alias (alias, entity_code, source, generic)
SELECT upper(entity_code), entity_code, 'cat-wo-14 code', false FROM ref.entity
WHERE entity_code IN ('ATTOTUDE', 'FUNDAM', 'LS-I', 'LS-II', 'MTV-III (PF)', 'MTV-IV (Annex)')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------- (2) folder rules (folder_path; priority 5 beats the generic path rules)
-- PD = the Partner Documents folder, LPP = the LP Portal folder (regex-escaped)
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT r.rule_id, 1, r.field, 'folder_path', replace(replace(r.pattern, '{PD}', pd), '{LPP}', lpp), r.value, 5, true, r.note, r.multi, true
FROM (VALUES
  ('^My Drive/Confidential - RYAN and CECILIA only/Partner Portal/Partner Documents',
   '^My Drive/Confidential - RYAN and CECILIA only/LP Portal \(Published Docs\)')) b(pd, lpp)
CROSS JOIN (VALUES
  -- PCAPs/<period>/<group>/...
  ('PP-KND-PCAP', 'kind', '{PD}/PCAPs/[^/]+$', 'capital_statement', false, 'CAT-WO-14: Partner Portal PCAPs/<period> -> capital statement'),
  ('PP-FY-PCAP', 'fiscal_year', '{PD}/PCAPs/((?:19|20)[0-9]{2})(?: ?Q[1-4])?$', '\1', false, 'CAT-WO-14: PCAPs/<period> -> fiscal year'),
  ('PP-FQ-PCAP', 'fiscal_quarter', '{PD}/PCAPs/(?:19|20)[0-9]{2} ?Q([1-4])$', '\1', false, 'CAT-WO-14: PCAPs/<yyyy Qn> -> quarter'),
  ('PP-FQ-PCAPY', 'fiscal_quarter', '{PD}/PCAPs/(?:19|20)[0-9]{2}$', '4', false, 'CAT-WO-14: PCAPs/<yyyy> = the year-end statements -> Q4'),
  -- K1s/<year>/...
  ('PP-KND-K1', 'kind', '{PD}/K1s/(?:19|20)[0-9]{2}$', 'k1', false, 'CAT-WO-14: K1s/<year> -> K-1'),
  ('PP-TY-K1', 'tax_year', '{PD}/K1s/((?:19|20)[0-9]{2})$', '\1', false, 'CAT-WO-14: K1s/<year> -> tax year'),
  ('PP-FY-K1', 'fiscal_year', '{PD}/K1s/((?:19|20)[0-9]{2})$', '\1', false, 'CAT-WO-14: K1s/<year> -> fiscal year (= tax year)'),
  -- Capital Calls/<fund>
  ('PP-KND-CCN', 'kind', '{PD}/Capital Calls/[^/]+$', 'capital_call_notice', false, 'CAT-WO-14: Capital Calls/<fund> -> capital call notice'),
  -- Legal Agreements/Transfer Agreements
  ('PP-KND-XFER', 'kind', '{PD}/Legal Agreements/Transfer Agreements$', 'legal_agreement', false, 'CAT-WO-14: Transfer Agreements -> legal agreement'),
  -- LP Portal (Published Docs): <yyyy-Qn>/Final PCAPs and <yyyy>/K-1s
  ('LPP-KND-PCAP', 'kind', '{LPP}/(?:19|20)[0-9]{2}-Q[1-4]/Final PCAPs$', 'capital_statement', false, 'CAT-WO-14: LP Portal <yyyy-Qn>/Final PCAPs -> capital statement'),
  ('LPP-FY-PCAP', 'fiscal_year', '{LPP}/((?:19|20)[0-9]{2})-Q[1-4]/Final PCAPs$', '\1', false, 'CAT-WO-14: LP Portal <yyyy-Qn> -> fiscal year'),
  ('LPP-FQ-PCAP', 'fiscal_quarter', '{LPP}/(?:19|20)[0-9]{2}-Q([1-4])/Final PCAPs$', '\1', false, 'CAT-WO-14: LP Portal <yyyy-Qn> -> quarter'),
  ('LPP-KND-K1', 'kind', '{LPP}/(?:19|20)[0-9]{2}/K-1s$', 'k1', false, 'CAT-WO-14: LP Portal <yyyy>/K-1s -> K-1'),
  ('LPP-TY-K1', 'tax_year', '{LPP}/((?:19|20)[0-9]{2})/K-1s$', '\1', false, 'CAT-WO-14: LP Portal <yyyy>/K-1s -> tax year'),
  ('LPP-FY-K1', 'fiscal_year', '{LPP}/((?:19|20)[0-9]{2})/K-1s$', '\1', false, 'CAT-WO-14: LP Portal <yyyy>/K-1s -> fiscal year'),
  -- handling for per-partner documents: Contains LP PII (Restricted already comes from HND-003)
  ('PP-PII', 'pii_lp_flag', '({PD}/(PCAPs|K1s|Capital Calls|Distribution Notices)|{PD}/Legal Agreements/Transfer Agreements|{LPP}/[^/]+/(Final PCAPs|K-1s))(/|$)',
   'true', false, 'CAT-WO-14: per-partner documents -> Contains LP PII')
) r(rule_id, field, pattern, value, multi, note)
ON CONFLICT (rule_id, version) DO NOTHING;

-- entity from the fund folder (literal codes; folder names are structural fund names). multi like the other entity rules.
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT 'PP-ENT-' || r.n, 1, 'entity', 'folder_path',
       -- fund folders under Partner Documents, and (for the PCAP / K-1 fund names) under LP Portal <period>/Final PCAPs | K-1s
       '(?i)^My Drive/Confidential - RYAN and CECILIA only/(?:Partner Portal/Partner Documents/' || r.parent
         || CASE WHEN r.parent LIKE '(?:PCAPs%' THEN '|LP Portal \(Published Docs\)/[^/]+/(?:Final PCAPs|K-1s)' ELSE '' END
         || ')/(' || r.names || ')$',
       r.code, 5, true, 'CAT-WO-14: fund folder -> entity ' || r.code, true, true
FROM (VALUES
  ('CC-X',    'Capital Calls',                      'Allegis X',                          'X'),
  ('CC-CIP2', 'Capital Calls',                      'CIP-II',                             'CIP-II'),
  ('CC-NL1',  'Capital Calls',                      'NL-I',                               'NL-I'),
  ('CC-NL2',  'Capital Calls',                      'NL-II',                              'NL-II'),
  -- the notices in these folders are the GP's capital calls to its members (first-page reading: the issuer on page 1 is the
  -- fund's GP entity for all four folders), so the GP entity is on them too: its roster is the one the addressee is on
  ('CC-XG',   'Capital Calls',                      'Allegis X',                          'X (GP)'),
  ('CC-CIP2G','Capital Calls',                      'CIP-II',                             'CIP-II (GP)'),
  ('CC-NL1G', 'Capital Calls',                      'NL-I',                               'NL-I (GP)'),
  ('CC-NL2G', 'Capital Calls',                      'NL-II',                              'NL-II (GP)'),
  ('MTEF5',   '(?:PCAPs|K1s)/[^/]+/[^/]+',          'MTEF-V|MTEF',                        'MTV-V (MTEF)'),
  ('MTV3PF',  '(?:PCAPs|K1s)/[^/]+/[^/]+',          'MTV-III PF',                         'MTV-III (PF)'),
  ('MTV4A',   '(?:PCAPs|K1s)/[^/]+/[^/]+',          'MTV-IV-A|MTV-IV \(A\)|MTV_IV_A_K1',  'MTV-IV (A)'),
  ('MTV4B',   '(?:PCAPs|K1s)/[^/]+/[^/]+',          'MTV-IV-B|MTV-IV \(B\)',              'MTV-IV (B)'),
  ('MTV4X',   '(?:PCAPs|K1s)/[^/]+/[^/]+',          'MTV-IV Annex',                       'MTV-IV (Annex)'),
  ('MTV5A',   '(?:PCAPs|K1s)/[^/]+/[^/]+',          'MTV-V ?\(A\)',                       'MTV-V (A)'),
  ('MTV5B',   '(?:PCAPs|K1s)/[^/]+/[^/]+',          'MTV-V ?\(B\)|MTV_V_B_K1',            'MTV-V (B)'),
  ('MTV6',    '(?:PCAPs|K1s)/[^/]+/[^/]+',          'MTV-VI',                             'MTV-VI'),
  ('FUNDAM',  '(?:PCAPs|K1s)/[^/]+/[^/]+',          'Fundamental',                        'FUNDAM'),
  ('LS1',     '(?:PCAPs|K1s)/[^/]+/[^/]+',          'LS-I',                               'LS-I'),
  ('LS2',     '(?:PCAPs|K1s)/[^/]+/[^/]+',          'LS-II',                              'LS-II'),
  ('ATTO',    '(?:PCAPs|K1s)/[^/]+/[^/]+',          'Attotude',                           'ATTOTUDE')
) r(n, parent, names, code)
ON CONFLICT (rule_id, version) DO NOTHING;
COMMIT;
