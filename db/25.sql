BEGIN EXCLUSIVE;
	ALTER TABLE teams RENAME TO teamsOld;

    CREATE TABLE IF NOT EXISTS teams 
    (
        team_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        created INTEGER NOT NULL,
        deleted INTEGER,
        teamname TEXT
    );

    INSERT INTO teams (team_id, created, deleted, teamname)
    SELECT team_id, created, deleted, teamname
    FROM teamsOld;

    DROP TABLE teamsOld;

COMMIT;
