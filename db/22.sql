BEGIN EXCLUSIVE;
	CREATE TABLE tasks_download_log (
		user_id INTEGER NOT NULL REFERENCES users(id),
		task_id INTEGER NOT NULL REFERENCES tasks(task_id),
		timestamp TEXT NOT NULL
	);
COMMIT;
