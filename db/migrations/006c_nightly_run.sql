-- CAT-WO-03.1 (Ryan 2026-11-19): the nightly run (scripts/nightly.py, Windows scheduled task on the ThinkPad) records
-- each night here; the app shows a banner when the last run failed or no run finished in 36 hours.
-- Codes only: step names, counts, an error CLASS (never a message that could hold a name). Idempotent.
BEGIN;
CREATE TABLE IF NOT EXISTS ops.nightly_run (
  run_id       text PRIMARY KEY,
  started_at   timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz,
  dry_run      boolean NOT NULL,
  status       text NOT NULL CHECK (status IN ('running', 'ok', 'failed')),
  last_step    text,
  failed_step  text CHECK (failed_step IS NULL OR failed_step ~ '^[a-z_]{1,30}$'),
  error_class  text CHECK (error_class IS NULL OR error_class ~ '^[A-Za-z_.]{1,80}$'),
  steps        jsonb NOT NULL DEFAULT '{}'::jsonb,
  host         text CHECK (host IS NULL OR host ~ '^[A-Za-z0-9_.-]{1,64}$')
);
REVOKE ALL ON ops.nightly_run FROM PUBLIC;

CREATE OR REPLACE VIEW app.v_nightly_status WITH (security_barrier = true) AS
 SELECT r.run_id, r.started_at, r.finished_at, r.dry_run, r.status, r.failed_step, r.error_class,
        (SELECT max(x.finished_at) FROM ops.nightly_run x WHERE x.status = 'ok' AND NOT x.dry_run) AS last_ok_at
   FROM ops.nightly_run r
  WHERE NOT r.dry_run
  ORDER BY r.started_at DESC
  LIMIT 1;
REVOKE ALL ON app.v_nightly_status FROM PUBLIC;
GRANT SELECT ON app.v_nightly_status TO catalog_app;
COMMIT;
