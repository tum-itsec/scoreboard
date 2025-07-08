import itertools
import time
import datetime
import json
from flask import Blueprint, render_template, request, url_for, redirect, jsonify, current_app
from .util import *
from collections import defaultdict

bp = Blueprint("timesheet", __name__, url_prefix="/timesheet")

def parse_timeval(val):
    try:
        return datetime.datetime.strptime(val, "%Y-%m-%d %H:%M")
    except ValueError:
        return None

def errmsg(msg):
    return jsonify({"type": "error", "message": msg})

TIME_FORMAT = lambda: current_app.config["TIME_FORMAT"]
SEMESTER_START = lambda: current_app.config["SEMESTER_START"]
SEMESTER_END = lambda: current_app.config["SEMESTER_END"]
HOURS_PER_WEEK = lambda: current_app.config["HOURS_PER_WEEK"]

def list_records_for_user(user_id):
    cur = get_db().cursor()
    print(type(SEMESTER_START()))

    # Add record on POST
    if request.method == "POST":
        record = json.loads(request.data)
        # Sanity check timestamps
        s = parse_timeval(record["start"])
        e = parse_timeval(record["end"])
        if not s:
            return errmsg("Invalid start time")
        if not e:
            return errmsg("Invalid end time")
        if not s < e:
            return errmsg("End time before start time!")
        if not datetime.datetime.now() > s:
            return errmsg("Looks like you have visionary abilities! Normal people cannot forsee the future!")
        if not SEMESTER_START() <= s <= SEMESTER_END():
            return errmsg("Start time is not in bounds of current semester!")
        if not SEMESTER_START() <= e <= SEMESTER_END():
            return errmsg("End time is not in bounds of current semester!")

        record['user_id'] = session['user-id']

        # Check for overlaps
        cur.execute("SELECT COUNT(*) FROM timesheet_records WHERE ((start <= :start AND :start < end) OR (start < :end AND :end <= end)) AND user_id = :user_id", record);
        if cur.fetchone()[0] != 0:
            return errmsg("The timespan of the new record overlaps with exisiting records!")

        cur.execute("INSERT INTO timesheet_records (start, end, tasktype_id, notes, user_id, created, approved) VALUES (:start, :end, :tasktype_id, :notes, :user_id, unixepoch(), NULL)", record)

    # Fall through. List all records in the response
    cur.execute("""SELECT timerecord_id, start, end, strftime("%W", start) as week, tasktype_desc, notes, CASE approved WHEN 1 THEN 1 ELSE 0 END as approved
                FROM timesheet_records 
                LEFT JOIN timesheet_tasks USING(tasktype_id)
                WHERE user_id=?
                ORDER BY start""", (user_id,))
    recs = [dict(x) for x in cur.fetchall()]

    # Sum up hours
    # N.B Tracked times are always accounted to the week where the task/activity started.
    # i.e. a timespan from Sun, 23:30 - Mon, 01:00, will be accounted as 1,5h for the first week
    weektimes = defaultdict(lambda: datetime.timedelta(hours=0))
    for r in recs:
        weektimes[r["week"]] += datetime.datetime.strptime(r["end"], TIME_FORMAT()) - datetime.datetime.strptime(r["start"], TIME_FORMAT())

    return jsonify({"type": "records", "records": recs, "aggregates": {k: str(v).rsplit(":", 1)[0] for k,v in weektimes.items()}})

@bp.route("/api", methods=["GET", "POST"])
@tutor_required
def list_records():
    return list_records_for_user(session['user-id'])

@bp.route("/api/<int:record_id>", methods=["DELETE"])
@tutor_required
def delete_record(record_id):
    cur = get_db().cursor()
    cur.execute("DELETE FROM timesheet_records WHERE timerecord_id=? and user_id=? and approved IS NULL", (record_id, session['user-id']))
    if cur.rowcount == 0:
        return "Not found", 404
    return "Okay", 200

@bp.route("/")
@tutor_required
def overview():
    cur = get_db().cursor()
    cur.execute("SELECT * FROM timesheet_tasks")
    tasktypes = cur.fetchall();
    for r in tasktypes:
        print(dict(r))
    return render_template("timesheet.html", admin_mode=False, tasktypes=tasktypes)

@bp.route("/admin")
@admin_required
def admin():
    cur = get_db().cursor()
    cur.execute("SELECT u.vorname, u.nachname, u.id, COUNT(*) as count, SUM(unixepoch(r.end) - unixepoch(r.start)) / 60 / 60 as sum FROM timesheet_records r LEFT JOIN users u ON r.user_id = u.id GROUP BY u.id, u.vorname, u.nachname ORDER BY u.nachname")
    since_start = datetime.datetime.now() - SEMESTER_START()
    allowed_hours = (since_start.days // 7) * HOURS_PER_WEEK()
    entries = cur.fetchall()
    return render_template("timesheet_admin.html", entries = entries, allowed_hours = allowed_hours)

@bp.route("/admin/<int:id_user>/")
@admin_required
def admin_user(id_user):
    return render_template("timesheet.html", admin_mode=True)

@bp.route("/admin/<int:id_user>/api")
@admin_required
def admin_user_api(id_user):
    return list_records_for_user(id_user)

@bp.route("/admin/<int:id_user>/api/<int:record_id>", methods=["PUT"])
def approve_record(id_user, record_id):
    cur = get_db().cursor()
    d = json.loads(request.data)
    cur.execute("UPDATE timesheet_records SET approved=? WHERE timerecord_id=?", (d["approved"], record_id))
    if cur.rowcount == 0:
        return "Not found", 404
    return "Okay", 200
