SELECT
  COUNT(DISTINCT task_id) AS independent_task_count,
  COUNT(DISTINCT attempt_id) AS attempt_count,
  COUNT(*) FILTER (WHERE decision = 'ACCEPT') AS accepted_count,
  COUNT(*) FILTER (WHERE decision = 'REJECT') AS rejected_count,
  COUNT(*) FILTER (WHERE decision = 'QUARANTINE') AS quarantined_count,
  COUNT(*) FILTER (WHERE outcome = 'PASS') AS verified_pass_count,
  COUNT(*) FILTER (WHERE outcome IS NULL OR outcome = 'UNKNOWN') AS unknown_outcome_count,
  COUNT(*) FILTER (WHERE usage_scope = 'TRAIN') AS train_member_count,
  COUNT(*) FILTER (WHERE usage_scope = 'DEVELOPMENT') AS development_member_count,
  COUNT(*) FILTER (WHERE usage_scope = 'TEST') AS test_member_count,
  NULL::BIGINT AS cost_cny_fen,
  NULL::DOUBLE AS cost_cny_fen_per_accepted_member
FROM membership;
