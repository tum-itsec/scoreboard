BEGIN EXCLUSIVE;
CREATE INDEX task_submissions_by_team_id on task_submissions (team_id);
COMMIT;
