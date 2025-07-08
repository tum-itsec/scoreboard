from flask import Blueprint, render_template, request, current_app
from .util import *

bp = Blueprint("presentations", __name__, url_prefix="/presentations")


# Use the config to determine what team_id in the presentations table should refer
# to: A user_id if the presentation is on a per user basis or a team_id if
# on a per team basis
# TODO: Rename team_id in tasks_presentations table
def get_subject_query():
    if current_app.config["PRESENTATIONS_PER_USER"]:
        subject_query = """
            SELECT
                id as subject_id,
                IIF(u.displayname IS NOT NULL, u.displayname, u.vorname || ' ' || u.nachname) as subject_name
            FROM users u"""
        subject_description = "Student"
    else:
        subject_query = """
            SELECT
                team_id as subject_id,
                CASE WHEN t.teamname IS NULL THEN 'Team ' || t.team_id ELSE t.teamname END as subject_name
            FROM teams t"""
        subject_description = "Team Name"
    return subject_query, subject_description

@bp.route("/")
@tutor_required
def presentations():
    filter_sql = []
    if week := request.args.get("week", type=int):
        filter_sql.append(f"""strftime("%W", tp.presentation_date)='{week}'""")
    if tutorium_id := request.args.get("tutorium_id", type=int):
        filter_sql.append(f"""tp.tutorium_id = {tutorium_id}""")


    if filter_sql:
        filter_sql = " AND ".join(filter_sql)
        filter_sql = "WHERE " + filter_sql
    else:
        filter_sql = ""
    print(filter_sql)

    cur = get_db().cursor()
    subject_query, subject_description = get_subject_query()
    cur.execute(f"""
    WITH subject_table AS 
    ({subject_query})
    SELECT
    tp.presentation_id,
    tp.team_id,
    tp.successful,
    sub.subject_name,
    ts.task_long,
    ts.task_short,
    tu.description,
    tp.presentation_date,
    tp.tutor_id,
    IIF(u.displayname IS NOT NULL, u.displayname, u.vorname || ' ' || u.nachname) AS tutor_name,
    tp.comments
    FROM task_presentations tp
    LEFT JOIN subject_table sub ON sub.subject_id = tp.team_id
    LEFT JOIN users u ON tp.tutor_id=u.id
    LEFT JOIN tasks ts USING(task_id)
    LEFT JOIN tutorium tu USING(tutorium_id)
    {filter_sql}
    ORDER BY tp.team_id, tp.task_id
    """)
    
    all_presentations = [dict(i) for i in cur.fetchall()]
    held_presentations = [i for i in all_presentations if i["team_id"] is not None]
    if request.args.get("mode") == "unused":
        dead_presentations = [i for i in all_presentations if i["team_id"] is None]
        return render_template("presentations.html", presentations=dead_presentations, tutor_id=session["user-id"], unused_mode=True)

    return render_template("presentations.html", presentations=held_presentations, tutor_id=session["user-id"], unused_mode=False)

