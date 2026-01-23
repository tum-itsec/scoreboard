#!/usr/bin/env python3

from collections import defaultdict
from logging.handlers import SMTPHandler
import base64
import binascii
import logging
import math
import re
import struct
import sys
import time

import click
from flask import Flask, render_template, session, redirect, url_for, request, g, flash, send_from_directory, abort, send_file, request

from board.util import *
from board import teaminfo, materials, gradeupload, taskadmin, sshkeys, tasks, users, autograde, presentations, tutorials, eastereggs, booking, timesheet

try:
    import config
except ImportError:
    print("Please create a config.py before using the scoreboard!")
    import sys
    sys.exit(-1)

from Crypto.Cipher import DES

app = Flask(__name__)
app.config.from_object(config.Config)
app.register_blueprint(teaminfo.bp)
app.register_blueprint(materials.bp)
app.register_blueprint(gradeupload.bp)
app.register_blueprint(taskadmin.bp)
app.register_blueprint(sshkeys.bp)
app.register_blueprint(tasks.bp)
app.register_blueprint(users.bp)
app.register_blueprint(autograde.bp)
app.register_blueprint(presentations.bp)
app.register_blueprint(tutorials.bp)
app.register_blueprint(booking.bp)
app.register_blueprint(eastereggs.bp)
app.register_blueprint(timesheet.bp)

@click.group()
def cli():
    pass

# Load plugins from configuration
menuitems = {"tutor": [], "admin": []}
for plugin_pkg in app.config["PLUGINS"]:
    import importlib
    plug = importlib.import_module("plugins." + plugin_pkg)
    app.register_blueprint(plug.bp)
    plug_menu = plug.get_menuitems()
    menuitems["tutor"].extend(plug_menu.get("tutor", []))
    menuitems["admin"].extend(plug_menu.get("admin", []))
    register_cli = getattr(plug, "register_cli", None)
    if register_cli:
        register_cli(cli)

#from werkzeug.middleware.profiler import ProfilerMiddleware
#app.wsgi_app = ProfilerMiddleware(app.wsgi_app)

@app.errorhandler(404)
def page_not_found(e):
    # note that we set the 404 status explicitly
    return render_template('404.html'), 404

def datetime_filter(x):
    if x:
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(x))
    return ""

app.jinja_env.filters["datetime"] = datetime_filter

app.jinja_env.globals.update(
        is_admin=is_admin,
        is_tutor=is_tutor,
        board_title=app.config["BOARD_TITLE"],
        plugmenu=menuitems)

if app.config.get("EMAIL_BUGS", False) == True:
    # Register SMTP handler to mail bugs to configured recipients
    recipients = app.config.get("EMAIL_BUGS_TO")
    sender = app.config.get("EMAIL_BUGS_FROM")
    mailserver = app.config.get("EMAIL_BUGS_VIA")
    credentials = app.config.get("EMAIL_BUGS_CREDENTIALS")
    subject = app.config.get("EMAIL_BUGS_SUBJECT")
    assert isinstance(recipients, list), "EMAIL_BUGS_TO must be a list of recipients"
    assert isinstance(sender, str), "EMAIL_BUGS_FROM must contain the sender's email address"
    assert isinstance(mailserver, str), "EMAIL_BUGS_VIA must contain the SMTP server's address"
    assert credentials is None or len(credentials) == 2, "Invalid EMAIL_BUGS_CREDENTIALS"
    assert isinstance(subject, str), "EMAIL_BUGS_SUBJECT must contain the email's subject line"
    handler = SMTPHandler(
        mailhost=mailserver,
        fromaddr=sender,
        toaddrs=recipients,
        subject=subject,
        credentials=credentials,
        secure=tuple() # NB: TLS is always via STARTTLS, and only enabled if credentials are given
    )
    handler.setLevel(logging.ERROR)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    ))
    app.logger.addHandler(handler)

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.before_request
def check_maintenance():
    if app.config["MAINTENANCE"] and request.endpoint != "maintenance" and not request.path.startswith("/static/"):
        return redirect("/maintenance")

