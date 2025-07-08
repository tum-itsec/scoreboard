BEGIN EXCLUSIVE;
CREATE TABLE tutorium_attendance_students (
    tracking_id INTEGER NOT NULL, 
    user_id INTEGER NOT NULL, 
    PRIMARY KEY(tracking_id, user_id),
    FOREIGN KEY(tracking_id) REFERENCES tutorium_attendance(tracking_id) ON DELETE CASCADE
);
COMMIT;