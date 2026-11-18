-- CAT-WO-03 fiscal-year derivation fix (throwaway branch only; NOT applied to main).
-- PER-001/003/008 read a folder's year only when the year is the whole name or starts it, so folders such as
-- "<fund> 2012 K-1s", "<x> 2006 Taxes" or "Tax 2014" gave no year (or a farther folder's year won).
-- Both rules capture ONLY the year (substring() returns the first capture group), priority 10 like PER-001/003,
-- so the nearest folder wins on distance. Measured on the branch: 774 files change (586 had no year).
-- The value must be the two characters backslash + 1 (insert it as a bound parameter, not via a shell string).
INSERT INTO ops.decomposition_rule (rule_id, version, field, applies_to, pattern, value, priority, active, notes, multi, provisional) VALUES
 ('PER-009', 1, 'fiscal_year', 'path_segment',
  $re$(?i)(?:^|[^0-9])((?:19|20)[0-9]{2})[ _-]*(?:K-?1'?s?|Tax|Taxes|Tax Returns?|Audit)\y$re$, $v$\1$v$, 10, true,
  'CAT-WO-03: year inside a folder name, before Tax/Taxes/Audit/K-1 (PER-003 matched only the whole name)', false, false),
 ('PER-010', 1, 'fiscal_year', 'path_segment',
  $re$(?i)\y(?:Tax|Taxes|Audit|K-?1'?s?)[ _-]+((?:19|20)[0-9]{2})(?:[^0-9]|$)$re$, $v$\1$v$, 10, true,
  'CAT-WO-03: year after Tax/Taxes/Audit/K-1 in a folder name', false, false)
ON CONFLICT DO NOTHING;
