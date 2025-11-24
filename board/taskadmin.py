import io
import tempfile
import json
import pathlib
import glob
from flask import current_app, Blueprint, request, render_template, abort, send_from_directory, send_file, jsonify, url_for
from .util import *
from Crypto.Cipher import AES
import zipfile
import time
import markdown
import subprocess

bp = Blueprint("taskadmin", __name__, url_prefix="/taskadmin")

try:
    import markdown.extensions.latex
except ModuleNotFoundError:
    HAS_LATEX = False
else:
    HAS_LATEX = True

def render_markdown(md):
    return markdown.markdown(md, extensions=["markdown.extensions.tables", "markdown.extensions.fenced_code", "markdown.extensions.footnotes", "markdown.extensions.codehilite"] + (["markdown.extensions.latex"] if HAS_LATEX else []))

TIMEFORMAT = "%Y-%m-%dT%H:%M"

def render_taskadmin(edit_record):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM tasks ORDER BY order_num")
    tasks = [dict(x) for x in cur.fetchall()]
    for t in tasks:
        cur.execute("SELECT COUNT(DISTINCT team_id) FROM task_submissions WHERE task_id=?", (t["task_id"],))
        t["submissions_received"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT team_id) FROM flag_submissions WHERE task_id=?", (t["task_id"],))
        t["flags_received"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM task_grading WHERE task_id=? and deleted_time IS NULL", (t["task_id"],))
        t["grading_done"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM task_grading g LEFT JOIN tasks t ON t.task_id = g.task_id WHERE g.task_id=? and points=max_points and deleted_time IS NULL", (t["task_id"],))
        t["full_points"] = cur.fetchone()[0]
        cur.execute("SELECT AVG(rating), COUNT(rating) FROM task_feedback WHERE task_id=?", (t["task_id"],))
        t["avg_rating"], t["number_of_ratings"] = cur.fetchone()
    return render_template("task-admin/list.html", tasks=tasks, edit=edit_record)

@bp.route("", strict_slashes=False, methods=["GET"])
@tutor_required
def task_overview():
    return render_taskadmin({})

def insert_or_update_task(task_id=None):
    if not request.form.get("start", "") or not request.form.get("end", ""):
        abort(400, "Start and end date/time are required")

    params = {k: request.form[k] for k in ["task_short", "task_long", "url"]}
    params["needed"] = ("subexp" in request.form)
    params["autograded"] = ("autograded" in request.form)
    params["bonus"] = ("bonus" in request.form)
    params["presentable"] = ("presentable" in request.form)
    st = time.strptime(request.form["start"],TIMEFORMAT)
    params["from_date"] = int(time.mktime(st))
    dt = time.strptime(request.form["end"],TIMEFORMAT)
    params["due_date"] = int(time.mktime(dt))
    params["order_num"] = int(request.form["order_num"])
    params["max_points"] = float(request.form["max_points"])
    params["file_extensions"] = ",".join(x.strip() for x in request.form["file_extensions"].split(","))
    if task_id:
        params["task_id"] = task_id

    final_path = os.path.join("tasks", request.form["task_short"])

    if "fileupload" in request.files and request.files["fileupload"].filename:
        params["filename"] = request.files["fileupload"].filename
    elif cached_dl := request.form.get("cached_dl"):
        d = pathlib.Path("tasks/tmp") / cached_dl
        d.rename(final_path)
        params["filename"] = cached_dl
    
    # Render Markdown
    params["markdown"] = request.form["markdown"]
    params["markdown_rendered"] = render_markdown(params['markdown'])

    cur = get_db().cursor()
    if not task_id:
        keys = ",".join(params.keys())
        values = ",".join(["?"] * len(params.keys()))
        sql = f"INSERT INTO tasks ({keys}) VALUES ({values})"
        try:
            cur.execute(sql, list(params.values()))
            cur.execute("SELECT last_insert_rowid()")
            task_id = cur.fetchone()[0]
            key = create_flag_key(task_id)
            cur.execute("UPDATE tasks SET flag_key=? WHERE task_id = ?", (key, task_id))
        except sqlite3.IntegrityError:
            flash("You tried to create a task that violates DB integrity. Some dup value?")
    else:
        sql = "UPDATE tasks SET {} WHERE task_id=:task_id".format(",".join(f"{k}=:{k}" for k in params.keys()))
        cur.execute(sql, params)
    
    if "fileupload" in request.files and request.files["fileupload"].filename:
        f = request.files["fileupload"]
        f.save(final_path)

@bp.route("/edit/<int:task_id>", methods=["GET", "POST"])
@admin_required
def task_edit(task_id):
    if request.method == "POST":
        insert_or_update_task(task_id)
        return redirect("/taskadmin")

    cur = get_db().cursor()
    cur.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    row = dict(cur.fetchone())
    row["from_date"] = time.strftime(TIMEFORMAT, time.localtime(row["from_date"]))
    row["due_date"] = time.strftime(TIMEFORMAT, time.localtime(row["due_date"]))
    return render_template("task-admin/detail.html", edit=True, data=row)

@bp.route("/key/<int:task_id>")
@admin_required
def task_key(task_id):
    cur = get_db().cursor()
    cur.execute("SELECT * from tasks WHERE task_id = ?", (task_id,))
    res = cur.fetchone()
    if res is not None:
        k = get_flag_key(task_id)
        b = io.BytesIO(k)
        return send_file(b, as_attachment=True, download_name=f"{res['task_short']}.key")
    abort(404)

@bp.route("/dl/<path:path>", methods=["GET", "POST"])
@admin_required
def task_dl(path):
    print(path)
    return send_from_directory("tasks", path, as_attachment=True)

@bp.route("/create", methods=["GET", "POST"])
@admin_required
def task_create():
    cur = get_db().cursor()
    cur.execute("SELECT MAX(order_num)+1 as order_num, COUNT(order_num) as short FROM tasks")
    suggestions = cur.fetchone()

    if request.method == "POST":
        insert_or_update_task()
        return redirect(url_for(".task_overview"))

    if metapath := request.args.get("repo"):
        metapath = os.path.normpath(metapath) # Get rid of ..
        git_path = pathlib.Path(current_app.config["TASKS_GIT_PATH"])
        with open(git_path / metapath / "META.json") as fd:
            try:
                task_data = json.load(fd)
            except json.JSONDecodeError:
                flash("Invalid META.json!")
                return redirect("task-admin/")
        short_title = task_data["short_title"]
        edit = {
            "task_short": short_title,
            "task_long": task_data["title"],
            "max_points": task_data["points"],
            "needed": task_data["exploit_required"],
            "url": task_data["url"],
            "autograded": task_data["autograded"],
            "order_num": suggestions["order_num"] or 0,
        }
        try:
            edit["markdown"] = open(current_app.config["TASKS_GIT_PATH"] + "/" + metapath + "/DESCRIPTION.md").read()
        except FileNotFoundError:
            edit["markdown"] = ""

        # Build distributable if needed
        if task_data["downloads"]:
            output_filename = f'tasks/tmp/{short_title}.zip'
            with zipfile.ZipFile(output_filename, 'w', compression=zipfile.ZIP_DEFLATED) as out:
                for subpath in task_data['downloads']:
                    subpath = subpath.lstrip('/')
                    actual_path = git_path / metapath / subpath
                    archive_path = pathlib.Path(short_title) / subpath
                    if not actual_path.exists():
                        flash(f'Error: Downloadable file {actual_path} does not exist')
                    out.write(actual_path, arcname=archive_path)
            edit["download_name"] = os.path.basename(output_filename)
            edit["download_link"] = "/taskadmin/dl/tmp/" + edit["download_name"]
        return render_template("task-admin/detail.html", edit=False, data=edit)
    return render_template("task-admin/detail.html", edit=False, data={"order_num": suggestions["order_num"] or 0})

@bp.route("/pull-repo")
@admin_required
def pull_repo():
    out = subprocess.check_output(["git", "pull"], cwd=current_app.config["TASKS_GIT_PATH"], env={"LANG": ""})
    flash(out.decode())
    return redirect(url_for('.tasks_from_repo'))

@bp.route("/rendermd", methods=["POST"])
@tutor_required
def render_markdown_service():
    resp = render_markdown(request.get_data().decode())
    return resp

@bp.route("/create-repo")
@admin_required
def tasks_from_repo():
    dirs = []
    basepath = current_app.config["TASKS_GIT_PATH"]
    for d in glob.glob(basepath + "/*/META.json"):
        dirpath = os.path.dirname(d)
        with open(d) as fd:
            try:
                task_data = json.load(fd)
            except json.JSONDecodeError:
                pass
        task_data["path"] = os.path.dirname(os.path.relpath(d, basepath))
        dirs.append(task_data)
    return render_template("task-admin/repo.html", tasks=sorted(dirs, key=lambda x: x['path']))

@bp.route("/dl")
@tutor_required
def download_submissions():
    cur = get_db().cursor()
    cur.execute("SELECT * FROM task_submissions s LEFT JOIN tasks t ON t.task_id = s.task_id")
    with tempfile.NamedTemporaryFile() as tmpzip:
        with zipfile.ZipFile(tmpzip.name, "w") as z:
            for f in cur.fetchall():
                try:
                    z.write(f["filepath"], f"{f['task_short']}/team-{f['team_id']}/{os.path.basename(f['filepath'])}")
                except FileNotFoundError:
                    print(f["filepath"], "not found")
        return send_file(tmpzip.name, as_attachment=True, download_name="submissions.zip")
        #return send_from_directory(directory="submissions", filename=filename)

@bp.route("/delete", methods=["POST"])
@admin_required
def task_delete():
    cur = get_db().cursor()
    cur.execute("SELECT COUNT(*) FROM flag_submissions WHERE task_id=?", (request.form["tasknum"],))
    if cur.fetchone()[0] > 0:
        flash("This task already has submitted flags and can therefore not get deleted!")
        return redirect("/taskadmin")
    cur.execute("DELETE FROM tasks WHERE task_id=?", (request.form["tasknum"],))

    return redirect("/taskadmin")

@bp.route("/feedback/<int:task_id>")
@tutor_required
def task_feedback(task_id):
    cur = get_db().cursor()
    cur.execute("""
            SELECT 
                f.*, 
                f.rating,
                u.vorname || ' ' || u.nachname as author,
                CASE WHEN t.teamname IS NULL THEN 'Team ' || t.team_id ELSE t.teamname END as team
            FROM task_feedback f 
            LEFT JOIN users u ON u.id = f.user_id 
            LEFT JOIN team_members m ON m.member_id = u.id
            LEFT JOIN teams t ON t.team_id = m.team_id
            WHERE task_id=? and t.deleted IS NULL and f.text != ''""", (task_id,))
    return render_template("task-admin/feedback.html", ratings=cur.fetchall())