@app.before_request
def anti_csrf():
    # These are the ones that according to RFC7231 mustn't modify state
    if request.method in ["GET", "HEAD", "OPTIONS", "TRACE"]:
        return
    sec_fetch_site = request.headers.get("Sec-Fetch-Site", None)
    if sec_fetch_site is None or sec_fetch_site == "same-origin":
        return
    abort(403)

if not app.config.get("DISABLE_ACTIVITY_LOG"):
    @app.before_request
    def log_activity():
        if is_logged_in():
            cur = get_db().cursor()
            cur.execute("UPDATE users SET last_active = strftime('%s','now') WHERE id = ?", [session['user-id']])

@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; script-src 'self'; object-src 'none'; form-action 'self';"
    return response

@app.route("/maintenance")
def maintenance():
    if not app.config["MAINTENANCE"]:
        return redirect("/")
    return render_template("maintenance.html")

@app.route("/")
def index():
    if is_logged_in():
        return redirect("/scoreboard")
    return render_template("login.html", welcome_text=app.config["WELCOME_TEXT"])

@app.route("/scoreboard")
@login_required
def scoreboard():
    # Replay submission log
    cur = get_db().cursor()
    #cur.execute("SELECT task_id, u.vorname || ' ' || u.nachname as user FROM flag_submissions LEFT JOIN users u ON u.id = user_id ORDER BY flag_time")

    # Fetch number of tasks
    cur.execute("SELECT task_id, task_short FROM tasks WHERE from_date < strftime('%s','now') ORDER BY order_num")
    tasks = [r for r in cur.fetchall()]

    cur.execute("SELECT s.task_id, s.team_id FROM flag_submissions s LEFT JOIN teams t ON s.team_id = t.team_id WHERE t.deleted IS NULL ORDER BY flag_time")

    task_ctr = {k["task_id"]: 1 for k in tasks}
    state = defaultdict(lambda: {k["task_id"]: 0 for k in tasks})

    for r in cur.fetchall():
        cur_state = state[r["team_id"]]
        if cur_state[r["task_id"]] == 0:
            cur_state[r["task_id"]] = task_ctr[r["task_id"]]
            task_ctr[r["task_id"]] += 1

    # Sort
    sorted_state = sorted(
        [(k, v, sum(v.values()), sum(1 for x in v.values() if x > 0)) for k, v in state.items()],
        key=lambda x: (-x[3], x[2])
    )   
    #print([(k,sum(v),v) for k,v in sorted_state])

    teams = None
    cur.execute("""SELECT
    t.team_id,
    CASE WHEN tt.teamname IS NULL THEN 'Team ' || tt.team_id ELSE tt.teamname END as teamname,
    GROUP_CONCAT(u.vorname || ' ' || u.nachname, ', ') as member
    FROM team_members t
    LEFT JOIN users u ON u.id = t.member_id
    LEFT JOIN teams tt ON t.team_id = tt.team_id
    WHERE tt.deleted IS NUll
    GROUP BY t.team_id""")
    teams = {res['team_id']: res for res in cur.fetchall()}

    show_names_in_scoreboard = is_admin() or app.config["SHOW_NAMES_TO_ALL"]

    feedback_data = None
    if "last-solved" in session:
        task_id = session["last-solved"]
        del session["last-solved"]
        if "pending-feedback" in session:
            session["pending-feedback"].append(task_id)
        else:
            session["pending-feedback"] = [task_id]

        cur.execute("SELECT task_long FROM tasks WHERE task_id = ?", (task_id,))
        res = cur.fetchone()
        if res:
            feedback_data = {
                "task_long": res["task_long"],
                "url": f"/tasks/{task_id}/feedback"
            }

    return render_template("scoreboard.html", scoreboard=sorted_state, teams=teams, tasks=tasks, show_names=show_names_in_scoreboard, feedback_data=feedback_data)

