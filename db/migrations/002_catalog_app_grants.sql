-- CAT-WO-01 · grants for catalog_app (no password here; included by 002_catalog_app_role.sql).
BEGIN;
ALTER ROLE catalog_app SET search_path = app;
ALTER ROLE catalog_app SET statement_timeout = '20s';

-- nothing on cat / ref / ops / public (explicit, and also strip anything PUBLIC would lend it)
REVOKE ALL ON ALL TABLES    IN SCHEMA cat, ref, ops FROM catalog_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA cat, ref, ops FROM catalog_app;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA cat, ref, ops FROM catalog_app;
REVOKE ALL ON SCHEMA cat, ref, ops FROM catalog_app;
REVOKE ALL ON SCHEMA cat, ref, ops FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM catalog_app;

GRANT USAGE ON SCHEMA app TO catalog_app;
REVOKE ALL ON ALL TABLES IN SCHEMA app FROM catalog_app;
GRANT SELECT ON app.v_find, app.v_review_queue, app.v_review_counts, app.v_portco, app.v_entity TO catalog_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.saved_view TO catalog_app;
GRANT INSERT ON app.review_event TO catalog_app;
-- (no grant on app.labelled_file: loaded by the owner; readable only through the views)
COMMIT;
