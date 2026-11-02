BEGIN EXCLUSIVE;
ALTER TABLE users ADD COLUMN session_generation integer default 0;
COMMIT;