@bp.route("/stats")
@tutor_required
def stats():
    cur = get_db().cursor()
    # Calc a few stats how many teams already have presented
    cur.execute("""
        WITH presentations_per_teams 
            as (SELECT t.team_id, COUNT(tp.team_id) as cnt 
                from teams t 
                LEFT JOIN task_presentations tp ON tp.team_id = t.team_id 
                WHERE t.deleted is null and (successful=1 or successful is null) 
                GROUP by t.team_id),
            points_per_team
            as (SELECT t.team_id, cast(SUM(tg.points)/5 as int)*5 as points 
                from teams t 
                INNER JOIN task_grading tg USING(team_id) 
                WHERE deleted_time is null 
                GROUP BY t.team_id)

        SELECT cnt, points || ' - ' || CAST(points+5 as TEXT) as points, COUNT(cnt) as cnt_no, GROUP_CONCAT(team_id, ',') as teams 
            FROM presentations_per_teams a 
            INNER JOIN points_per_team b USING(team_id) 
            GROUP BY cnt, points 
            ORDER BY cnt
    """)
    stats = cur.fetchall()

    cur.execute("""
        SELECT 
            strftime('%W', presentation_date) as week,
            tu.description as tutorium,
            tutorium_id,
            COUNT(presentation_id) as cnt,
            SUM(successful) as successful_cnt,
            sum(case when team_id is null then 1 else 0 end) as unused_cnt,
            sum(case when successful = 0 and team_id is not null then 1 else 0 end) as failed_cnt
        FROM task_presentations p
        LEFT JOIN tutorium tu USING(tutorium_id)
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)

    stats2 = cur.fetchall()

    cur.execute("""SELECT team_id, successful FROM task_presentations tp""")

    counters = dict()

    all_presentations = [dict(i) for i in cur.fetchall()]
    held_presentations = [i for i in all_presentations if i["team_id"] is not None]

    counters["total_pres_count"] = len(all_presentations)
    counters["dead_pres_count"] = len(all_presentations) - len(held_presentations)
    counters["succ_pres_count"] = len([i for i in held_presentations if i["successful"] == 1])
    counters["failed_pres_count"] = len(held_presentations) - counters["succ_pres_count"]

    cur.execute("""
        WITH presentations_per_teams 
            as (SELECT t.team_id, COUNT(tp.team_id) as cnt
                from teams t 
                LEFT JOIN task_presentations tp ON tp.team_id = t.team_id 
                WHERE t.deleted is null and (successful=1 or successful is null) 
                GROUP by t.team_id)

        SELECT SUM(weight) FROM 
        (SELECT ppt.team_id, (?1 - cnt) as weight FROM presentations_per_teams ppt WHERE cnt < ?1 and ppt.team_id in
            (SELECT g.team_id FROM task_grading g)
            GROUP BY 1)
        """, [current_app.config["REQ_PRESENTATIONS"]])
    nr_missing_pres = cur.fetchone()[0]

    cur.execute("""
        SELECT count(t.team_id) FROM teams t WHERE t.team_id not in (SELECT g.team_id FROM task_grading g)
        """)
    nr_never_active_teams = cur.fetchone()[0]
    

    return render_template("presentations_stats.html", stats=stats, stats2=stats2, counters=counters, nr_missing_pres=nr_missing_pres, nr_never_active_teams=nr_never_active_teams)

@bp.route("/add", methods = ["POST", "GET"])
@tutor_required
def add_presentation():
    subject_query, subject_description = get_subject_query()
    if request.method == "POST":
        cur = get_db().cursor()
        subject_id = request.form.get("key", "").strip()
        task_id = request.form.get("task_id", "").strip()
        tutorium_id = request.form.get("tutorium_id", "").strip()
        date = request.form.get("date", "")
        if not date:
            flash("Please enter the date!")
            return redirect("/presentations/add")
        comments = request.form.get("comments", "").strip()

        cur.execute(f"{subject_query} WHERE subject_id=?", (subject_id,))
        subject_ids = cur.fetchall()
        if len(subject_ids) != 1:
            flash(f"The {subject_description} could not be found on the database!")
            return redirect("/presentations/add")
        subject_id = subject_ids[0][0]
        success = request.form.get("successful", 0)
        cur.execute("""
        INSERT INTO task_presentations (team_id, task_id, tutorium_id, tutor_id, presentation_date, comments, successful) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (subject_id, task_id, tutorium_id, session["user-id"], date, comments, success))
        flash("Presentation successfully added", category="success")
        return redirect("/presentations")
    cur = get_db().cursor()
    cur.execute("SELECT * FROM tutorium ORDER BY tutor_id=? DESC NULLS LAST, tutorium_id ASC", (session['user-id'],))
    tutorials = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT * FROM tasks ORDER BY order_num")
    tasks = [dict(i) for i in cur.fetchall()]
    cur.execute(subject_query)
    teams = [{"key": k[0], "value": k[1]} for k in cur.fetchall()]
    return render_template("presentations_add.html", tutorials=tutorials, tasks=tasks, teams=teams, edit=False, data=None, subject_description=subject_description)


def update_presentation(presentation_id):
    params = {k: request.form[k] for k in ["task_id", "tutorium_id", "presentation_date", "comments"]}
    cur = get_db().cursor()
    cur.execute("SELECT tutor_id FROM task_presentations WHERE presentation_id=?", (presentation_id,))
    tutor_id = cur.fetchone()[0]
    if not tutor_id == session["user-id"]:
        return False

    date = request.form.get("presentation_date", "")
    if not date:
        flash("Please enter the date!")
        return redirect("/presentations/edit/" + str(presentation_id))
    params["presentation_date"] = date
    successful = request.form.get("successful", 0)

    sql = "UPDATE task_presentations SET {}, successful=:successful WHERE presentation_id=:presentation_id".format(",".join(f"{k}=:{k}" for k in params.keys()), successful, presentation_id)
    params["presentation_id"] = presentation_id
    params["successful"] = successful
    cur.execute(sql, params)
    return True