@app.route("/lookup")
@tutor_required
def lookup():
    q = request.args.get("q")
    # Clear name
    q = re.sub(r'\W*\[[^\]]*\]', "", q)
    cur = get_db().cursor()
    cur.execute("""SELECT tm.team_id FROM team_members tm LEFT JOIN users u ON u.id = tm.member_id WHERE u.vorname || ' ' || u.nachname LIKE :q OR u.displayname LIKE :q ORDER BY tm.team_id DESC LIMIT 1""", {"q": q})
    row = cur.fetchone()
    if row is None:
        return redirect("/404")
    return redirect(f"/teaminfo/{row[0]}")


@app.route("/logout")
@login_required
def logout():
    session.pop("user-id")
    return redirect("/")

@app.route("/flag", methods=["POST"])
@login_required
def flag():
    team_id = get_team_from_db()

    if not team_id:
        flash("You have to form a team with another student in order to submit flags!")
        return redirect("/scoreboard")
    flag = request.form["flag"].strip()

    # Check for an easter egg
    cur = get_db().cursor()
    cur.execute("SELECT * FROM easteregg_flags WHERE flag = ?", (flag,))
    if m := cur.fetchone():
        # Updated accessed counter
        cur.execute("UPDATE easteregg_flags SET counter=counter+1 WHERE easteregg_id=?", (m['easteregg_id'],))

        # Redirect user to target
        return redirect(m['link'])

    fdec = check_flag(flag)
    if fdec is not None:
        cur = get_db().cursor()
        cur.execute("SELECT user_id, team_id FROM flag_submissions WHERE flag=?", (flag,))
        data = cur.fetchone()

        # Check if task is already available
        cur.execute("SELECT * FROM tasks WHERE task_id=?", [fdec['task_id']])
        task_data = cur.fetchone()
        if task_data['from_date'] > (fdec['ftime'] / 1e6):
            flash("You are really fast! The task which created this flag hasn't even been released so far. Please wait until it started and submit a new flag then!")
            return redirect("/scoreboard")

        if data:
            team = get_team_from_db()
            if data["user_id"] == session["user-id"] or data["team_id"] == team:
                # This was already submitted -- by the same team!
                flash("You already submitted this flag!")
            else:
                log_event(session["user-id"], Category.STUDENT_INCIDENT, f"User {session['user-id']} on team {team} submitted flag {flag} for task {fdec['task_id']} previously submitted by user {data['user_id']} on team {data['team_id']}")
                flash("We already got this flag submitted by another team! Flag sharing is forbidden!")
        else:
            cur.execute("INSERT INTO flag_submissions (flag, team_id, user_id, task_id, submission_time, flag_time) VALUES (?,?,?,?,strftime('%s','now'),?)", (flag, team_id, session["user-id"], fdec["task_id"], fdec["ftime"]))
            flash("Looks like a flag! Congratz!", "success")
            session["last-solved"] = fdec["task_id"]
    else:
        flash("This does not look like a flag :/")
    return redirect("/scoreboard")

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")

