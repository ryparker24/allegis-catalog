-- CAT-WO-02 Part 1 · 003_wo02_part1.sql
-- Saved-view folders (item 4), pinned views, per-user "last state" of the lists (item 2),
-- entity names for the Labels panel (item 3). Idempotent. Run as the DB owner; grants are at the end.
-- Codes and Allegis entity names only: nothing here reads ref.lp or ref.person.

BEGIN;

-- ---------------------------------------------------------------- item 4 · folders
CREATE TABLE IF NOT EXISTS app.view_folder (
    folder_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_email text        NOT NULL CHECK (owner_email = lower(owner_email)),
    name        text        NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 60),
    parent_id   bigint      REFERENCES app.view_folder (folder_id) ON DELETE RESTRICT,
    sort        smallint    NOT NULL DEFAULT 100,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (parent_id IS DISTINCT FROM folder_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS view_folder_name_uq ON app.view_folder (owner_email, coalesce(parent_id, 0), lower(name));
CREATE INDEX IF NOT EXISTS view_folder_owner_idx ON app.view_folder (owner_email);

-- Two levels at most, and a parent must belong to the same owner. Enforced in the DB, not only in the app.
CREATE OR REPLACE FUNCTION app.tg_view_folder_depth() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p record;
BEGIN
    IF NEW.parent_id IS NULL THEN
        -- a folder that has children cannot itself move under another folder (that would make 3 levels)
        RETURN NEW;
    END IF;
    -- FOR UPDATE: two concurrent moves (X under Y, Z under X) serialise here, so neither can make 3 levels
    SELECT owner_email, parent_id INTO p FROM app.view_folder WHERE folder_id = NEW.parent_id FOR UPDATE;
    IF NOT FOUND OR p.owner_email <> NEW.owner_email THEN
        RAISE EXCEPTION 'view_folder: parent not found' USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF p.parent_id IS NOT NULL THEN
        RAISE EXCEPTION 'view_folder: folders nest two levels at most' USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'UPDATE' AND EXISTS (SELECT 1 FROM app.view_folder c WHERE c.parent_id = NEW.folder_id) THEN
        RAISE EXCEPTION 'view_folder: folders nest two levels at most' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS view_folder_depth ON app.view_folder;
CREATE TRIGGER view_folder_depth BEFORE INSERT OR UPDATE OF parent_id, owner_email ON app.view_folder
    FOR EACH ROW EXECUTE FUNCTION app.tg_view_folder_depth();

ALTER TABLE app.saved_view ADD COLUMN IF NOT EXISTS folder_id bigint REFERENCES app.view_folder (folder_id) ON DELETE RESTRICT;
ALTER TABLE app.saved_view ADD COLUMN IF NOT EXISTS pinned boolean NOT NULL DEFAULT false;

-- a view may only sit in a folder of its own owner
CREATE OR REPLACE FUNCTION app.tg_saved_view_folder_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.folder_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM app.view_folder f WHERE f.folder_id = NEW.folder_id AND f.owner_email = NEW.owner_email) THEN
        RAISE EXCEPTION 'saved_view: folder not found' USING ERRCODE = 'foreign_key_violation';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS saved_view_folder_owner ON app.saved_view;
CREATE TRIGGER saved_view_folder_owner BEFORE INSERT OR UPDATE OF folder_id, owner_email ON app.saved_view
    FOR EACH ROW EXECUTE FUNCTION app.tg_saved_view_folder_owner();

-- ---------------------------------------------------------------- item 2 · last list state per user
CREATE TABLE IF NOT EXISTS app.user_pref (
    owner_email text        NOT NULL CHECK (owner_email = lower(owner_email)),
    pref_key    text        NOT NULL CHECK (pref_key ~ '^[a-z_]{1,40}$'),
    value       jsonb       NOT NULL CHECK (octet_length(value::text) <= 32768),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_email, pref_key)
);

-- ---------------------------------------------------------------- item 3 · entity names (Allegis entities only)
CREATE OR REPLACE VIEW app.v_entity WITH (security_barrier = true) AS
SELECT entity_code, coalesce(name, entity_code) AS display_name FROM ref.entity;

-- ---------------------------------------------------------------- item 4 · seed folders for owners who already have the seed views
-- "Tax" (K-1s TY2025), "Agreements" (ACCSO subscription docs, Unsigned side letters), "Close" (MTV-II FY2025 close).
-- New users get the same from the app on first visit (src/lib/views.ts).
WITH seeds(folder, sort, view_name) AS (VALUES
        ('Tax', 1, 'K-1s · tax year 2025'),
        ('Agreements', 2, 'ACCSO · subscription docs'),
        ('Agreements', 2, 'Unsigned side letters'),
        ('Close', 3, 'MTV-II · FY2025 close')),
     owners AS (SELECT DISTINCT sv.owner_email, s.folder, s.sort
                FROM app.saved_view sv JOIN seeds s ON s.view_name = sv.name WHERE sv.is_seed)
INSERT INTO app.view_folder (owner_email, name, sort)
SELECT o.owner_email, o.folder, o.sort FROM owners o
WHERE NOT EXISTS (SELECT 1 FROM app.view_folder f WHERE f.owner_email = o.owner_email AND f.parent_id IS NULL AND lower(f.name) = lower(o.folder));

UPDATE app.saved_view sv SET folder_id = f.folder_id, updated_at = now()
FROM (VALUES ('Tax', 'K-1s · tax year 2025'), ('Agreements', 'ACCSO · subscription docs'),
             ('Agreements', 'Unsigned side letters'), ('Close', 'MTV-II · FY2025 close')) s(folder, view_name),
     app.view_folder f
WHERE sv.is_seed AND sv.name = s.view_name AND sv.folder_id IS NULL
  AND f.owner_email = sv.owner_email AND f.parent_id IS NULL AND lower(f.name) = lower(s.folder);

COMMIT;

-- ---------------------------------------------------------------- grants (same shape as 002: owner-scoped tables, no cat/ref/ops)
BEGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.view_folder TO catalog_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.user_pref TO catalog_app;
GRANT SELECT ON app.v_entity TO catalog_app;
COMMIT;
