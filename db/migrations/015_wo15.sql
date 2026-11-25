-- CAT-WO-15 · Review queue split. app.v_review_counts + review_total: the open queue WITHOUT the two rule-round backlogs
-- (no_kind, status_unknown). open_total is unchanged (all lanes). CREATE OR REPLACE can only append a column, so review_total is
-- the last column (the app reads columns by name). View change only: no rule, checklist or nightly change. Re-runnable.
BEGIN;
CREATE OR REPLACE VIEW app.v_review_counts WITH (security_barrier = true) AS
 SELECT ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'stage_unknown'::text) AS stage_unknown,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'low_confidence_executed'::text) AS low_confidence_executed,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'no_kind'::text) AS no_kind,
    ( SELECT count(*)::integer FROM app.v_review_queue) AS open_total,
    ( SELECT count(*)::integer FROM app.review_event r JOIN app.v_find v USING (file_id)
       WHERE r.created_at >= date_trunc('day'::text, now()) AND r.status = ANY (ARRAY['confirmed'::text, 'wrong'::text])) AS reviewed_today,
    ( SELECT count(DISTINCT r.file_id)::integer FROM app.review_event r JOIN app.v_find v USING (file_id)
       WHERE r.status = ANY (ARRAY['confirmed'::text, 'wrong'::text])) AS reviewed_total,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'status_unknown'::text) AS status_unknown,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'match_subject'::text) AS match_subject,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason = 'content_disagrees'::text) AS content_disagrees,
    ( SELECT count(*)::integer FROM app.v_review_queue WHERE queue_reason <> ALL (ARRAY['no_kind'::text, 'status_unknown'::text])) AS review_total;
GRANT SELECT ON app.v_review_counts TO catalog_app;
COMMIT;