@app.route("/flagcheck")
@tutor_required
def flagcheck():
    flag = request.args.get("flag")
    if flag:
        flag = flag.strip()
        cur = get_db().cursor()
        cur.execute("SELECT * FROM easteregg_flags WHERE flag = ?", (flag,))
        if m := cur.fetchone():
            flash(f"Easteregg-Flag; Link: {m['link']}")
        else:
            fdec, fdetails = check_flag_details(flag)
            if fdec is not None:
                t = time.localtime(fdec['ftime'] // 1e6)
                tstr = time.strftime('%Y-%m-%d %H:%M:%S', t)
                flash(f"Valide Flag für Aufgabe {fdec['task_short']}, erstellt am {tstr}", category="success")
            else:
                flash(f"Keine valide Flag! Details: {fdetails}")
    return render_template("flagcheck.html")

@app.route("/team/join", methods=["POST"])
@login_required
def team_join():
    join_code = request.form["join_code"].strip()
    try:
        join_code_dec = base64.b32decode(join_code.replace("0","O") + "="*(len(join_code)%5))
    except:
        print(f"Join code: Base64 decoding failed: {join_code}")
        flash("Ungültiger Join-Code!")
        return redirect("/team")

    cry = DES.new(key=app.config["JOIN_KEY"], mode=DES.MODE_ECB)
    try:
        mate_user_id, jtime = struct.unpack("<II", cry.decrypt(join_code_dec))
    except struct.error:
        print(f"Join code: Unpacking failed: {join_code}")
        flash("Ungültiger Join-Code!")
        return redirect("/team")
    now = time.time()

    # Check for outdated join code
    if not now - app.config["JOIN_MINUTES_VALID"]*60 < jtime < now:
        flash("Dein Join-Code ist bereits abgelaufen")
        return redirect("/team")

    # Check if we are about to join the team of a different user
    if session["user-id"] == mate_user_id:
        flash("Das ist dein eigener Join-Code! Bilde ein Team mit einem anderen Studenten!")
        return redirect("/team")

    # Check for mate existance in DB
    mate_name = get_user_name(mate_user_id)
    if mate_name is None:
        flash("Ungültiger Join-Code!")
        return redirect("/team")

    if not create_team([mate_user_id, session["user-id"]]):
        return redirect("/team")
    flash("Du bist dem Team von {} beigetreten".format(mate_name), "success")
    return redirect("/team")

@app.route("/team/singleteam", methods=["POST"])
@login_required
def create_one_person_team():
    if not app.config["SINGLETEAMS_ALLOWED"]:
        return redirect("/team")
    create_team([session["user-id"]])
    return redirect("/team")

@app.route("/team")
@login_required
def team():
    team_id = get_team_from_db()
    cur = get_db().cursor()
    cur.execute("""
    SELECT t.team_id, IIF(u.displayname IS NOT NULL, u.displayname, u.vorname || ' ' || u.nachname) as name, tt.teamname
    FROM team_members t
    LEFT JOIN users u ON u.id = t.member_id
    LEFT JOIN teams tt ON t.team_id = tt.team_id
    WHERE tt.team_id=? and tt.deleted is null""", (team_id, ))
    res = cur.fetchall()
    if res:
        teamname = generate_teamname(res[0]["teamname"], res[0]['team_id'])
        return render_template("team.html",
            in_team=True, teamname=teamname,teammember=[x['name'] for x in res])
    else:
        cry = DES.new(key=app.config["JOIN_KEY"], mode=DES.MODE_ECB)
        join_code = cry.encrypt(struct.pack("<II", session["user-id"], int(time.time())))
        join_code = base64.b32encode(join_code).rstrip(b"=").decode()
    return render_template("team.html",
        in_team=False, join_code=join_code, minutes_valid=app.config["JOIN_MINUTES_VALID"], singleteams=app.config["SINGLETEAMS_ALLOWED"])

@app.route("/team/changename", methods=["POST"])
@login_required
def team_changename():
    cur = get_db().cursor()
    team_id = get_team_from_db()
    new_name = request.form["teamname"]
    if not re.match(r"^[A-z0-9 ]*$", new_name):
        flash("Der neue Teamname darf nur alphanumerische Zeichen und Leerzeichen enthalten!")
        return redirect("/team")

    new_name = new_name.strip()
    if len(new_name) == 0:
        flash("Nur Leerzeichen im Namen oder ein leerer Name?! Sehr witzig, aber nein...")
        return redirect("/team")

    if len(new_name) > 32:
        flash("Wow... Sehr kreativ, aber auch sehr lang! Die maximale Länge für Teamnamen beträgt 32 Zeichen!")
        return redirect("/team")

    m = re.match(r"Team (\d+)", new_name)
    if m and int(m.group(1)) != team_id:
        flash("Olalala... Sieht so aus als würdest du vorgeben wollen ein anderes Team zu. Mehr Glück beim nächsten Mal!")
        return redirect("/team")

    cur.execute("""SELECT COUNT(*) FROM teams WHERE teamname = ? AND deleted IS NULL""", [new_name])
    if cur.fetchone()[0] > 0:
        flash("Dieser Teamname ist leider schon vergeben. Bitte suche dir einen anderen aus!")
        return redirect("/team")

    cur.execute("UPDATE teams SET teamname =? WHERE team_id=?", [new_name, get_team_from_db()])
    return redirect("/team")

@app.route("/comments")
@tutor_required
def comments():
    # Find task/team combinations with comments other than grading entries
    cur = get_db().cursor()
    cur.execute("""
        SELECT
            a.*,
            g.corrector AS last_corrector,
            MAX(g.created_time) AS last_correction_time,
            g.comment AS last_correction_text
        FROM
        (
            SELECT
                s.task_id,
                s.team_id,
                x.task_long,
                t.teamname,
                s.author AS last_comment_author,
                MAX(s.created_time) AS last_comment_time,
                s.text AS last_comment_text
            FROM submission_comments s
            LEFT OUTER JOIN teams t
            ON
                t.team_id = s.team_id
            LEFT OUTER JOIN tasks x
            ON
                x.task_id = s.task_id
            GROUP BY s.task_id, s.team_id
        ) a
        LEFT OUTER JOIN task_grading g
        ON
            g.task_id = a.task_id AND
            g.team_id = a.team_id AND
            g.deleted_time IS NULL
        GROUP BY a.task_id, a.team_id
    """)
    threads = []
    for row in cur:
        last_is_comment = row["last_comment_time"] > row["last_correction_time"]
        last_event_text = row["last_comment_text"] if last_is_comment else row["last_correction_text"]
        last_event_author = get_user_name(row["last_comment_author"]) if last_is_comment else row["last_corrector"]
        last_event_time = row["last_comment_time"] if last_is_comment else row["last_correction_time"]
        acted_on = (not last_is_comment) or row["last_comment_author"] not in get_team_members(row["team_id"]) # acted on: new grading upload, or a comment by a non-team-member.
        threads.append({
            "team_name": row["teamname"] if row["teamname"] is not None else f"Team {row['team_id']}",
            "team_id": row["team_id"],
            "task_long": row["task_long"],
            "task_id": row["task_id"],
            "last_comment": last_event_text,
            "last_author": last_event_author,
            "last_time": last_event_time,
            "acted_on": acted_on
        })
    return render_template("comments.html", threads=threads)

@app.route("/comments/<int:team_id>/<int:task_id>", methods=["GET", "POST"])
@tutor_required
def comment_thread(team_id, task_id):
    if request.method == "POST":
        text = request.form.get("message", "").strip()
        if not text:
            flash("You didn't specify a message!")
        else:
            author = session["user-id"]
            add_comment(task_id, team_id, author, text)
            flash("Comment added", "success")
        return redirect(f"/comments/{team_id}/{task_id}")
    else:
        comments = get_comments(task_id, team_id)
        teammates = get_team_members(team_id)

        cur = get_db().cursor()
        cur.execute("SELECT teamname FROM teams WHERE team_id = ?", (team_id,))
        res = cur.fetchone()
        if not res:
            flash("No such team")
            return redirect("/comments")
        team_name = res["teamname"] or f"Team {team_id}"

        cur.execute("SELECT task_long FROM tasks WHERE task_id = ?", (task_id,))
        res = cur.fetchone()
        if not res:
            flash("No such task")
            return redirect("/comments")
        task_long = res["task_long"] or f"Task {task_id}"

        comments = sorted(({
            **c,
            "by_tutor": c["author"] not in teammates,
            "own": c["author"],
            "author": get_user_name(c["author"]) if isinstance(c["author"], int) else c["author"]
        } for c in comments), key=lambda c: c["time"])

        # TODO: Since this is for complaints, maybe add a link to their submission?
        return render_template("comment_thread.html", comments=comments, team_id=team_id, task_id=task_id, team_name=team_name, task_long=task_long)

@app.route("/shib-login")
def login():
    """This URL is protected by the apache server. Just set a cookie so that
    we can recognize the user"""
    session["user-permanent-id"] = request.headers.get("X-Remoteuser")
    session["user-matrikel"] = request.headers.get("X-Matrikel").encode("iso-8859-1").decode("utf-8")
    session["user-vorname"] = request.headers.get("X-Givenname").encode("iso-8859-1").decode("utf-8")
    session["user-name"] = request.headers.get("X-Sn").encode("iso-8859-1").decode("utf-8")
    session["user-mail"] = request.headers.get("X-Mail")
    uid = request.headers.get("X-Uid")
    gender = request.headers.get("X-Gender")
    session["user-displayname"] = request.headers.get("X-DisplayName").encode("iso-8859-1").decode("utf-8")

    # Create user on demand
    cur = get_db().cursor()
    cur.execute("SELECT * FROM users WHERE permanent_id = ?", (session["user-permanent-id"],))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (permanent_id, matrikel, vorname, nachname, uid, gender, role, email, displayname) VALUES (?,?,?,?,?,?,?,?,?)", (session["user-permanent-id"], session["user-matrikel"], session["user-vorname"], session["user-name"], uid, gender, 0, session['user-mail'], session["user-displayname"]))
    else:
        # In rare circumstances the first- and surname are changed in TUMOnline.
        # Maybe also the mail address and display name change, update the database accordingly
        cur.execute("UPDATE users SET vorname=?, nachname=?, gender=?, email=?, displayname=? WHERE permanent_id=? LIMIT 1", (session['user-vorname'], session['user-name'], gender, session['user-mail'], session["user-displayname"], session["user-permanent-id"],))

    cur.execute("SELECT id, role FROM users WHERE permanent_id = ?", (session["user-permanent-id"],))
    res = cur.fetchone()
    session["user-id"] = res["id"]
    session["user-role"] = res["role"]

    # Check if the user is on the list of allowed students (for seminars etc.)
    if res["role"] not in TUTOR_ROLES and app.config["USER_ALLOWLIST_TABLE"] is not None:
        # Can't parametrize the allowlist table name, so concatenation it is...
        # This comes from the config so it shouldn't be injectable
        cur.execute(f"SELECT * FROM {app.config['USER_ALLOWLIST_TABLE']} WHERE matrikel=?", [session["user-matrikel"]])
        if not cur.fetchone():
            session.pop("user-id")
            return render_template("login-denied.html", contact_info=app.config["CONTACT_INFO"])

    # do this last so that session becomes valid as late as possible, to guard against exceptions during login process
    session["logged-in-until"] = time.time() + app.config["MAX_SESSION_SECONDS"]
    return redirect_to_post_login_url()


@app.route("/alternative-login", methods=["POST", "GET"])
def alternative_login():
    if request.method == "POST" and "email" in request.form and "password" in request.form:
        # Try to login
        cur = get_db().cursor()

        cur.execute("SELECT * FROM users WHERE email=?", (request.form["email"],))
        res = cur.fetchone()
        if res and res["password"]:
            salt, db_pw = res["password"].split(":")
            salt = binascii.unhexlify(salt)
            if pw_hash(request.form["password"].encode(), salt).hex() == db_pw:
                session["user-name"] = res ["nachname"]
                session["user-vorname"] = res["vorname"]
                session["user-matrikel"] = res["matrikel"]
                session["user-id"] = res["id"]
                session["user-role"] = res["role"]
                session["user-displayname"] = res["displayname"]
                session["logged-in-until"] = time.time() + app.config["MAX_SESSION_SECONDS"]
                return redirect_to_post_login_url()
            else:
                return redirect("/alternative-login")
        else:
            return redirect("/alternative-login")
    else:
        return render_template("alternative-login.html")

@app.route("/set-role/<int:role>")
@tutor_required
def set_role(role):
    if role in ADMIN_ROLES and not is_admin():
        return redirect("/")
    if role in TUTOR_ROLES and not is_tutor():
        return redirect("/")

    session["user-role"] = role
    return redirect("/")

@app.route("/impersonate/<int:user_id>")
@admin_required
def impersonate(user_id):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (user_id,))

    res = cur.fetchone()
    session["user-id"] = res["id"]
    session["user-role"] = res["role"]
    session["user-matrikel"] = res["matrikel"]
    session["user-vorname"] = res["vorname"]
    session["user-name"] = res["nachname"]
    session["user-displayname"] = res["displayname"]

    return redirect("/scoreboard")

