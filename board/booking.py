import itertools
import time
from flask import Blueprint, render_template, request, url_for, redirect
from .util import *

bp = Blueprint("booking", __name__, url_prefix="/booking")

@bp.route("/")
@login_required
def booking():
    cur = get_db().cursor()

    #XXX: Check if already presented

    # Assume we only want to give out presentation slots for the upcoming week
    # and that the due date of the assignments is always in the same week as the
    # corresponding presentations
    cur.execute("""
        SELECT t.task_id, t.task_short, t.task_long, tut.*, br.*,
            (SELECT COUNT(*) FROM booking_requests bri WHERE bri.tutorium_id = tut.tutorium_id AND t.task_id = bri.task_id) applications,
            (SELECT COUNT(*) FROM tutorium_attendance_students tas JOIN tutorium_attendance ta ON tas.tracking_id=ta.tracking_id WHERE ta.tutorium_id=tut.tutorium_id AND tas.user_id = ?1) attendance
        FROM tasks t 
        CROSS JOIN tutorium tut
        LEFT JOIN booking_requests br ON br.tutorium_id = tut.tutorium_id AND br.task_id = t.task_id AND br.user_id=?1
        WHERE strftime('%Y-%W', t.due_date, 'unixepoch') == strftime('%Y-%W', 'now', '+7 days') AND t.from_date <= unixepoch('now') AND t.presentable = 1 AND t.task_id NOT IN (SELECT task_id FROM booking_requests WHERE confirmed=1 and user_id=?1)
        ORDER BY attendance DESC, t.task_id ASC, tut.tutorium_id ASC""", (session['user-id'],))
    slots = cur.fetchall()
    slots = [dict(d) for d in slots]
    
    cur.execute("""
        SELECT t.task_id, t.task_short, t.task_long, br.*, tut.* FROM booking_requests br
        LEFT JOIN tasks t USING(task_id)
        LEFT JOIN tutorium tut USING(tutorium_id)
        WHERE user_id=? AND confirmed = 1 """, (session['user-id'],))
    approved_presentations = cur.fetchall()
    print(slots)
    return render_template("booking.html", slots=slots, approved_presentations=approved_presentations)

@bp.route("/book", methods=["POST"])
@login_required
def reserve():
    cur = get_db().cursor()
    tutorium = request.form.get("slot")
    task = request.form.get("task")
    cur.execute("insert into booking_requests (task_id, tutorium_id, user_id, confirmed) values (?, ?, ?, ?)", [task, tutorium, session['user-id'], 0])
    return redirect(url_for('.booking'))

@bp.route("/cancelbook", methods=["POST"])
@login_required
def cancel():
    cur = get_db().cursor()
    req_id = request.form.get("req_id")
    cur.execute("delete from booking_requests where req_id = ? and user_id = ?", [req_id, session['user-id']])
    return redirect(url_for('.booking'))

@bp.route("/tutor-overview")
@tutor_required
def tutor_overview():
    selected_tutorial = request.args.get("tutorium_id")
    args = {}
    if selected_tutorial:
        filter_sql = "tut.tutorium_id = ?"
        filter_parameter = int(selected_tutorial)
        args["selected_tutorial"] = filter_parameter
    else:
        filter_sql = "tut.tutor_id = ?"
        filter_parameter = session['user-id']

    cur = get_db().cursor()
    
    # team_id in task_presentations is in fact a user_id if PRESENTATIONS_PER_USER = True
    cur.execute(f"""
        SELECT 
            t.task_id, 
            t.task_short, 
            t.task_long, 
            tut.*, 
            br.*, 
            vorname || ' ' || nachname as booker,
            (SELECT tg.team_id FROM task_grading tg LEFT JOIN team_members tm ON tm.team_id = tg.team_id WHERE task_id=t.task_id AND member_id=br.user_id AND deleted_time IS NULL AND points > 0) task_solved,
            (SELECT COUNT(*) FROM tutorium_attendance_students tas JOIN tutorium_attendance ta ON tas.tracking_id=ta.tracking_id WHERE ta.tutorium_id=br.tutorium_id AND user_id = br.user_id) attendance,
            (SELECT COUNT(*) FROM booking_requests WHERE user_id = br.user_id AND confirmed = 1) approved_presentations,
            (SELECT COUNT(*) FROM task_presentations WHERE team_id = br.user_id and successful=1) presentations_success,
            (SELECT COUNT(*) FROM task_presentations WHERE team_id = br.user_id and successful=0) presentations_failed
        FROM booking_requests br
        LEFT JOIN tasks t ON t.task_id = br.task_id
        LEFT JOIN users u ON u.id = br.user_id
        LEFT JOIN tutorium tut ON tut.tutorium_id = br.tutorium_id
        WHERE {filter_sql}
        ORDER BY t.task_id ASC, attendance DESC""", (filter_parameter,))
    slots = cur.fetchall()
    cur.execute("""SELECT tutorium_id, task_id, SUM(confirmed) as confirmed FROM booking_requests br GROUP BY tutorium_id, task_id""")
    state_tuts = cur.fetchall()
    state_tuts = {(x['tutorium_id'], x['task_id']):x['confirmed'] for x in state_tuts}

    cur.execute("SELECT * FROM tutorium")
    tutorials = cur.fetchall()
    return render_template("booking_admin.html", slots=slots, state_tuts=state_tuts, tutorials=tutorials, **args)

@bp.route("/approve", methods=["POST"])
@tutor_required
def approve():
    cur = get_db().cursor()
    req_id = request.form.get("req_id")
    selected_tutorial = request.form.get("selected_tutorial")
    args = {}
    if selected_tutorial:
        args["tutorium_id"] = selected_tutorial
    try:
        approve_status = int(request.form.get("approve_status"))
    except TypeError:
        return "approve_status should be int", 500

    if approve_status not in (1,0):
        return "approve_status should be 1 or 0", 500

    cur.execute("update booking_requests set confirmed = ? where req_id = ?", [approve_status, req_id]) 
    print("Selected Tutorial:", selected_tutorial)
    return redirect(url_for('.tutor_overview', **args))

