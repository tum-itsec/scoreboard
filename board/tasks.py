import os
import math
import datetime
import time
from Crypto.Cipher import Blowfish

from flask import Blueprint, render_template, send_from_directory, abort, request, send_file, jsonify, current_app

from .util import *

filetypes_desc = {
    ".py": "Python Script/Exploit (.py)",
    ".txt": "Plain Text File (.txt)",
    ".md": "Markdown (.md)",
    ".zip": "ZIP File (.zip)"
}

bp = Blueprint("tasks", __name__, url_prefix="/tasks")

@bp.route("/")
@login_required
def tasks():
    cur = get_db().cursor()
    if current_app.config["PRESENTATIONS_PER_USER"]:
        presentation_query = """
            SELECT * FROM task_presentations tp
            WHERE tp.team_id=?1"""
    else:
        presentation_query = """
            select * from task_presentations tp
            left join team_members m on m.team_id = tp.team_id
            where m.member_id=?1"""
    cur.execute(f"""SELECT t.task_id, task_short, task_long,
        strftime('%d.%m.%Y %H:%M', due_date, 'unixepoch','localtime') as due_date,
        strftime('%d.%m.%Y %H:%M', submission_time, 'unixepoch','localtime') as submission_time,
        from_date,
        filepath,
        original_name,
        needed,
        max_points,
        bonus,
        t.filename as filename,
        t.url as url,
        g.team_id as team_id,
        g.comment as comment, max(g.points) as points,
        MAX(submission_time) as submission_time,
        original_name,
        t.status as status,
        t.last_check_time as last_checked_raw,
        strftime('%d.%m.%Y %H:%M:%S', t.last_check_time, 'unixepoch','localtime') as last_checked,
        tp.presentation_date as presented_on,
        tp.successful as successful
    FROM tasks t
    LEFT JOIN
    (
        SELECT s.*
        FROM task_submissions s
        LEFT JOIN team_members m ON m.team_id = s.team_id
        WHERE m.member_id=?1
    ) s ON t.task_id = s.task_id
    LEFT JOIN
    (
        SELECT g.team_id, g.task_id, comment, points
        FROM task_grading g
        LEFT JOIN team_members m ON m.team_id = g.team_id
        WHERE g.deleted_time IS NULL and m.member_id=?1
    ) g ON t.task_id = g.task_id
    LEFT JOIN
    (
        {presentation_query}
    ) tp ON tp.task_id = t.task_id
    GROUP BY t.task_id
    ORDER BY t.order_num""", [session['user-id']])

    tasks = [dict(i) for i in cur.fetchall()]
    preview_tasks = [x for x in tasks if time.localtime(x['from_date']) > time.localtime()] if is_tutor() or is_admin() else []
    tasks = [x for x in tasks if time.localtime(x['from_date']) <= time.localtime()]
    pointbonus = 0.0
    max_points = 0.0
    presentations = 0
    for i in tasks:
        pointbonus += i["points"] if i["points"] else 0
        # Only sum up max_points for tasks that have already been graded
        max_points += i["max_points"] if not i["bonus"] else 0
        presentations += 1 if i["presented_on"] and i["successful"] == 1 else 0

    pointbonus = min(max_points, math.ceil(pointbonus*2) / 2)

    # Mark tasks as down whose last sign of life was more than an hour (configurable) ago.
    current_time = datetime.datetime.now().timestamp()
    for i in tasks:
        if i["status"] is not None:
            # We have a status report.
            secs_since_last_report = current_time - i["last_checked_raw"]
            if secs_since_last_report > current_app.config.get("TASK_STATUS_UP_TIMEOUT", 60*60):
                # Task hasn't reported since way too long ago, it is down.
                i["status"] = False

    return render_template("tasks.html", tasks=tasks, preview=preview_tasks, pointbonus=pointbonus, max_points=max_points, presentations=presentations, req_presentations=current_app.config["REQ_PRESENTATIONS"])

