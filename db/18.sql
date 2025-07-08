BEGIN EXCLUSIVE;
CREATE TABLE booking_requests (req_id INTEGER PRIMARY KEY, tutorium_id INTEGER NOT NULL, task_id INTEGER NOT NULL, user_id INTEGER NOT NULL, confirmed INTEGER NOT NULL, UNIQUE(tutorium_id, task_id, user_id));
ALTER TABLE tasks ADD COLUMN presentable INT NOT NULL DEFAULT 1;
COMMIT;
