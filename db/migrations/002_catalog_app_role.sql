-- CAT-WO-01 · 002_catalog_app_role.sql
-- Role catalog_app: SELECT on app views; I/U/D on app.saved_view; INSERT only on app.review_event;
-- NOTHING on cat, ref, ops. Its connection URL becomes the Worker secret CATALOG_APP_DB_URL.
-- psql:  psql "$OWNER_URL" -v pw="<generated password>" -f 002_catalog_app_role.sql
-- Idempotent.

\set ON_ERROR_STOP on
\if :{?pw}
\else
  \echo 'REFUSED: pass -v pw=<generated password>'
  \quit
\endif
SELECT length(:'pw') >= 20 AS pw_ok \gset
\if :pw_ok
\else
  \echo 'REFUSED: password must be at least 20 characters (generate one; see the handoff)'
  \quit
\endif

SELECT format('CREATE ROLE catalog_app LOGIN PASSWORD %L', :'pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'catalog_app') \gexec
-- (NOSUPERUSER / NOBYPASSRLS are the defaults; Neon's owner role may not state them explicitly)
SELECT format('ALTER ROLE catalog_app LOGIN NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD %L', :'pw') \gexec

\ir 002_catalog_app_grants.sql
