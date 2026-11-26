-- CAT-WO-16 · R-068 ruled by Ryan (2026-11-26 06:07 UTC, "Release cat-wo-16 with version 2 of the bank rule"): BANK-L4 v2 is the
-- active version (a delimited 4-digit token in the file name, date-shaped runs skipped; the last 4 of a longer account number after
-- an account cue on page 1). v1 stays for history. Re-runnable.
BEGIN;
UPDATE ops.decomposition_rule
   SET active = true,
       notes = 'CAT-WO-16 v2 (R-068 ruled by Ryan 2026-11-26): v1 + a delimited 4-digit token in the file name (date-shaped runs '
               'skipped) + the last 4 of a longer account number after an account cue on page 1.'
 WHERE rule_id = 'BANK-L4' AND version = 2;
COMMIT;
