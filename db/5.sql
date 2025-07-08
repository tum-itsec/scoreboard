CREATE TABLE plagcheck 
(
	check_id INTEGER PRIMARY KEY, 
	task_id INT NOT NULL, 
	similarity FLOAT NOT NULL, 
	token_count INT NOT NULL, 
	submission_a INT NOT NULL, 
	submission_b INT, 
	submission_b_path TEXT
);
