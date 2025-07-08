BEGIN EXCLUSIVE;
	ALTER TABLE tasks ADD COLUMN last_check_time INTEGER;
	ALTER TABLE tasks ADD COLUMN status INTEGER;
	UPDATE tasks SET status=s.status, last_check_time=s.time FROM (SELECT task_id, status, MAX(time) as time FROM task_status GROUP BY task_id) s WHERE tasks.task_id=s.task_id;
	DROP TABLE task_status;
COMMIT;