@app.route("/presenter-view")
@admin_required
def presenter_view():
    # Drop privileges to normal user for demonstration purposes to not leak PII while screen sharing etc.
    session["user-role"] = 0
    # Hide the user's PII too
    session["user-matrikel"] = "hidden"
    return redirect("/scoreboard")

@cli.command()
def create_db():
    init_db()
    set_teamidoffset(app)
@cli.command()
def upgrade_db():
    init_db()

@cli.command()
@click.argument("email")
@click.argument("firstname")
@click.argument("name")
@click.option("--matrikel", "-m")
def create_user(email, firstname, name, matrikel):
    import getpass
    pw = getpass.getpass()
    add_user(email, firstname, name, matrikel, pw)

@cli.command()
@click.argument("task")
@click.option("-d", "--due")
def get_newest_submissions(task, due):
    cur = get_db().cursor()
    if due:
        dt = time.strptime(due,"%Y-%m-%d-%H-%M")
        dts = int(time.mktime(dt))
        cur.execute("""
        SELECT ts.task_id, MAX(ts.submission_time) as submission_time, ts.filepath, ts.original_name
          FROM task_submissions ts
          LEFT JOIN tasks t ON t.task_id = ts.task_id
          WHERE t.task_short=? and ts.submission_time < ?
          GROUP BY ts.task_id,ts.team_id
        """, (task,dts))
    else:
        cur.execute("""
        SELECT ts.task_id, MAX(ts.submission_time) as submission_time, ts.filepath, ts.original_name
          FROM task_submissions ts
          LEFT JOIN tasks t ON t.task_id = ts.task_id
          WHERE t.task_short=?
          GROUP BY ts.task_id,ts.team_id
        """, (task,))
    for r in cur.fetchall():
        print(r["filepath"])

