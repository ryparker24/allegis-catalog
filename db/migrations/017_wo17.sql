-- CAT-WO-17 · Duplicates and zips (LIMITED - Finance + Confidential - RYAN and CECILIA only)
--   R-060  which copy of a duplicate group wins, for groups wholly inside those two places
--   R-062  zip contents, listed read-only (cat.zip_listing / cat.zip_member)
-- R-061 (copies hidden in Find) is app-only: no SQL.
-- Idempotent. Run on the throwaway first; main only at release.

BEGIN;

-- ------------------------------------------------------------------ R-060
CREATE TABLE IF NOT EXISTS ops.dup_folder_pref (
  folder_prefix text PRIMARY KEY,          -- drive / folder path prefix, as cat.file.folder_path
  note          text,
  ruled_by      text NOT NULL,
  ruled_at      timestamptz NOT NULL DEFAULT now(),
  active        boolean NOT NULL DEFAULT true
);
INSERT INTO ops.dup_folder_pref (folder_prefix, note, ruled_by) VALUES
  ('LIMITED - Finance/FINANCE TEAM - Allegis Accounting/02-Legal/Organized Entities - 2026-10-21',
   'main copy over the older CIP, CSOP and GP folders', 'Ryan R-060 2026-11-25')
ON CONFLICT DO NOTHING;

-- The R-060 keys per live, groupable file. in_scope = Finance shared drive or the Confidential folder.
CREATE OR REPLACE VIEW ops.v_file_r060 AS
SELECT f.file_id,
       coalesce('md5:' || f.md5, 'file:' || f.file_id) AS gk,
       f.drive_id, f.source_system, f.modified_time, f.created_time, f.path_depth,
       (f.drive_name = 'LIMITED - Finance'
        OR f.folder_path LIKE 'My Drive/Confidential - RYAN and CECILIA only%')                                   AS in_scope,
       EXISTS (SELECT 1 FROM unnest(coalesce(f.path_segments, '{}'::text[])) s
               WHERE s ~* '^z-' OR s ~* '(archive|(^|[^a-z])old([^a-z]|$)|backup|superseded|bisync|_files$)')     AS r060_archive,
       (f.name ~* '^copy of ' OR f.name ~* '\(\d{1,2}\)(\.[a-z0-9]{1,5})?$' OR f.name ~* ' - copy(\.[a-z0-9]{1,5})?$') AS r060_copyname,
       -- Ryan 2026-11-25: a preferred folder wins (ops.dup_folder_pref); a year folder outside its range folder
       -- (e.g. '2011 - 2020/2010') is misfiled and loses
       EXISTS (SELECT 1 FROM ops.dup_folder_pref p WHERE p.active AND f.folder_path LIKE p.folder_prefix || '%')              AS r060_preferred,
       EXISTS (SELECT 1 FROM generate_subscripts(coalesce(f.path_segments, '{}'::text[]), 1) i
               WHERE f.path_segments[i] ~ '^\d{4} - \d{4}$' AND f.path_segments[i + 1] ~ '^\d{4}$'
                 AND f.path_segments[i + 1]::int NOT BETWEEN substr(f.path_segments[i], 1, 4)::int AND substr(f.path_segments[i], 8, 4)::int) AS r060_misfiled
FROM cat.file f
WHERE f.removed_run IS NULL AND NOT f.noise_flag AND f.handling <> 'secret';

COMMENT ON VIEW ops.v_file_r060 IS
  'CAT-WO-17 R-060 v1: winner keys for duplicate groups wholly inside LIMITED - Finance + Confidential (Ryan 2026-11-25).';