@bp.route("/<int:task_id>")
@login_required
def task_detail(task_id):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    task = cur.fetchone()
    if task is None:
        abort(404)
    if task["from_date"] > time.time() and not (is_admin() or is_tutor()):
        abort(404)

    task = dict(task)
    verifier_code = current_user_verifier(task)

    if task["url"]:
        task["url"] = task["url"].replace("{{CODE}}", verifier_code)

    if task["markdown_rendered"]:
        task["markdown_rendered"] = task["markdown_rendered"].replace("{{CODE}}", verifier_code)

    cur.execute("""SELECT id, task_id, s.team_id, user_id,
        strftime('%d.%m.%Y %H:%M', submission_time, 'unixepoch','localtime') as submission_time,
        filepath, original_name, autograde_output, autograde_result, member_id 
        FROM task_submissions s
        LEFT JOIN team_members m ON m.team_id = s.team_id
        WHERE task_id = ?1 and m.member_id=?2
        ORDER BY s.submission_time DESC
        LIMIT 1""", (task_id, session['user-id']))

    submission = cur.fetchone()

    if submission is not None:
        submission = dict(submission)

    print(submission)

    cur.execute("""SELECT created_time as grading_created_time, comment, points FROM task_grading g
        LEFT JOIN team_members m ON m.team_id = g.team_id
        WHERE g.deleted_time IS NULL and m.member_id=?2 and g.task_id=?1
        ORDER BY g.created_time DESC LIMIT 1""", [task_id, session["user-id"]])
    grading = cur.fetchone()

    if submission:
        comments = get_comments(task_id, submission["team_id"])
        first_user_comment = next((e for e, v in enumerate(comments) if v["type"] == "comment"), 0)
        first_displayed_comment = first_user_comment - 1
        displayed_comments = comments[first_displayed_comment:]

        teammates = get_team_members(submission["team_id"])

        final_comments = [{
            "message": c["message"],
            "points": c["points"],
            "own": c["author"] == session["user-id"],
            "author": "You" if c["author"] == session["user-id"] else get_user_name(c["author"]) if c["author"] in teammates else "Your tutors",
            "time": c["time"]
        } for c in displayed_comments]
    else:
        final_comments = []

    still_open = task["due_date"]+current_app.config["SUBMISSION_GRACE_PERIOD"] > time.time()
    files_allowed = ", ".join(filetypes_desc.get(x, x) for x in task['file_extensions'].split(","))
    return render_template("task_detail.html", task=task, submission=submission, comments=final_comments, grading=grading, still_open = still_open, files_allowed = files_allowed)


@bp.route("/<int:task_id>/comment", methods=["POST"])
@login_required
def complain(task_id):
    text = request.form.get("message", "").strip()
    if not text:
        flash("You didn't specify a message!")
    else:
        author = session["user-id"]
        team_id = get_team_from_db()
        add_comment(task_id, team_id, author, text)
        flash("Comment added", "success")
    return redirect(f"/tasks/{task_id}")

@bp.route("/<int:task_id>/dl")
@login_required
def task_download(task_id):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM tasks WHERE task_id=?", [task_id])
    r = cur.fetchone()
    if r["from_date"] > time.time() and not is_tutor():
        abort(404)
    cur.execute("INSERT INTO tasks_download_log VALUES (?, ?, datetime('now', 'localtime'))", [session["user-id"],task_id])
    # TODO insert team code. Hard if we don't know if this is .zip or .tar or .tar.gz or .py or...
    return send_from_directory("tasks", path=r["task_short"], as_attachment=True, download_name=r["filename"])

