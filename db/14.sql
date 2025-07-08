BEGIN EXCLUSIVE;
    DROP TABLE tutorium_attendance;
    CREATE TABLE tutorium_attendance
    (
        tracking_id INTEGER PRIMARY KEY,
	    tutorium_id INTEGER REFERENCES tutorium(tutorium_id),
	    attendance INTEGER NOT NULL DEFAULT 0,
        comments TEXT,
        tutor_id INTEGER NOT NULL REFERENCES users(id),
	    tutorial_date TEXT NOT NULL CHECK(date(tutorial_date) IS NOT NULL)
    );
COMMIT;