-- Replace step 1 of ops.build_documents (grouping + primary choice). The rest of the live body is kept as it is.
DO $$
DECLARE body text; old_sel text; new_sel text;
BEGIN
  body := pg_get_functiondef('ops.build_documents()'::regprocedure);
  IF position('r060_preferred' IN body) > 0 THEN
    RAISE NOTICE 'build_documents already on R-060'; RETURN;
  END IF;
  old_sel := $o$  SELECT file_id, gk, rn = 1 FROM (
    SELECT f.file_id, coalesce('md5:'||f.md5, 'file:'||f.file_id) gk,
           row_number() OVER (PARTITION BY coalesce('md5:'||f.md5, 'file:'||f.file_id)
             ORDER BY (f.drive_id IS NOT NULL) DESC, (f.source_system <> 'revver') DESC, f.modified_time DESC NULLS LAST, f.file_id) rn
    FROM cat.file f WHERE f.removed_run IS NULL AND NOT f.noise_flag AND f.handling <> 'secret') x;$o$;
  new_sel := $n$  SELECT file_id, gk, rn = 1 FROM (
    -- CAT-WO-17 R-060: groups wholly inside Finance + Confidential get the R-060 keys; every other group keeps CAT-WO-02's
    SELECT v.file_id, v.gk,
           row_number() OVER (PARTITION BY v.gk
             ORDER BY (v.drive_id IS NOT NULL) DESC, (v.source_system <> 'revver') DESC,
                      CASE WHEN v.sc THEN v.r060_preferred END DESC NULLS LAST, CASE WHEN v.sc THEN v.r060_misfiled END,
                      CASE WHEN v.sc THEN v.r060_archive END, CASE WHEN v.sc THEN v.r060_copyname END,
                      CASE WHEN v.sc THEN v.created_time END ASC NULLS LAST, CASE WHEN v.sc THEN v.path_depth END ASC NULLS LAST,
                      v.modified_time DESC NULLS LAST, v.file_id) rn
    FROM (SELECT r.*, bool_and(r.in_scope) OVER (PARTITION BY r.gk) sc FROM ops.v_file_r060 r) v) x;$n$;
  IF position(old_sel IN body) = 0 THEN
    RAISE EXCEPTION 'CAT-WO-17: step 1 of ops.build_documents is not the CAT-WO-02 text; not replaced';
  END IF;
  EXECUTE replace(body, old_sel, new_sel);
END $$;

-- ------------------------------------------------------------------ R-062
CREATE TABLE IF NOT EXISTS cat.zip_listing (
  zip_file_id   text PRIMARY KEY REFERENCES cat.file(file_id),
  zip_md5       text,
  status        text NOT NULL CHECK (status IN ('listed', 'directory_only', 'encrypted', 'not_a_zip', 'too_large', 'failed')),
  member_count  integer NOT NULL DEFAULT 0,
  note          text CHECK (note IS NULL OR length(note) <= 200),     -- error class only, never a name or content
  rule_version  integer NOT NULL DEFAULT 1,
  listed_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cat.zip_member (
  zip_file_id      text NOT NULL REFERENCES cat.zip_listing(zip_file_id) ON DELETE CASCADE,
  member_path      text NOT NULL CHECK (length(member_path) <= 1000),
  parent_member    text NOT NULL DEFAULT '',           -- '' = in the zip itself; else the nested zip's member_path (one level)
  is_dir           boolean NOT NULL DEFAULT false,
  size_bytes       bigint,
  compressed_bytes bigint,
  crc32            text,
  member_mtime     timestamp,                          -- zip times carry no zone
  md5              text CHECK (md5 IS NULL OR md5 ~ '^[0-9a-f]{32}$'),
  encrypted        boolean NOT NULL DEFAULT false,
  nested_zip       boolean NOT NULL DEFAULT false,
  PRIMARY KEY (zip_file_id, parent_member, member_path)
);
CREATE INDEX IF NOT EXISTS zip_member_md5_idx ON cat.zip_member (md5);

COMMENT ON TABLE cat.zip_member IS 'CAT-WO-17 R-062: names and hashes of files inside zips (read in memory, drive.readonly).';

-- members with their match to a live catalog file (same md5)
CREATE OR REPLACE VIEW app.v_zip_member AS
SELECT m.zip_file_id, m.parent_member, m.member_path, m.is_dir, m.size_bytes, m.member_mtime, m.encrypted, m.nested_zip,
       (SELECT f.file_id FROM cat.file f
         WHERE m.md5 IS NOT NULL AND f.md5 = m.md5 AND f.removed_run IS NULL AND f.handling <> 'secret' AND f.file_id <> m.zip_file_id
         ORDER BY (f.drive_name = 'LIMITED - Finance') DESC, f.file_id LIMIT 1)                                   AS on_drive_file_id
FROM cat.zip_member m;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'catalog_app') THEN
    GRANT SELECT ON app.v_zip_member, cat.zip_listing TO catalog_app;
  END IF;
END $$;

COMMIT;