@bp.route("/edit/<int:presentation_id>", methods=["GET", "POST"])
@tutor_required
def presentation_edit(presentation_id):
    subject_query, subject_description = get_subject_query()
    if request.method == "POST":
        if not update_presentation(presentation_id):
            flash("Only the tutor that created the presentation is allowed to update it!")
        else:
            flash("Presentation successfully updated", category="success")
        return redirect("/presentations")

    cur = get_db().cursor()
    cur.execute("""SELECT * FROM task_presentations tp
                    LEFT JOIN tasks ta USING(task_id)
                    LEFT JOIN tutorium USING(tutorium_id)
                    WHERE presentation_id=?""", (presentation_id,))
    curvals = dict(cur.fetchone())
    curvals["prevDate"] = curvals["presentation_date"]
    cur.execute("SELECT * FROM tutorium")
    tutorials = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT * FROM tasks ORDER BY order_num")
    tasks = [dict(i) for i in cur.fetchall()]
    cur.execute(f"{subject_query} WHERE subject_id=?", (curvals["team_id"],))
    subjects_result = cur.fetchone()
    if subjects_result:
        subjects_result = dict(subjects_result)
        curvals["teamname"] = subjects_result["subject_name"]
    else:
        curvals["teamname"] = None
    return render_template("presentations_add.html", tutorials=tutorials, tasks=tasks, teams=None, edit=True, data=curvals, subject_description=subject_description)

def delete_presentation(presentation_id):
    cur = get_db().cursor()
    cur.execute("SELECT tutor_id FROM task_presentations WHERE presentation_id=?", (presentation_id,))
    tutor_id = cur.fetchone()[0]
    if not tutor_id == session["user-id"]:
        return False

    cur.execute("DELETE FROM task_presentations WHERE presentation_id=?", (presentation_id,))
    return True


@bp.route("/delete/<int:presentation_id>", methods=["GET", "POST"])
@tutor_required
def presentation_delete(presentation_id):
    subject_query, subject_description = get_subject_query()
    if request.method == "POST":
        if not delete_presentation(presentation_id):
            flash("Only the tutor that created the presentation is allowed to delete it!")
        else:
            flash("Presentation successfully deleted", category="success")
        return redirect("/presentations")

    cur = get_db().cursor()
    cur.execute("""SELECT * FROM task_presentations tp
                    LEFT JOIN tasks ta USING(task_id)
                    LEFT JOIN tutorium tu USING(tutorium_id)
                    WHERE presentation_id=?""", (presentation_id,))
    curvals = dict(cur.fetchone())
    curvals["prevDate"] = curvals["presentation_date"]
    cur.execute(f"{subject_query} WHERE subject_id=?", (curvals["team_id"],))
    subjects_result = cur.fetchone()
    if subjects_result:
        subjects_result = dict(subjects_result)
        curvals["teamname"] = subjects_result["subject_name"]
    else:
        curvals["teamname"] = None
    return render_template("presentations_delete.html", data=curvals, subject_description=subject_description)


@bp.route("/add/unused", methods = ["POST", "GET"])
@tutor_required
def unused_presentation():
    if request.method == "POST":
        cur = get_db().cursor()
        task_id = request.form.get("task_id", "").strip()
        tutorium_id = request.form.get("tutorium_id", "").strip()
        date = request.form.get("date", "")
        if not date:
            flash("Please enter the date!")
            return redirect("/presentations/add")
        comments = request.form.get("comments", "").strip()
        success = 0
        cur.execute("""
        INSERT INTO task_presentations (task_id, tutorium_id, tutor_id, presentation_date, comments, successful) VALUES (?, ?, ?, ?, ?, ?)
        """, (task_id, tutorium_id, session["user-id"], date, comments, success))
        flash("Unused slot successfully added", category="success")
        return redirect("/presentations")
    cur = get_db().cursor()
    cur.execute("SELECT * FROM tutorium ORDER BY tutor_id=? DESC NULLS LAST, tutorium_id ASC", (session['user-id'],))
    tutorials = [dict(i) for i in cur.fetchall()]
    cur.execute("SELECT * FROM tasks ORDER BY order_num")
    tasks = [dict(i) for i in cur.fetchall()]
    return render_template("presentations_unused.html", tutorials=tutorials, tasks=tasks)
