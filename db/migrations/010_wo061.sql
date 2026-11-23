-- CAT-WO-06.1 · GP folders: a folder named "<entity> (GP)" gives the GP entity (as CIP-I (GP) already did through its
-- file names). One generic path rule plus code aliases (data). Re-runnable. The rule is provisional until Ryan's ruling.
-- Folder names are never printed in reports; the two folders whose names differ from the entity code (S-10, S-12 in the
-- CAT-WO-06 diagnosis) get alias rows looked up from cat.folder here, so their names stay out of the repo too.
BEGIN;

-- every GP entity's own code, upper-cased (cat.v_file_entity joins ref.entity_alias on upper(signal value))
INSERT INTO ref.entity_alias (alias, entity_code, source, generic)
SELECT upper(entity_code), entity_code, 'cat-wo-06.1 gp code', false FROM ref.entity WHERE entity_type = 'gp'
ON CONFLICT DO NOTHING;

-- the two 2025 partner-package folders whose names spell the GP differently (MTV-III (PF) (GP), MTV-IV (Annex) (GP))
INSERT INTO ref.entity_alias (alias, entity_code, source, generic)
SELECT DISTINCT upper(f.path_segments[array_position(f.path_segments, '01_Partner Packages') + 1]), x.entity_code, 'cat-wo-06.1 gp folder', false
FROM cat.file f
JOIN (SELECT 'MTV-III (PF) (GP)' AS entity_code, '(?i)MTV.*III.*\yPF\y.*\(GP\)$' AS rx UNION ALL
      SELECT 'MTV-IV (Annex) (GP)', '(?i)MTV.*IV.*annex.*\(GP\)$') x
  ON f.path_segments[array_position(f.path_segments, '01_Partner Packages') + 1] ~ x.rx
WHERE f.removed_run IS NULL AND f.folder_path ILIKE '%/01_Partner Packages/%'
  AND upper(f.path_segments[array_position(f.path_segments, '01_Partner Packages') + 1]) <> upper(x.entity_code)
ON CONFLICT DO NOTHING;

-- one generic rule: a folder named "... (GP)" -> its whole name as the entity value (resolved through the aliases above)
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional)
VALUES ('ENT-GP-P', 1, 'entity', 'path_segment', '(?i)^(.+ \(GP\))$', '\1', 30, true,
        'CAT-WO-06.1: a folder named "<entity> (GP)" -> the GP entity (via ref.entity_alias); the fund code in the same name still counts, as for CIP-I (GP)',
        true, true)
ON CONFLICT (rule_id, version) DO NOTHING;
COMMIT;
