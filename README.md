# Scoreboard

A simple and performant scoreboard for hosting CTF style competitions as part of a lecture.

## Installation and Usage

### Docker setup

```sh
docker build -t scoreboard .
# data directory can be anywhere; just adjust following commands as necessary
mkdir data
cp config.py.default data/config.py
docker run -v $(realpath data):/data -p 8000:8000 -it --name scoreboard scoreboard
```

### Non-Docker setup

Install all the requirements in `requirements.txt`, optionally in a venv.
Then use `run.sh` or a variation of it.

If you want to keep the data directory separate, the Gunicorn `--chdir` option is probably useful.
Look at `run-docker.sh` for inspiration.

### Add a User

```
# for non-Docker deployments
python3 app.py create-user EMAIL GIVENNAME SURNAME
# for Docker deployments
docker exec -it --workdir /data scoreboard /venv/bin/python3 /app/app.py create-user EMAIL GIVENNAME SURNAME
```

This will create an entry in the `users` database table. The role of every user is tracked through an `INTEGER` value:

|Role|Meaning|
|----|-------|
|0   |user   |
|1   |admin  |
|2   |tutor  |

There is no way to change the role of a user in the frontend.
Manually update the value accordingly in sqlite (`sqlite3 scoreboard.db`):

```sql
UPDATE users SET role=1 WHERE email="admin@admin";
```

### Add a Task

Tasks should be added directly through the scoreboard's web interface.

## Folder Structure

### within source / git repo:
- `autograder/`: Task autograder implementation
- `board/`: Contains Flask [blueprints](https://https://flask.palletsprojects.com/en/2.3.x/tutorial/views/#blueprints-and-views)
- `db/`: Database migrations
- `flag/`: Flag generator
- `static/`: [Flask static files](https://flask.palletsprojects.com/en/2.3.x/quickstart/#static-files)
- `templates`: [Flask templates](https://flask.palletsprojects.com/en/2.3.x/templating/#templates)
### Within your data directory:
- `materialien/`: All files within this folder can be downloaded through the web interface
- `tasks/`: Mainly contains downloadable files associated with a specific task (e.g. `.zip` archive containing template code)
- `submissions/`: All current student submissions are collected here
- `archive/`: Student submissions from previous years are located here. **This is not autmated**. The Plagiarism-Check will also compare current submissions with previous submissions if available.
