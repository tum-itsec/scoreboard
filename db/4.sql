BEGIN EXCLUSIVE;
	CREATE TABLE sshkeys_new (
		key_id INTEGER PRIMARY KEY, 
		user_id INTEGER REFERENCES users(id) NOT NULL, 
		ssh_key TEXT NOT NULL,
		used_date INTEGER,
		added_date INTEGER
	);
	INSERT INTO sshkeys_new (key_id, user_id, ssh_key) SELECT NULL, user_id, ssh_key FROM sshkeys;
	DROP TABLE sshkeys;
	ALTER TABLE sshkeys_new RENAME TO sshkeys;
COMMIT;
