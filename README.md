# Scoreboard

A simple and performant scoreboard for hosting CTF style competitions as part of a lecture.

## Installation and Usage

The required python3 packages are listed here: `requirements.txt`

### Setup

```
docker build -t scoreboard-new .
cp config.py.default config.py
docker run -v $(pwd):/home/scoreboard -p 8000:8000 -it scoreboard-new python3 init.py
docker run -v $(pwd):/home/scoreboard -p 8000:8000 -it scoreboard-new
python3 app.py create-db
```

### Add a User

```
python3 app.py create-user [user-email] [forename] [surname]
```

This will create an entry in the `users` database table. The role of every user is tracked through an `INTEGER` value:

```
+-+-------+
|#|Meaning|
+-+-------+
|0|user   |
|1|admin  |
|2|tutor  |
+-+-------+
```

Update the value accordingly in sqlite (`sqlite3 scoreboard.db`):

```
UPDATE users SET role=1 WHERE email="admin@admin";
```

### Add a Task

Tasks should be added directly through the scoreboard's web interface.

## Folder Structure

- `autograder/`: Task autograder implementation
- `board/`: Contains Flask [blueprints](https://https://flask.palletsprojects.com/en/2.3.x/tutorial/views/#blueprints-and-views)
- `db/`: Database migrations
- `flag/`: Flag generator
- `materialien/`: All files within this folder can be downloaded through the web interface
- `static/`: [Flask static files](https://flask.palletsprojects.com/en/2.3.x/quickstart/#static-files)
- `submissions/`: All current student submissions are collected here
- `submissions-archive`: Student submissions from previous years are located here (***THIS IS NOT AUTOMATED***). The Plagiarism-Check will also compare current submissions with previous submissions if available.
- `tasks`: Mainly contains downloadable files associated with a specific task (e.g. `.zip` archive containing template code)
- `templates`: [Flask templates](https://flask.palletsprojects.com/en/2.3.x/templating/#templates)

