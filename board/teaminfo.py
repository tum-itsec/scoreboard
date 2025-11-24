from flask import Blueprint, flash, redirect, render_template, request, session, send_file
from .util import *

bp = Blueprint("teaminfo", __name__, url_prefix="/teaminfo")

@bp.route("")
@tutor_required
def team_info_overview():
    cur = get_db().cursor()
    cur.execute("SELECT id, vorname || ' ' || nachname FROM users")
    users = [{"key": k[0], "value": k[1]} for k in cur.fetchall()]

    filter_sql = ""
    if teams := request.args.get("teams"):
        teams_sanitized = ",".join(str(int(x)) for x in teams.split(","))
        filter_sql = f"WHERE t.team_id IN ({teams_sanitized})"

    cur.execute(f"""SELECT t.team_id,
                CASE WHEN t.teamname IS NOT NULL THEN t.teamname ELSE 'Team ' ||t.team_id END as teamname,
                datetime(t.created, 'unixepoch', 'localtime') as created,
                datetime(t.deleted, 'unixepoch', 'localtime') as deleted,
                GROUP_CONCAT(IIF(u.displayname IS NOT NULL, u.displayname, u.vorname || ' ' || u.nachname), ', ') as members,
                IFNULL((SELECT SUM(points) FROM task_grading WHERE team_id=t.team_id and deleted_time IS NULL), 0.0) as points,
                (SELECT COUNT(*) FROM task_presentations WHERE team_id=t.team_id and successful=1) as presentations,
                (SELECT datetime(MAX(submission_time),'unixepoch', 'localtime') FROM task_submissions WHERE team_id=t.team_id) as last_submission
            FROM teams t
            LEFT JOIN team_members tm ON tm.team_id = t.team_id
            LEFT JOIN users u ON tm.member_id = u.id
            {filter_sql}
            GROUP BY t.team_id""")

    return render_template("team-admin/list.html", teams=cur.fetchall(), users=users)

@bp.route("/dl/<int:submission>")
@tutor_required
def submission_dl(submission):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM task_submissions s WHERE id= ?", (submission,))
    submission = cur.fetchone()
    # We manually open the file instead of passing the path to send_file
    # because Flask / Werkzeug will try to read from app root instead of cwd
    return send_file(open(submission['filepath'], "rb"), as_attachment=True, download_name=submission['original_name'])

@bp.route("/show/<int:submission>")
@tutor_required
def submission_show(submission):
    cur = get_db().cursor()
    cur.execute("""
        SELECT *, 
        CASE WHEN tt.teamname IS NULL THEN 'Team ' || tt.team_id ELSE tt.teamname END as team,
        IIF(u.displayname IS NOT NULL, u.displayname, u.vorname || ' ' || u.nachname) as name
        FROM task_submissions s 
        LEFT JOIN tasks t USING(task_id)
        LEFT JOIN teams tt USING(team_id)
        LEFT JOIN users u ON u.id = s.user_id
        WHERE s.id= ?""", (submission,))
    submission = cur.fetchone()
    file_content = open(submission['filepath'], "r", errors="replace").read()
    return render_template("team-admin/show_submission.html", file_content=file_content, submission=submission)

@bp.route("/<int:team_id>")
@tutor_required
def team_info(team_id):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM task_grading tg INNER JOIN tasks t ON t.task_id = tg.task_id WHERE tg.team_id = ? ORDER BY tg.task_id, tg.deleted_time DESC", (team_id,))
    grading = cur.fetchall()

    cur.execute("""
    SELECT * FROM task_submissions s 
    LEFT JOIN users u ON u.id == s.user_id 
    LEFT JOIN tasks t ON t.task_id = s.task_id 
    LEFT JOIN (SELECT submission_a_id as pfid FROM plagflags UNION SELECT submission_b_id as pfid FROM plagflags) pf ON pf.pfid = s.id
    WHERE team_id = ?""", (team_id,))
    submissions = cur.fetchall()
    
    isDeleted = cur.execute("""SELECT deleted FROM teams WHERE team_id=?""", (team_id,)).fetchone()[0]

    teamname = cur.execute("SELECT teamname FROM teams WHERE team_id=?", [team_id]).fetchone()[0]
    teamname = generate_teamname(teamname, team_id)

    cur.execute("SELECT u.vorname || ' ' || u.nachname as name FROM team_members LEFT JOIN users u ON u.id = member_id WHERE team_id = ?", [team_id])
    teammember = [x['name'] for x in cur.fetchall()]

    return render_template("team-admin/show.html", grading=grading, submissions=submissions, team_id=team_id, teamname=teamname, teammember=teammember, isDeleted=isDeleted)

@bp.route("/create", methods=["POST"])
@admin_required
def team_info_create():
    # Ignore empty fields
    ids = [x for x in request.form.getlist("key") if x]
    if len(ids) == 0:
        flash("Leeres Team wird nicht angelegt!")
        return redirect("/teaminfo")

    create_team(ids)
    return redirect("/teaminfo")

@bp.route("/<int:team_id>/delete", methods=["POST"])
@admin_required
def team_delete(team_id):
    cur = get_db().cursor()
    cur.execute("UPDATE teams SET deleted = ? WHERE team_id = ?", (int(time.time()), team_id))
    return redirect("/teaminfo")

