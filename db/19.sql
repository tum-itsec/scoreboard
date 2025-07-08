BEGIN EXCLUSIVE;
CREATE TABLE timesheet_tasks
(
	tasktype_id INTEGER PRIMARY KEY, 
	tasktype_desc TEXT NOT NULL
);
CREATE TABLE timesheet_records 
(
	timerecord_id INTEGER PRIMARY KEY, 
	start TEXT NOT NULL, 
	end TEXT NOT NULL,
	tasktype_id INTEGER NOT NULL REFERENCES timesheet_records(tasktype_id),
	notes TEXT, user_id INTEGER REFERENCES users(id), 
	created INTEGER, 
	approved INTEGER
);
INSERT INTO timesheet_tasks VALUES (NULL, 'Vorbereitung'), (NULL, 'Tutorium'), (NULL, 'Tutorbesprechung'), (NULL, 'Sonstiges');
COMMIT;
