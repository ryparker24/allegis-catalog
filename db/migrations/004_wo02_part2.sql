-- CAT-WO-02 Part 2 · 004_wo02_part2.sql   (run as the DB owner; idempotent; THROWAWAY BRANCH until release)
-- R-021 Parties, R-022 Status, item 7 read-back / re-sync state, item 8 app edits.
-- Codes only. Nothing here reads ref.lp or ref.person. LP-level receiving codes beyond 'LP' need Ryan's list.

BEGIN;

-- ---------------------------------------------------------------- document fields (auto = rules, confirmed = a person)
ALTER TABLE cat.document
    ADD COLUMN IF NOT EXISTS issuing_entity_auto          text,
    ADD COLUMN IF NOT EXISTS issuing_entity_confirmed     text,
    ADD COLUMN IF NOT EXISTS receiving_entities_auto      text[],
    ADD COLUMN IF NOT EXISTS receiving_entities_confirmed text[],
    ADD COLUMN IF NOT EXISTS parties_rule                 text,
    ADD COLUMN IF NOT EXISTS status_auto                  text,
    ADD COLUMN IF NOT EXISTS status_confirmed             text,
    ADD COLUMN IF NOT EXISTS status_rule                  text,
    ADD COLUMN IF NOT EXISTS issued_date_auto             date,
    ADD COLUMN IF NOT EXISTS issued_date_confirmed        date,
    ADD COLUMN IF NOT EXISTS entities_confirmed           text[],
    ADD COLUMN IF NOT EXISTS portcos_confirmed            text[];

