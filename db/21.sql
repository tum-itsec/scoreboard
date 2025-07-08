BEGIN EXCLUSIVE;
ALTER TABLE task_submissions add column autograde_output text;
ALTER TABLE task_submissions add column autograde_result integer;
COMMIT;
