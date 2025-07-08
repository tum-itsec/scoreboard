BEGIN EXCLUSIVE;
	ALTER TABLE tasks ADD COLUMN flag_key BLOB;
	UPDATE tasks SET flag_key = k.key FROM flag_keys k WHERE k.task_id = tasks.task_id;
	DROP TABLE flag_keys;
COMMIT; 
