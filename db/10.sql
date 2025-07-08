BEGIN EXCLUSIVE;
	CREATE TABLE tutorium 
    (
	    tutorium_id INTEGER PRIMARY KEY,
	    description TEXT,
	    tutor_id INTEGER
    );

	CREATE TABLE tutorium_attendance 
    (
	    tutorium_id INTEGER PRIMARY KEY,
	    attendance INTEGER NOT NULL,
	    date TEXT
    );

    CREATE TABLE task_presentations 
    (
		team_id INTEGER NOT NULL REFERENCES teams(team_id),
	    task_id INTEGER NOT NULL REFERENCES tasks(task_id),
	    tutorium INTEGER NOT NULL REFERENCES tutorium(tutorium_id),
		tutor_id INTEGER NOT NULL REFERENCES users(id),
	    presentation_date TEXT NOT NULL,
		comments TEXT
    );
COMMIT;
