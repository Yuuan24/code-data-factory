SELECT
  COUNT(DISTINCT task_id) AS independent_task_count,
  COUNT(DISTINCT attempt_id) AS attempt_count,
  COUNT(*) FILTER (WHERE decision = 'ACCEPT') AS accepted_count,
  COUNT(*) FILTER (WHERE outcome = 'PASS') AS verified_pass_count,
  COUNT(*) FILTER (WHERE outcome IS NULL OR outcome = 'UNKNOWN') AS unknown_outcome_count
FROM membership;
