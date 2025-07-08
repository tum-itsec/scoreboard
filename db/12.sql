BEGIN EXCLUSIVE;
	UPDATE task_presentations SET presentation_date = substr(presentation_date,7,4)||'-'||substr(presentation_date, 4, 2)||'-'||substr(presentation_date, 1, 2);
	ALTER TABLE task_presentations RENAME TO task_presentations_old;
	CREATE TABLE "task_presentations"
	(
		presentation_id INTEGER PRIMARY KEY,
		team_id INTEGER NOT NULL REFERENCES teams(team_id),
		task_id INTEGER NOT NULL REFERENCES tasks(task_id),
		tutorium_id INTEGER NOT NULL REFERENCES tutorium(tutorium_id),
		tutor_id INTEGER NOT NULL REFERENCES users(id),
		presentation_date TEXT NOT NULL CHECK(date(presentation_date) IS NOT NULL),
		comments TEXT
	);
	INSERT INTO task_presentations SELECT * FROM task_presentations_old;
	DROP TABLE task_presentations_old;
COMMIT;

