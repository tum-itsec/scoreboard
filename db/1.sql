CREATE TABLE IF NOT EXISTS users 
(
	id INTEGER PRIMARY KEY, 
	permanent_id TEXT, 
	matrikel TEXT, 
	vorname TEXT NOT NULL, 
	nachname NOT NULL, 
	uid TEXT, 
	gender INTEGER, 
	email TEXT, 
	password TEXT, 
	role INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS flag_submissions 
(
	user_id INTEGER, 
	team_id INTEGER NOT NULL, 
	task_id INTEGER NOT NULL, 
	submission_time INTEGER NOT NULL, 
	flag_time INTEGER NOT NULL, 
	flag TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams 
(
	team_id INTEGER PRIMARY KEY, 
	created INTEGER NOT NULL,
	deleted INTEGER,
	teamname TEXT
);

CREATE TABLE IF NOT EXISTS team_members
(
	team_id INTEGER NOT NULL,
	member_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks 
(
	task_id INTEGER PRIMARY KEY, 
	task_short TEXT,
	task_long TEXT,
	task_uuid TEXT,
	markdown TEXT,
	markdown_rendered TEXT,
	filename TEXT,
	url TEXT,
	from_date INTEGER, 
	due_date INTEGER, 
	needed INTEGER NOT NULL,
	order_num INTEGER NOT NULL,
	max_points INT NOT NULL,
	UNIQUE(task_short),
	UNIQUE(task_uuid)
);

CREATE TABLE IF NOT EXISTS task_submissions 
(
	id INTEGER PRIMARY KEY, 
	task_id INTEGER NOT NULL, 
	team_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	submission_time INTEGER NOT NULL, 
	filepath TEXT NOT NULL, 
	original_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_grading 
(
	id INTEGER PRIMARY KEY, 
	task_id INTEGER NOT NULL, 
	team_id INTEGER NOT NULL, 
	comment TEXT NOT NULL, 
	internal_comment TEXT NOT NULL, 
	points REAL NOT NULL, 
	corrector TEXT NOT NULL, 
	created_time INTEGER NOT NULL,
	deleted_time INTEGER,
	UNIQUE(task_id, team_id, deleted_time)
);

CREATE TABLE IF NOT EXISTS sshkeys
(
	user_id INT PRIMARY KEY, 
	ssh_key TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flag_keys
(
	task_id INTEGER PRIMARY KEY REFERENCES tasks(task_id),
	key BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS task_status
(
	task_id INTEGER NOT NULL REFERENCES tasks(task_id),
	time INTEGER NOT NULL,
	status INTEGER NOT NULL /* boolean values: ok / not ok */
);

CREATE TABLE IF NOT EXISTS task_feedback
(
	task_id INTEGER NOT NULL REFERENCES tasks(task_id),
	user_id INTEGER NOT NULL REFERENCES users(id), /* feedback is per user >:D */
	rating REAL NOT NULL,
	text TEXT,
	UNIQUE(task_id, user_id)
);

CREATE TABLE IF NOT EXISTS submission_comments
(
	task_id INTEGER NOT NULL REFERENCES tasks(task_id),
	team_id INTEGER NOT NULL REFERENCES teams(team_id),
	author INTEGER NOT NULL REFERENCES users(id),
	text TEXT NOT NULL,
	created_time INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS logs
(
	time INTEGER NOT NULL,
	user_id INTEGER REFERENCES users(id),
	category TEXT NOT NULL,
	message TEXT NOT NULL
);

CREATE VIEW IF NOT EXISTS task_submissions_human as select s.id, s.task_id, s.team_id, s.user_id, u.vorname || ' ' || u.nachname as submitter, datetime(s.submission_time, 'unixepoch'), s.filepath, s.original_name from task_submissions s left join users u on u.id = s.user_id
/* task_submissions_human(id,task_id,team_id,user_id,submitter,"datetime(s.submission_time, 'unixepoch')",filepath,original_name) */;