@bp.route("/<int:task_id>/upload", methods=["GET", "POST"])
@login_required
def task_upload(task_id):
    team_id = get_team_from_db()
    if request.method == "POST":
        r = get_db().execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if r is None:
            flash("Das ist keine gültige Task-ID für die Abgabe!")
            return redirect("/tasks")

        if not team_id:
            flash("Du benötigst einen Team-Partner für die Abgabe der Übungsaufgaben!")
            return redirect(f"/tasks/{task_id}")

        if "fileupload" not in request.files:
            flash("Keine Datei hochgeladen!")
            return redirect(f"/tasks/{task_id}")
        f = request.files["fileupload"]

        if not any(f.filename.endswith(ext) for ext in r['file_extensions'].split(",")):
            flash("This file extension is not valid for uploads to this task!")
            return redirect(f"/tasks/{task_id}")

        ext = f.filename.split(".")[-1]

        if r["due_date"] + current_app.config["SUBMISSION_GRACE_PERIOD"] < time.time():
            flash("Die Abgabefrist ist abgelaufen!")
            return redirect(f"/tasks/{task_id}")

        filename = "task-{}-team{}-{}.{}".format(r["task_short"], team_id, datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S"), ext)
        final_path = os.path.join("submissions", filename)
        f.save(final_path)
        f.close()

        with open(final_path, "rb") as fu:
            first_two_bytes = fu.read(2)
            if not first_two_bytes:
                flash("Leere Datei hochgeladen!")
                os.remove(final_path)
                return redirect(f"/tasks/{task_id}")
            if ext == "zip" and not b"PK" == first_two_bytes:
                flash("Das ist keine ZIP-Datei!")
                os.remove(final_path)
                return redirect(f"/tasks/{task_id}")

        # Create a log record inside the database
        cur = get_db().cursor()
        cur.execute("INSERT INTO task_submissions (task_id, team_id, user_id, submission_time, filepath,original_name) VALUES (?,?,?,strftime('%s','now'),?,?)",
		(task_id, team_id, session["user-id"], final_path, f.filename))

        flash("Deine Abgabe wurde erfolgreich entgegengenommen", category="success")
        return redirect(f"/tasks/{task_id}")
    else:
        if not team_id:
            abort(404)
        cur = get_db().cursor()
        cur.execute("SELECT MAX(submission_time), filepath, original_name FROM task_submissions WHERE team_id=? and task_id=? GROUP BY team_id,task_id", (team_id, task_id))
        res = cur.fetchone()
        if not res:
            abort(404)
        else:
            # We manually open the file instead of passing the path to send_file
            # because Flask / Werkzeug will try to read from app root instead of cwd
            return send_file(open(res["filepath"], "rb"), as_attachment=True, download_name=res["original_name"])

@bp.route("/status")
@admin_required # TODO: Maybe we don't want this to be admin-only?
def task_status():
    cur = get_db().cursor()
    cur.execute("SELECT task_short, last_check_time, status FROM tasks")
    # TODO: Make this a little cleaner and format into HTML, this is just a test for now
    result = []
    for r in cur.fetchall():
        result.append(dict(r))
    return jsonify(result)


@bp.route("/status/update", methods=["POST"])
def update_task_status():
    api_key = current_app.config.get("TASK_STATUS_APIKEY")
    if not api_key:
        abort(503) # No API key configured that allows submitting status updates
    if request.form.get("APIKEY") != current_app.config["TASK_STATUS_APIKEY"]:
        abort(403)

    output = request.form.get("output")
    if not output:
        abort(400) # No output passed in the request

    for flag in find_flags(output):
        result = check_flag(flag)
        if not result:
            # Invalid flag
            # Since we don't have UUIDs anymore (they map badly for tasks with multiple flags),
            # just don't record an event at all. Instead, log an event in the logs table
            log_event(None, Category.TASK_STATUS, f"Received bad flag {flag} in status update")
        else:
            # Valid flag for something
            print(result['task_id'])
            set_task_status(result["task_id"], True)
    return '', 204 # No content


@bp.route("/<int:task_id>/feedback", methods=["POST"])
@login_required
def feedback(task_id):
    if "pending-feedback" not in session:
        flash("You can't give feedback for this task right now!") # No solve of this yet
    if task_id not in session["pending-feedback"]:
        flash("You can't give feedback for this task right now!")
    if "rating" not in request.form:
        flash("You didn't specify a rating!") # No rating given 
    else:
        session["pending-feedback"].remove(task_id)
        cur = get_db().cursor()
        try:
            cur.execute("INSERT INTO task_feedback (task_id, user_id, rating, text) VALUES (?, ?, ?, ?)", (task_id, session["user-id"], float(request.form["rating"]), request.form.get("text")))
        except sqlite3.IntegrityError:
            # Duplicate feedback
            pass
        else:
            flash("Thank you for your feedback", "success")
    return redirect("/scoreboard")
