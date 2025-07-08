BEGIN EXCLUSIVE;

ALTER TABLE task_presentations RENAME TO task_presentations_old;

CREATE TABLE task_presentations
    (
		presentation_id INTEGER PRIMARY KEY,
        team_id INTEGER NOT NULL REFERENCES teams(team_id),
	    task_id INTEGER NOT NULL REFERENCES tasks(task_id),
	    tutorium INTEGER NOT NULL REFERENCES tutorium(tutorium_id),
		tutor_id INTEGER NOT NULL REFERENCES users(id),
	    presentation_date TEXT NOT NULL,
		comments TEXT
    );

INSERT INTO task_presentations (team_id, task_id, tutorium, tutor_id, presentation_date, comments) select team_id, task_id, tutorium, tutor_id, presentation_date, comments from task_presentations_old;

DROP table task_presentations_old;

COMMIT;