@cli.command()
@click.argument("filename")
def export_grading(filename):
    cur = get_db().cursor()
    cur.execute("""SELECT u.vorname, u.nachname, u.matrikel,SUM(g.points) as points
            FROM task_grading g
            LEFT JOIN team_members m ON m.team_id = g.team_id
            LEFT JOIN users u ON m.member_id = u.id
            LEFT JOIN (SELECT m.member_id as user_id, SUM(successful) as presentations FROM task_presentations p LEFT JOIN team_members m ON m.team_id=p.team_id GROUP BY m.member_id) p ON p.user_id = u.id
            WHERE g.deleted_time IS NULL AND u.matrikel IS NOT NULL AND u.matrikel != "(null)" AND p.presentations >=2
            GROUP BY u.id""")
    print("matrikel;problem;subproblem;credit")
    for u in cur.fetchall():
        pointbonus = math.ceil(((min(u['points'],28.5) / 28.5) * 10)*2) / 2
        # pointbonus = min(11.5, pointbonus)
        if pointbonus < 0.001:
            continue
        print(";".join(map(str, [u['matrikel'], "1", "1", pointbonus])))

@cli.command()
@click.argument("taskshort")
@click.argument("taskname")
@click.argument("flaguid")
@click.argument("starttime")
@click.argument("deadline")
@click.argument("submission_expected")
@click.argument("order_num")
def add_task(taskshort, taskname, flaguid, starttime, deadline, submission_expected, order_num):
    import time
    submission_expected = (submission_expected == "1")
    dt = time.strptime(deadline,"%Y-%m-%d-%H-%M")
    dts = int(time.mktime(dt))
    st = time.strptime(starttime,"%Y-%m-%d-%H-%M")
    sts = int(time.mktime(st))
    order_num = int(order_num)
    print("Creating task {} Short: {} Deadline: {} Submission: {}".format(taskname, taskshort, dts, submission_expected))

    cur = get_db().cursor()
    cur.execute("""INSERT INTO tasks (task_short, task_desc, flag_uid, from_date, due_date, needed, order_num) values (?, ?, ?, ?, ?, ?, ?)""", (taskshort, taskname, flaguid, sts, dts, submission_expected, order_num))

if __name__ == "__main__":
    with app.app_context():
        cli()
