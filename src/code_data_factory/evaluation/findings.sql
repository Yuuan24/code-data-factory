SELECT family, count(*) FILTER (WHERE NOT task_success) AS failures
FROM records
GROUP BY family
ORDER BY family;
