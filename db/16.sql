BEGIN EXCLUSIVE;
CREATE TABLE plagflags (plagcase_id INTEGER PRIMARY KEY, submission_a_id INTEGER NOT NULL REFERENCES task_submissions(id), submission_b_id INTEGER REFERENCES task_submissions(id), submission_b_filename TEXT, comment TEXT, result INTEGER NOT NULL, creator INTEGER NOT NULL REFERENCES users(id), created_time INTEGER NOT NULL);
COMMIT;
