BEGIN EXCLUSIVE;
    /* Drop task_uuid column (we can't ALTER TABLE tasks DROP COLUMN task_uuid because it has a UNIQUE constraint) */
    CREATE TABLE upgrading_tasks
    (
        task_id INTEGER PRIMARY KEY,
        task_short TEXT,
        task_long TEXT,
        markdown TEXT,
        markdown_rendered TEXT,
        filename TEXT,
        url TEXT,
        from_date INTEGER,
        due_date INTEGER,
        needed INTEGER NOT NULL,
        order_num INTEGER NOT NULL,
        max_points INT NOT NULL,
        UNIQUE(task_short)
    );
    INSERT INTO upgrading_tasks SELECT task_id, task_short, task_long, markdown, markdown_rendered, filename, url, from_date, due_date, needed, order_num, max_points FROM tasks;
    DROP TABLE tasks;
    ALTER TABLE upgrading_tasks RENAME TO tasks;
COMMIT;
