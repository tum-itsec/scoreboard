import csv
import tempfile
import base64
import json
from flask import Blueprint, request, render_template, send_file
from .util import *
from Crypto.Cipher import AES

class GradeCSVException(Exception):
    pass

bp = Blueprint("grade-upload", __name__, url_prefix="/grade-upload")

@bp.route("", strict_slashes=False, methods=["POST", "GET"])
@tutor_required
def grade_upload():
    if request.method == "POST":
        if "gradefile" in request.files:
            f = request.files["gradefile"]
            with tempfile.NamedTemporaryFile() as tmp:
                f.save(tmp.name)
                try:
                    # Check teams and tasks exist
                    cur = get_db().cursor()
                    cur.execute("SELECT team_id FROM teams")
                    available_teams = [x[0] for x in cur.fetchall()]
                    
                    cur = get_db().cursor()
                    cur.execute("SELECT task_short FROM tasks")
                    available_tasks = [x[0] for x in cur.fetchall()]

                    # Interpret Uploaded Grades
                    l = read_grade_csv(tmp.name, available_teams, available_tasks)

                    # Get already present grades from DB
                    cur.execute("SELECT * FROM task_grading g LEFT JOIN tasks t ON t.task_id = g.task_id WHERE deleted_time IS NULL")
                    grades_in_db = cur.fetchall()

                    delta = compare_grades(grades_in_db, l)
                    changed_records = sum(1 for x in delta if x[0] == "m")
                    new_records = sum(1 for x in delta if x[0] == "n")
                    ignored_records = len(l) - new_records - changed_records
                    changeset = base64.b64encode(json.dumps(delta).encode()).decode()

                    return render_template("grade-upload-step2.html", changed_records=changed_records, new_records=new_records, changeset=changeset, ignored_records=ignored_records, new_grading=delta)
                except GradeCSVException as e:
                    flash(e)
                    return render_template("grade-upload-step1.html")
        elif "changeset" in request.form:
            changeset = json.loads(base64.b64decode(request.form["changeset"]))
            cur = get_db().cursor()
            for elm in changeset:
                task_short, team_id, points, comment, internal_comment, corrector = elm[1]
                task_id = cur.execute("SELECT task_id FROM tasks WHERE task_short=?", [task_short]).fetchone()[0]
                if elm[0] == "m":
                    cur.execute("UPDATE task_grading SET deleted_time=strftime('%s','now') WHERE task_id = ? and team_id = ? and deleted_time IS NULL", (task_id, team_id))
                elif elm[0] != "n":
                    raise Exception("Bad action in changeset!")
                cur.execute("INSERT INTO task_grading (task_id, team_id, comment, internal_comment, points, corrector, created_time) VALUES (?,?,?,?,?,?,strftime('%s','now'))", (task_id, team_id, points, comment, internal_comment, corrector))
            flash("Benotung importiert!", category="success")
            return render_template("grade-upload-step1.html")
            #return changeset
    else:
        return render_template("grade-upload-step1.html")

@bp.route("/dl")
@tutor_required
def grade_dl():
    cur = get_db().cursor()
    cur.execute("SELECT * FROM task_grading g  LEFT JOIN tasks t ON t.task_id=g.task_id WHERE deleted_time IS NULL ORDER BY order_num, task_id, team_id")

    with tempfile.NamedTemporaryFile(mode="w+") as tmp:
        w = csv.writer(tmp, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        w.writerow(['task', 'team', 'points', 'comment', 'internal_comment', 'corrector'])
        for r in cur.fetchall():
            w.writerow([r['task_short'], r['team_id'], r['points'], r['comment'], r['internal_comment'], r['corrector']])
            print(r)
        tmp.flush()
        return send_file(tmp.name, as_attachment=True, download_name="grading.csv")


def read_grade_csv(csvfile, available_teams, available_tasks):
    with open(csvfile, "r") as f:
        reader = csv.DictReader(f,delimiter=";")
        l = []
        for row in reader:
            try:
                team = int(row['team'])
                if team not in available_teams:
                    raise GradeCSVException(f"Fehler in Zeile {reader.line_num} - Team {team} exisistiert nicht in der DB")
                task = row['task']
                if task not in available_tasks:
                    raise GradeCSVException(f"Fehler in Zeile {reader.line_num} - Task {task} exisistiert nicht in der DB")
                points = float(row['points'].replace(",",".").strip())
                comment = row["comment"]
                internal_comment = row["internal_comment"]
                corrector = row["corrector"]
                l.append((task, team, comment, internal_comment, points, corrector))
            except ValueError as e:
                if len(row['team'].strip()) == 0 and len(row['task'].strip()) == 0:
                    # ignore if row is empty
                    pass
                else:
                    # otherwise, throw error
                    raise GradeCSVException(f"Parse error in line {reader.line_num}: {e}") from e
            except KeyError as e:
                raise GradeCSVException(f"KeyError beim parsen in Zeile {reader.line_num}. Spalten gelöscht oder keine ; als Delimiter verwendet?!")
        return l

def compare_single_grade(db_grades, i):
    for x in db_grades:
        if i[0] == x["task_short"] and i[1] == x["team_id"]:
            if i[2] == x["comment"] and i[3] == x["internal_comment"] and i[4] == x["points"] and i[5] == x["corrector"]:
                return ("u", None, None)
            else:
                return ("m", i, (x["task_short"], x["team_id"], x["comment"], x["internal_comment"], x["points"], x["corrector"]))
    return ("n", i, None)

def compare_grades(db_grades, csv_grades):
    r = []
    for i in csv_grades:
        res = compare_single_grade(db_grades, i)
        if res == ("u", None, None):
            continue
        else:
            r.append(res)
    return r