-- NOT VALID + VALIDATE: the scan of ~200k rows runs without holding the table's exclusive lock (coder review)
-- DROP first so a re-run replaces an older body (review: duplicate_object kept a stale one)
ALTER TABLE cat.document DROP CONSTRAINT IF EXISTS document_status_codes;
ALTER TABLE cat.document DROP CONSTRAINT IF EXISTS document_parties_codes;
DO $$ BEGIN
    ALTER TABLE cat.document ADD CONSTRAINT document_status_codes CHECK (
        coalesce(status_auto, 'draft') IN ('draft','in_review','final','issued','superseded') AND
        coalesce(status_confirmed, 'draft') IN ('draft','in_review','final','issued','superseded')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- R-021: Parties hold CODES only (entity / portco codes, 'LP', 'EXTERNAL'), never a name (CISO review)
DO $$ BEGIN
    ALTER TABLE cat.document ADD CONSTRAINT document_parties_codes CHECK (
        coalesce(issuing_entity_auto, 'X') ~ '^[A-Za-z0-9()_ -]{1,40}$' AND
        coalesce(issuing_entity_confirmed, 'X') ~ '^[A-Za-z0-9()_ -]{1,40}$' AND
        coalesce(array_to_string(receiving_entities_auto, ','), 'X') ~ '^[A-Za-z0-9()_ ,-]+$' AND
        coalesce(array_to_string(receiving_entities_confirmed, ','), 'X') ~ '^[A-Za-z0-9()_ ,-]+$' AND
        length(coalesce(array_to_string(receiving_entities_auto, ','), '')) <= 400 AND
        length(coalesce(array_to_string(receiving_entities_confirmed, ','), '')) <= 400) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE cat.document VALIDATE CONSTRAINT document_status_codes;
ALTER TABLE cat.document VALIDATE CONSTRAINT document_parties_codes;

-- ---------------------------------------------------------------- item 7 · label state per file (the read-back's memory)
-- machine = the values the machine last wrote. On first sight of a file it is seeded from the LIVE labels (the bulk
-- run wrote them; item 0.3 measured 0 drift), so stale catalog values are never mistaken for a person's edit.
-- live = what the last read-back saw on the file.
-- person_fields = fields a person owns (Catalog Review = Confirmed, or live differs from the machine write):
-- the re-sync never overwrites them.
CREATE TABLE IF NOT EXISTS ops.label_state (
    file_id         text PRIMARY KEY,
    machine         jsonb,
    machine_at      timestamptz,
    live            jsonb,
    live_at         timestamptz,
    review_status   text,
    reviewed_by_set boolean NOT NULL DEFAULT false,
    person_fields   text[]  NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ops.label_sync_run (
    run_id              text PRIMARY KEY,
    mode                text NOT NULL CHECK (mode IN ('readback', 'resync')),
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    applied             boolean NOT NULL DEFAULT false,
    files_read          integer NOT NULL DEFAULT 0,
    confirmed_by_person integer NOT NULL DEFAULT 0,
    resynced            integer NOT NULL DEFAULT 0,
    skipped_person      integer NOT NULL DEFAULT 0,
    errors              integer NOT NULL DEFAULT 0,
    by_field            jsonb,
    notes               text
);

-- ---------------------------------------------------------------- item 8 · app edits are recorded in the review log
ALTER TABLE app.review_event ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'review';
ALTER TABLE app.review_event ADD COLUMN IF NOT EXISTS edits  jsonb;
DO $$ BEGIN
    ALTER TABLE app.review_event ADD CONSTRAINT review_event_source CHECK (source IN ('review', 'find_single', 'find_bulk', 'review_edit'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- A bulk edit is 'edited': a person changed a field but did not review the file, so it must not take the file out
-- of the Review queue (only 'confirmed' / 'wrong' do; the queue view is updated after the CAT-WO-01.1 rebase).
ALTER TABLE app.review_event DROP CONSTRAINT IF EXISTS review_event_status_check;
ALTER TABLE app.review_event ADD CONSTRAINT review_event_status_check CHECK (status IN ('confirmed', 'wrong', 'edited'));
DO $$ BEGIN
    ALTER TABLE app.review_event ADD CONSTRAINT review_event_edits_size CHECK (edits IS NULL OR octet_length(edits::text) <= 4000);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------- Find over v_find + the WO-02 fields (v_find itself unchanged)
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
       coalesce(d.issued_date_confirmed, d.issued_date_auto)                AS issued_date
FROM app.v_find v                       -- secret tier already excluded in v_find
LEFT JOIN cat.document d ON d.document_id = v.document_id;

COMMIT;

BEGIN;
GRANT SELECT ON app.v_find_x TO catalog_app;
COMMIT;

-- ---------------------------------------------------------------- fiscal-year derivation fixes (from CAT-WO-03 prep, Ryan-approved)
-- Released with Part 2's derive + resync. Both take effect at the next `drive_crawl.py derive` (ops.apply_rules).
BEGIN;
-- (2) deterministic winner: two signals tied on priority / distance / source used to pick a different winner per
--     execution (the same diff gave 774 / 775 / 776). A final key (rule_id, value) makes the winner stable.
CREATE OR REPLACE VIEW cat.v_file_best AS
 SELECT DISTINCT ON (s.file_id, s.field) s.file_id,
    s.field,
    s.value,
    s.rule_id,
    s.rule_version,
    s.source,
    s.matched
   FROM cat.file_signal s
     JOIN ops.decomposition_rule r ON r.rule_id = s.rule_id AND r.version = s.rule_version
  WHERE NOT r.multi
  ORDER BY s.file_id, s.field, s.priority, s.distance, (s.source = 'name'::text) DESC, s.rule_id, s.value;

-- (1) a folder's year when it sits before / after Tax, Taxes, Tax Return(s), Audit or K-1 inside the name
--     ("<fund> 2012 K-1s", "<x> 2006 Taxes", "Tax 2014"); PER-001/003/008 read it only at the start of the name.
--     Priority 10 like PER-001/003, so the NEAREST folder still wins on distance. Capture = the year only.
--     NOTE: the prep file named the second rule PER-010, but PER-010 v1 already exists on main (a fiscal_quarter
--     rule), so its ON CONFLICT DO NOTHING would have skipped it silently. It is PER-014 here (free on main).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ops.decomposition_rule WHERE rule_id IN ('PER-009', 'PER-014') AND field <> 'fiscal_year') THEN
        RAISE EXCEPTION 'PER-009 / PER-014 already used by a different rule: pick free rule ids';
    END IF;
END $$;
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional) VALUES
 ('PER-009', 1, 'fiscal_year', 'path_segment',
  $re$(?i)(?:^|[^0-9])((?:19|20)[0-9]{2})[ _-]*(?:K-?1'?s?|Tax|Taxes|Tax Returns?|Audit)\y$re$, $v$\1$v$, 10, true,
  'CAT-WO-02 (from CAT-WO-03 prep): year inside a folder name, before Tax/Taxes/Audit/K-1', false, false),
 ('PER-014', 1, 'fiscal_year', 'path_segment',
  $re$(?i)\y(?:Tax|Taxes|Audit|K-?1'?s?)[ _-]+((?:19|20)[0-9]{2})(?:[^0-9]|$)$re$, $v$\1$v$, 10, true,
  'CAT-WO-02 (from CAT-WO-03 prep, was PER-010): year after Tax/Taxes/Audit/K-1 in a folder name', false, false)
ON CONFLICT (rule_id, version) DO NOTHING;

-- (T1 ruling, Ryan) a state partnership return (CA 568, NY IT-204, NJ-1065 ...) is a tax_return: KND-024 wins over
--     KND-041 (both were priority 25 and tied) by moving to priority 24 (v2; v1 is kept for history).
--     Exceptions checked before KND-024:
--       state K-1s ('Sch K-1', 'Schedule K-1', 'K-1') -> k1: already KND-001 at priority 20, no new rule needed;
--       payment vouchers / extensions -> tax_form: KND-057 at priority 23. Form numbers 3537 / 3538 / 7004 / 8868
--       always; 'voucher' / 'extension' only next to a tax word or a return number (a fund-term or lease
--       'extension' is not a tax form). Name rules run in Python (drive_crawl.derive), so the lookahead is fine.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ops.decomposition_rule WHERE rule_id = 'KND-057' AND value <> 'tax_form') THEN
        RAISE EXCEPTION 'KND-057 already used by a different rule: pick a free rule id';
    END IF;
END $$;
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT 'KND-024', 2, field, applies_to, pattern, value, 24, true,
       'CAT-WO-02 T1 ruling: state partnership returns are tax_return; beats KND-041 (25)', multi, provisional
FROM ops.decomposition_rule WHERE rule_id = 'KND-024' AND version = 1
ON CONFLICT (rule_id, version) DO NOTHING;
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional) VALUES
 ('KND-057', 1, 'kind', 'name',
  $re$(?i)\y(3537|3538|7004|8868)\y|^(?=.*(\ytax|\y(1065|1120S?|990|568|565|1040|IT-?204|FTB)\y)).*\y(vouchers?|extensions?)\y$re$,
  'tax_form', 23, true, 'CAT-WO-02 T1 ruling: payment vouchers / extensions are tax_form, checked before KND-024', false, false)
ON CONFLICT (rule_id, version) DO NOTHING;

-- (T1 ruling, round 3) financial_statements wins over workpaper. Both KNX-006 and KND-044 are priority 40 (not 25 as
--     the recommendation assumed), so KNX-006 v2 goes to 39: it beats workpaper and nothing else. Priority 24 would
--     also have put financial_statements above every kind rule at 25-39 (see the handoff for that count).
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT 'KNX-006', 2, field, applies_to, pattern, value, 39, true,
       'CAT-WO-02 T1 ruling: financial_statements over workpaper (KND-044, 40)', multi, provisional
FROM ops.decomposition_rule WHERE rule_id = 'KNX-006' AND version = 1
ON CONFLICT (rule_id, version) DO NOTHING;

-- (RK1, approved) KND-049 '(?i)pledge (agreement|fin)' also matched the MTV pledge vehicles' "Pledge Fin(ancial)
--     Report" names and set loc_agreement on all 27 labelled hits. v2 keeps only 'pledge agreement'; the reports then
--     reach RK1Q / RK1F in pipeline/derive_wo02.py (quarterly_report / financial_statements).
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT 'KND-049', 2, field, applies_to, '(?i)pledge agreement', value, priority, true,
       'CAT-WO-02 RK1: pledge agreement only (the fin branch caught pledge-vehicle financial reports)', multi, provisional
FROM ops.decomposition_rule WHERE rule_id = 'KND-049' AND version = 1
ON CONFLICT (rule_id, version) DO NOTHING;

-- (RK2, review) the two new kinds replace lpa / lpa_amendment, which are executable kinds: so are they (signed
--     agreements keep their Stage). ops.build_documents and apply_derive_wo02.py read this list.
INSERT INTO ref.vocab (list_name, code, label, parent_code, synonyms, sort, active)
SELECT 'executable_kind', v.code, v.code, NULL, '{}', (SELECT coalesce(max(sort), 0) FROM ref.vocab WHERE list_name = 'executable_kind') + v.n, true
FROM (VALUES ('operating_agreement', 1), ('operating_agreement_amendment', 2)) v(code, n)
WHERE NOT EXISTS (SELECT 1 FROM ref.vocab x WHERE x.list_name = 'executable_kind' AND x.code = v.code);

-- (CYBER-II, Ryan) CYBER-II is not a real entity; "AllegisCyber II" is CIP-II (Cyber Innovation Partners II).
--     ENT-018 / ENT-018P v2 point to CIP-II; the CYBER-II alias row goes and the entity is made inactive (kept, not
--     deleted, for history). The Drive Entity choice is DISABLED (not deleted) at the Part 2 label publish.
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT rule_id, 2, field, applies_to, pattern, 'CIP-II', priority, true,
       'CAT-WO-02: AllegisCyber II is CIP-II (CYBER-II retired)', multi, provisional
FROM ops.decomposition_rule WHERE rule_id IN ('ENT-018', 'ENT-018P') AND version = 1
ON CONFLICT (rule_id, version) DO NOTHING;
DELETE FROM ref.entity_alias WHERE alias = 'CYBER-II' AND entity_code = 'CYBER-II';
UPDATE ref.entity SET active = false,
       notes = concat_ws(' · ', nullif(notes, ''), 'CAT-WO-02: retired, not a real entity; AllegisCyber II = CIP-II')
WHERE entity_code = 'CYBER-II' AND active IS DISTINCT FROM false;

-- (Ryan, round 4) spelled-out "Cyber Innovation Partners II" (name or folder) -> CIP-II. ENT-002 only knows "CIP II".
--     \y after II keeps "Cyber Innovation Partners III" out. Same priority / multi as ENT-002.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ops.decomposition_rule WHERE rule_id IN ('ENT-020', 'ENT-020P') AND value <> 'CIP-II') THEN
        RAISE EXCEPTION 'ENT-020 / ENT-020P already used by a different rule: pick free rule ids';
    END IF;
END $$;
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
SELECT CASE r.applies_to WHEN 'name' THEN 'ENT-020' ELSE 'ENT-020P' END, 1, r.field, r.applies_to,
       '(?i)\yCyber Innovation Partners,? II\y', 'CIP-II', r.priority, true,
       'CAT-WO-02: spelled-out Cyber Innovation Partners II (Ryan)', r.multi, false
FROM ops.decomposition_rule r WHERE r.rule_id IN ('ENT-002', 'ENT-002P') AND r.version = 1
ON CONFLICT (rule_id, version) DO NOTHING;

-- (Ryan, round 5) legal-name entity rules from the Datum roster's company_name (approved: ASOF, CSOP, NL-I, NL-II, X,
--     MTV-VI; CIP-I and every GP rule held). Legal name without its L.P. / LLC suffix, whole words, never followed by
--     another fund number (II, III, 2 ...); a year (2019) is allowed. ENT-0nn = file name, ENT-0nnP = any folder name.
--     Same priority / multi as ENT-002. Patterns are valid in Python re and Postgres ARE (checked on the branch).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ops.decomposition_rule WHERE rule_id IN ('ENT-021', 'ENT-021P', 'ENT-022', 'ENT-022P', 'ENT-023', 'ENT-023P', 'ENT-024', 'ENT-024P', 'ENT-025', 'ENT-025P', 'ENT-026', 'ENT-026P')
               AND (rule_id, value) NOT IN (('ENT-021', 'ASOF'), ('ENT-021P', 'ASOF'), ('ENT-022', 'CSOP'), ('ENT-022P', 'CSOP'), ('ENT-023', 'NL-I'), ('ENT-023P', 'NL-I'), ('ENT-024', 'NL-II'), ('ENT-024P', 'NL-II'), ('ENT-025', 'X'), ('ENT-025P', 'X'), ('ENT-026', 'MTV-VI'), ('ENT-026P', 'MTV-VI'))) THEN
        RAISE EXCEPTION 'ENT-021..026 already used by different rules: pick free rule ids';
    END IF;
