BEGIN EXCLUSIVE;
	ALTER TABLE task_presentations RENAME TO task_presentations_old;
	CREATE TABLE "task_presentations"
	(
		presentation_id INTEGER PRIMARY KEY,
		team_id INTEGER,
		task_id INTEGER NOT NULL REFERENCES tasks(task_id),
		tutorium_id INTEGER NOT NULL REFERENCES tutorium(tutorium_id),
		tutor_id INTEGER NOT NULL REFERENCES users(id),
		presentation_date TEXT NOT NULL CHECK(date(presentation_date) IS NOT NULL),
		comments TEXT
	);
	INSERT INTO task_presentations SELECT * FROM task_presentations_old;
	DROP TABLE task_presentations_old;

	ALTER TABLE task_presentations ADD successful boolean NOT NULL CHECK (successful IN (0, 1)) DEFAULT 1;
COMMIT;
