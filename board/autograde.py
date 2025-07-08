from flask import Blueprint, render_template, send_from_directory, abort, request, send_file, jsonify
import flask.json
import os
import enum
import math

from .util import *

bp = Blueprint("autograde", __name__, url_prefix="/autograde")

class AutogradeStatus(enum.Enum):
    OKAY = 1
    NO_FLAG = 2
    AT_LEAST_ONE_WRONG_FLAG = 3
    FLAG_NOT_FRESH = 4
    CANCELED = 5

def get_submission_queue():
    cur = get_db().cursor()
    # TODO what if the autograder later does supply a result for any of these?
    # It's probably more sane to introduce another key like is_queued
    #cur.execute("""UPDATE task_submissions SET autograde_result = 5, autograde_output = '<overridden by later submission>'
    #            WHERE id in (
    #                SELECT s.id
    #                FROM task_submissions s
    #                LEFT JOIN tasks t USING (task_id)
    #                LEFT JOIN task_submissions sb
    #                ON sb.task_id = s.task_id and sb.team_id = s.team_id and sb.submission_time > s.submission_time
    #                WHERE sb.submission_time is not null and t.autograded=1 and s.autograde_result IS NULL
    #            )""")

    cur.execute("""SELECT s.id as id, s.original_name as original_name, *,
                CASE WHEN tt.teamname IS NULL THEN 'Team ' || tt.team_id ELSE tt.teamname END as team,
                IIF(u.displayname IS NOT NULL, u.displayname, u.vorname || ' ' || u.nachname) as name
                FROM task_submissions s
                LEFT JOIN tasks t USING (task_id)
                LEFT JOIN teams tt USING (team_id)
                LEFT JOIN users u ON u.id = s.user_id
                LEFT JOIN task_submissions sb
                ON sb.task_id = s.task_id and sb.team_id = s.team_id and sb.submission_time > s.submission_time
                WHERE sb.submission_time is null and t.autograded=1 and s.autograde_result IS NULL""")

    # ChatGPT's suggestion - doesn't seem faster:
    #    cur.execute("""WITH ts_rownums AS (
    #SELECT *,
    #ROW_NUMBER() OVER (PARTITION BY task_id, team_id ORDER BY submission_time DESC) AS rownum
    #FROM task_submissions
    #LEFT JOIN tasks t USING (task_id)
    #WHERE t.autograded = 1
    #)
    #SELECT s.id as id, s.original_name as original_name, *,
    #CASE WHEN tt.teamname IS NULL THEN 'Team ' || tt.team_id ELSE tt.teamname END as team,
    #                IIF(u.displayname IS NOT NULL, u.displayname, u.vorname || ' ' || u.nachname) as name
    #                FROM ts_rownums s
    #                LEFT JOIN teams tt USING (team_id)
    #                LEFT JOIN users u ON u.id = s.user_id
    #                WHERE s.autograde_result IS NULL AND s.rownum = 1""")

    return cur.fetchall()

@bp.route("/")
def autograde_list():
    if not request.args.get("APIKEY") == current_app.config["SSHKEY_APIKEY"]:
        abort(403)
    submission_data = []
    for r in get_submission_queue():
        submission_data.append({"id": r['id'], "filename": r['original_name']})
    return jsonify(submission_data)

@bp.route("/queue")
@tutor_required
def autograde_show_queue():
    queue = get_submission_queue()
    pagesize = 100

    page = request.args.get("page", 1, type=int)
    offset = (page-1)*pagesize

    cur = get_db().cursor()
    cur.execute("SELECT COUNT(*) FROM task_submissions WHERE autograde_result is not null")
    total_pages = math.ceil(cur.fetchone()[0] / pagesize) + 1

    cur.execute("""SELECT *,
                CASE WHEN tt.teamname IS NULL THEN 'Team ' || tt.team_id ELSE tt.teamname END as team,
                IIF(u.displayname IS NOT NULL, u.displayname, u.vorname || ' ' || u.nachname) as name
                FROM task_submissions
                LEFT JOIN tasks USING(task_id)
                LEFT JOIN teams tt USING(team_id)
                LEFT JOIN users u ON u.id = user_id
                WHERE autograde_result is not null
                ORDER BY submission_time desc
                LIMIT ?, ?""", [offset, pagesize])
    done = cur.fetchall()
    done = [dict(x) for x in done]
    for x in done:
        x['autograde_result'] = AutogradeStatus(x['autograde_result']).name

    return render_template("autograde_queue.html", queue=queue, done=done, page=page, total_pages=total_pages)

@bp.route("/<int:submission_id>", methods=["GET"])
def grade(submission_id):
    if not request.args.get("APIKEY") == current_app.config["SSHKEY_APIKEY"]:
        abort(403)
    
    cur = get_db().cursor()
    cur.execute("SELECT * FROM task_submissions s LEFT JOIN tasks t on t.task_id = s.task_id WHERE t.autograded=1 and s.id = ?""", (submission_id,))
    r = cur.fetchone()
    if not r:
        abort(404)
    return send_file(r["filepath"], as_attachment=True, download_name = r['original_name'])

def autograde_output(db_submission, output):
    # Get and decode flags from output
    flags = [check_flag(x) for x in find_flags(output)]
    print("Found flags:", flags)

    # Is there at least one flag?
    if not len(flags) >= 1:
        return AutogradeStatus.NO_FLAG
        
    # All flags should be valid and match the task of the submission
    if any(f is None or db_submission['task_id'] != f['task_id'] for f in flags):
        return AutogradeStatus.AT_LEAST_ONE_WRONG_FLAG

    # All flags should be fresh
    if any(f['ftime'] <= db_submission['submission_time']*1e6 for f in flags):
        return AutogradeStatus.FLAG_NOT_FRESH
    
    return AutogradeStatus.OKAY


@bp.route("/<int:submission_id>", methods=["POST"])
def grade_write(submission_id):
    if not request.args.get("APIKEY") == current_app.config["SSHKEY_APIKEY"]:
        abort(403)

    print(request.form.get("output"))
    if (output := request.form.get("output")) is not None:
        # Fetch submission
        cur = get_db().cursor()
        cur.execute("SELECT *, t.max_points FROM task_submissions LEFT JOIN tasks t ON t.task_id = task_submissions.task_id WHERE id=?", (submission_id,))
        db_submission = cur.fetchone()
        if not db_submission:
            abort(400) # The submission we want to update does not exist
        result = autograde_output(db_submission, output)

        cur.execute("UPDATE task_submissions SET autograde_output=?, autograde_result=? WHERE id=?", (output, result.value, submission_id))
        cur.execute("""UPDATE task_grading SET deleted_time=strftime('%s', 'now') WHERE task_id=? and team_id=? and deleted_time IS NULL""", (db_submission['task_id'], db_submission['team_id'],))
        cur.execute("""INSERT INTO task_grading (task_id, team_id, comment, points, corrector, internal_comment, created_time, deleted_time) 
                     VALUES (?,?,?,?,?,'',strftime('%s','now'),NULL)""", 
                    (db_submission['task_id'],
                     db_submission['team_id'], 
                     result.name, 
                     db_submission['max_points'] if result == AutogradeStatus.OKAY else 0.0, 
                     "Scoreboard - Grading Task"))
        return jsonify({"result": result.name})
    else:
        abort(400)