END $$;
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional) VALUES
 ('ENT-021', 1, 'entity', 'name', $re$(?i)(?<![A-Za-z0-9])Allegis[^A-Za-z0-9]*Special[^A-Za-z0-9]*Opportunities[^A-Za-z0-9]*Fund(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'ASOF', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-021P', 1, 'entity', 'path_segment', $re$(?i)(?<![A-Za-z0-9])Allegis[^A-Za-z0-9]*Special[^A-Za-z0-9]*Opportunities[^A-Za-z0-9]*Fund(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'ASOF', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-022', 1, 'entity', 'name', $re$(?i)(?<![A-Za-z0-9])Cyber[^A-Za-z0-9]*Special[^A-Za-z0-9]*Opportunity[^A-Za-z0-9]*Partners(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'CSOP', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-022P', 1, 'entity', 'path_segment', $re$(?i)(?<![A-Za-z0-9])Cyber[^A-Za-z0-9]*Special[^A-Za-z0-9]*Opportunity[^A-Za-z0-9]*Partners(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'CSOP', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-023', 1, 'entity', 'name', $re$(?i)(?<![A-Za-z0-9])Allegis[^A-Za-z0-9]*NL[^A-Za-z0-9]*Capital(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'NL-I', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-023P', 1, 'entity', 'path_segment', $re$(?i)(?<![A-Za-z0-9])Allegis[^A-Za-z0-9]*NL[^A-Za-z0-9]*Capital(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'NL-I', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-024', 1, 'entity', 'name', $re$(?i)(?<![A-Za-z0-9])AllegisNL[^A-Za-z0-9]*Capital[^A-Za-z0-9]*II(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'NL-II', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-024P', 1, 'entity', 'path_segment', $re$(?i)(?<![A-Za-z0-9])AllegisNL[^A-Za-z0-9]*Capital[^A-Za-z0-9]*II(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'NL-II', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-025', 1, 'entity', 'name', $re$(?i)(?<![A-Za-z0-9])Allegis[^A-Za-z0-9]*Capital[^A-Za-z0-9]*X(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'X', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-025P', 1, 'entity', 'path_segment', $re$(?i)(?<![A-Za-z0-9])Allegis[^A-Za-z0-9]*Capital[^A-Za-z0-9]*X(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'X', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-026', 1, 'entity', 'name', $re$(?i)(?<![A-Za-z0-9])Allegis[^A-Za-z0-9]*MTV[^A-Za-z0-9]*VI(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'MTV-VI', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false),
 ('ENT-026P', 1, 'entity', 'path_segment', $re$(?i)(?<![A-Za-z0-9])Allegis[^A-Za-z0-9]*MTV[^A-Za-z0-9]*VI(?![A-Za-z0-9])(?![^A-Za-z0-9]*(i{1,3}|iv|vi{0,3}|ix|x|[0-9])(?![A-Za-z0-9]))$re$, 'MTV-VI', 30, true, 'CAT-WO-02: legal name (Datum roster), Ryan round 5', true, false)
ON CONFLICT (rule_id, version) DO NOTHING;
COMMIT;

-- ---------------------------------------------------------------- item 6 / item 8 · Review queue (after the CAT-WO-01.1 rebase)
-- (a) only 'confirmed' / 'wrong' take a file out of the queue: a bulk edit ('edited') changed a field but nobody reviewed
--     the file. v_find is the live definition with that one change; security_barrier is restated (CREATE OR REPLACE
--     without WITH would drop it - caught on the branch) and grants are unchanged.
-- (b) R-022 "Status unknown" lane: a non-executable kind with no Status. Shown after "Signing status unknown" in the
--     lane list; ranked LAST in the default order (26k labelled files would otherwise bury the smaller lanes).
-- (c) counts: + status_unknown; reviewed_today / reviewed_total count reviews only (not bulk edits).
BEGIN;
CREATE OR REPLACE VIEW app.v_find WITH (security_barrier = true) AS
SELECT f.file_id,
    d.document_id,
    f.web_view_link,
    f.mime_type,
    f.file_type_family,
    f.modified_time,
    f.handling AS tier,
    COALESCE(d.kind_confirmed, d.kind_auto) AS kind,
    COALESCE(d.fiscal_year_confirmed, d.fiscal_year_auto) AS fiscal_year,
        CASE
            WHEN (COALESCE(d.fiscal_quarter_confirmed, d.fiscal_quarter_auto) IS NOT NULL) THEN ('q'::text || COALESCE(d.fiscal_quarter_confirmed, d.fiscal_quarter_auto))
            WHEN COALESCE(d.fye_flag_confirmed, d.fye_flag_auto) THEN 'fy'::text
            ELSE NULL::text
        END AS period,
    COALESCE(d.effective_date_confirmed, d.effective_date_auto) AS effective_date,
    COALESCE(d.workstream_confirmed, d.workstream_auto) AS workstream,
    COALESCE(d.issuer_confirmed, d.issuer_auto) AS issuer,
    COALESCE(d.requires_execution_confirmed, d.requires_execution_auto) AS requires_execution,
    COALESCE(d.execution_stage_confirmed, d.execution_stage_auto) AS stage,
    COALESCE(d.signed_date_confirmed, d.signed_date_auto) AS signed_date,
    COALESCE(d.pii_lp_flag_confirmed, d.pii_lp_flag_auto) AS pii_lp,
    COALESCE(ent.codes, '{}'::text[]) AS entities,
    COALESCE(pco.codes, '{}'::text[]) AS portcos,
    (fd.file_role = 'primary'::text) AS is_primary,
    chk.confidence,
    chk.stage_suggested,
    COALESCE(chk.signals, '{}'::text[]) AS signals,
    (EXISTS ( SELECT 1
           FROM app.review_event r
          WHERE ((r.file_id = f.file_id) AND (r.status = ANY (ARRAY['confirmed'::text, 'wrong'::text]))))) AS reviewed
   FROM ((((((app.labelled_file lf
     JOIN cat.file f ON ((f.file_id = lf.file_id)))
     LEFT JOIN cat.file_document fd ON ((fd.file_id = f.file_id)))
     LEFT JOIN cat.document d ON ((d.document_id = fd.document_id)))
     LEFT JOIN ( SELECT e.file_id,
            array_agg(DISTINCT e.entity_code ORDER BY e.entity_code) AS codes
           FROM (cat.v_file_entity e
             JOIN app.labelled_file l2 ON ((l2.file_id = e.file_id)))
          GROUP BY e.file_id) ent ON ((ent.file_id = f.file_id)))
     LEFT JOIN ( SELECT p.file_id,
            array_agg(DISTINCT p.portco_code ORDER BY p.portco_code) AS codes
           FROM (cat.v_file_portco p
             JOIN app.labelled_file l3 ON ((l3.file_id = p.file_id)))
          GROUP BY p.file_id) pco ON ((pco.file_id = f.file_id)))
     LEFT JOIN cat.doc_content_check chk ON ((chk.document_id = d.document_id)))
  WHERE ((COALESCE(f.handling, 'secret'::text) <> 'secret'::text) AND (f.removed_run IS NULL) AND (f.trashed IS NOT TRUE) AND (f.is_shortcut IS NOT TRUE));

CREATE OR REPLACE VIEW app.v_review_queue WITH (security_barrier = true) AS
 SELECT file_id, document_id, web_view_link, mime_type, file_type_family, modified_time, tier, kind, fiscal_year, period,
    effective_date, workstream, issuer, requires_execution, stage, signed_date, pii_lp, entities, portcos, is_primary,
    confidence, stage_suggested, signals, reviewed, queue_reason,
        CASE queue_reason
            WHEN 'stage_unknown'::text THEN 1
            WHEN 'low_confidence_executed'::text THEN 2
            WHEN 'no_kind'::text THEN 3
            ELSE 4
        END AS queue_rank,
        CASE confidence
            WHEN 'none'::text THEN 0
            WHEN 'low'::text THEN 1
            WHEN 'medium'::text THEN 2
            WHEN 'high'::text THEN 3
            ELSE 4
        END AS confidence_rank,
    status
   FROM ( SELECT v.file_id, v.document_id, v.web_view_link, v.mime_type, v.file_type_family, v.modified_time, v.tier, v.kind,
            v.fiscal_year, v.period, v.effective_date, v.workstream, v.issuer, v.requires_execution, v.stage, v.signed_date,
            v.pii_lp, v.entities, v.portcos, v.is_primary, v.confidence, v.stage_suggested, v.signals, v.reviewed,
            COALESCE(d.status_confirmed, d.status_auto) AS status,
                CASE
                    WHEN (v.requires_execution AND (v.stage = 'unknown'::text)) THEN 'stage_unknown'::text
                    WHEN ((v.stage = 'fully_executed'::text) AND (v.confidence = 'low'::text)) THEN 'low_confidence_executed'::text
                    WHEN (v.kind IS NULL) THEN 'no_kind'::text
                    WHEN (NOT COALESCE(v.requires_execution, false) AND COALESCE(d.status_confirmed, d.status_auto) IS NULL) THEN 'status_unknown'::text
                    ELSE NULL::text
                END AS queue_reason
           FROM app.v_find v
           LEFT JOIN cat.document d ON d.document_id = v.document_id
          WHERE (NOT v.reviewed)) q
  WHERE (queue_reason IS NOT NULL);

CREATE OR REPLACE VIEW app.v_review_counts WITH (security_barrier = true) AS   -- as in 001 (review: was dropped)
 SELECT ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'stage_unknown'::text) AS stage_unknown,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'low_confidence_executed'::text) AS low_confidence_executed,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'no_kind'::text) AS no_kind,
    ( SELECT count(*)::integer FROM app.v_review_queue) AS open_total,
    ( SELECT count(*)::integer FROM app.review_event r JOIN app.v_find v USING (file_id)
       WHERE r.created_at >= date_trunc('day'::text, now()) AND r.status = ANY (ARRAY['confirmed'::text, 'wrong'::text])) AS reviewed_today,
    ( SELECT count(DISTINCT r.file_id)::integer FROM app.review_event r JOIN app.v_find v USING (file_id)
       WHERE r.status = ANY (ARRAY['confirmed'::text, 'wrong'::text])) AS reviewed_total,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'status_unknown'::text) AS status_unknown;
COMMIT;

-- ---------------------------------------------------------------- the same tie-break in the document roll-up
-- cat.v_file_best got its final key (above), but ops.build_documents rolls file signals up to the DOCUMENT with its own
-- DISTINCT ON whose ORDER BY ended at (file_role = 'primary'): two tied rules (e.g. KND-019 invoice vs KND-022
-- wire_confirmation, both 30; KND-007 lpa vs KNX-002 ppm, both 20) still gave a different document kind / fiscal year /
-- issuer per run. Found on the branch when the re-sync diff moved by 3 files between two derives with no rule change.
-- The live definition with ONE change: the final keys s.rule_id, s.value, s.file_id.
BEGIN;
CREATE OR REPLACE FUNCTION ops.build_documents()
 RETURNS TABLE(step text, n bigint)
 LANGUAGE plpgsql
AS $function$
DECLARE c bigint;
BEGIN
  -- 1. group files: same md5 = one document; primary = shared-drive, non-Revver, newest
  TRUNCATE cat.file_group;
  INSERT INTO cat.file_group (file_id, group_key, is_primary)
  SELECT file_id, gk, rn = 1 FROM (
    SELECT f.file_id, coalesce('md5:'||f.md5, 'file:'||f.file_id) gk,
           row_number() OVER (PARTITION BY coalesce('md5:'||f.md5, 'file:'||f.file_id)
             ORDER BY (f.drive_id IS NOT NULL) DESC, (f.source_system <> 'revver') DESC, f.modified_time DESC NULLS LAST, f.file_id) rn
    FROM cat.file f WHERE f.removed_run IS NULL AND NOT f.noise_flag AND f.handling <> 'secret') x;
  GET DIAGNOSTICS c = ROW_COUNT; step := 'files grouped'; n := c; RETURN NEXT;

  INSERT INTO cat.document (group_key, title_auto, rules_version)
  SELECT g.group_key, f.name, 'rules_v2' FROM cat.file_group g JOIN cat.file f USING (file_id) WHERE g.is_primary
  ON CONFLICT (group_key) DO UPDATE SET title_auto = EXCLUDED.title_auto, updated_at = now();
  GET DIAGNOSTICS c = ROW_COUNT; step := 'documents upserted'; n := c; RETURN NEXT;

  DELETE FROM cat.file_document WHERE source = 'auto';
  INSERT INTO cat.file_document (file_id, document_id, file_role, source)
  SELECT g.file_id, d.document_id, CASE WHEN g.is_primary THEN 'primary' ELSE 'copy' END, 'auto'
  FROM cat.file_group g JOIN cat.document d USING (group_key) ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS c = ROW_COUNT; step := 'file links'; n := c; RETURN NEXT;

  -- 2. best single value per document across all its files
  TRUNCATE cat.doc_best;
  INSERT INTO cat.doc_best
  SELECT DISTINCT ON (fd.document_id, s.field) fd.document_id, s.field, s.value, s.rule_id, s.rule_version, s.source, s.file_id
  FROM cat.file_signal s JOIN cat.file_document fd ON fd.file_id = s.file_id
  JOIN ops.decomposition_rule r ON r.rule_id = s.rule_id AND r.version = s.rule_version
  WHERE NOT r.multi AND s.field IN ('kind','workstream','fiscal_year','fiscal_quarter','period_type','tax_year','issuer','confidentiality','pii_lp_flag','draft_version_no')
  ORDER BY fd.document_id, s.field, s.priority, s.distance, (s.source='name') DESC, (fd.file_role='primary') DESC,
           s.rule_id, s.value, s.file_id;   -- CAT-WO-02: final keys, same fix as cat.v_file_best (ties were a coin-flip per run)

  UPDATE cat.document d SET kind_auto = p.kind, workstream_auto = p.workstream, fiscal_year_auto = p.fy, fiscal_quarter_auto = p.fq,
         period_type_auto = p.pt, tax_year_auto = p.ty, issuer_auto = p.iss, confidentiality_auto = p.conf,
         pii_lp_flag_auto = p.pii, draft_version_no_auto = p.dv, updated_at = now()
  FROM (SELECT document_id, max(value) FILTER (WHERE field='kind') kind, max(value) FILTER (WHERE field='workstream') workstream,
               max(value) FILTER (WHERE field='fiscal_year')::int fy, max(value) FILTER (WHERE field='fiscal_quarter')::smallint fq,
               max(value) FILTER (WHERE field='period_type') pt, max(value) FILTER (WHERE field='tax_year')::int ty,
               max(value) FILTER (WHERE field='issuer') iss, max(value) FILTER (WHERE field='confidentiality') conf,
               (max(value) FILTER (WHERE field='pii_lp_flag'))::boolean pii, max(value) FILTER (WHERE field='draft_version_no')::int dv
        FROM cat.doc_best GROUP BY document_id) p
  WHERE p.document_id = d.document_id;
  GET DIAGNOSTICS c = ROW_COUNT; step := 'documents derived'; n := c; RETURN NEXT;

  -- 3. execution stage (R-005): tokens across all copies; non-agreement formats excluded; Word w/o tokens = draft (inferred)
  CREATE TEMP TABLE IF NOT EXISTS _pf ON COMMIT DROP AS
    SELECT fd.document_id, f.file_type_family fam FROM cat.file_document fd JOIN cat.file f USING (file_id) WHERE fd.file_role = 'primary';
  CREATE TEMP TABLE IF NOT EXISTS _tok ON COMMIT DROP AS
    SELECT fd.document_id, array_agg(DISTINCT s.value) toks FROM cat.file_signal s JOIN cat.file_document fd ON fd.file_id = s.file_id
    WHERE s.field = 'exec_token' GROUP BY fd.document_id;

  UPDATE cat.document d SET
    kind_auto = CASE WHEN pf.fam = 'email' AND d.kind_auto IN (SELECT code FROM ref.vocab WHERE list_name='executable_kind') THEN 'correspondence' ELSE d.kind_auto END,
    requires_execution_auto = (d.kind_auto IN (SELECT code FROM ref.vocab WHERE list_name='executable_kind') AND pf.fam IN ('pdf','doc','image')),
    execution_stage_auto = CASE
      WHEN NOT (d.kind_auto IN (SELECT code FROM ref.vocab WHERE list_name='executable_kind') AND pf.fam IN ('pdf','doc','image')) OR d.kind_auto IS NULL THEN 'n_a'
      WHEN t.toks && ARRAY['fully_executed','docusign'] THEN 'fully_executed'
      WHEN 'executed' = ANY(t.toks) AND NOT ('unsigned' = ANY(t.toks)) THEN 'fully_executed'
      WHEN 'signature_page' = ANY(t.toks) THEN 'partially_executed'
      WHEN 'draft' = ANY(t.toks) OR d.draft_version_no_auto IS NOT NULL THEN 'draft'
      WHEN t.toks && ARRAY['final','unsigned'] THEN 'final_unexecuted'
      WHEN pf.fam = 'doc' THEN 'draft'
      ELSE 'unknown' END
  FROM _pf pf LEFT JOIN _tok t ON t.document_id = pf.document_id
  WHERE pf.document_id = d.document_id;

  DELETE FROM cat.derivation WHERE field = 'execution_stage';
  INSERT INTO cat.derivation (document_id, field, rule_id, rule_version)
  SELECT d.document_id, 'execution_stage',
         CASE WHEN d.execution_stage_auto = 'draft' AND pf.fam = 'doc' AND t.toks IS NULL AND d.draft_version_no_auto IS NULL
              THEN 'STAGE-INF-WORD' ELSE 'STAGE-TOKENS' END, 1
  FROM cat.document d JOIN _pf pf USING (document_id) LEFT JOIN _tok t USING (document_id)
  WHERE d.requires_execution_auto;
  GET DIAGNOSTICS c = ROW_COUNT; step := 'executable documents staged'; n := c; RETURN NEXT;
END $function$;
COMMIT;
