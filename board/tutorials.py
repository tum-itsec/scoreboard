from flask import Blueprint, render_template, request, current_app
from .util import *
from Crypto.Cipher import DES
import base64, datetime
import io

try:
	import qrcode
except ModuleNotFoundError:
	qrcode = None

bp = Blueprint("tutorials", __name__, url_prefix="/tutorials")

@bp.route("/")
@tutor_required
def tutorials():
    
    cur = get_db().cursor()
    cur.execute(f"""
    SELECT
    ta.tracking_id,
    ta.comments,
    ta.tutor_id,
    ta.tutorial_date,
    t.description,
    t.tutorium_id,
    u.vorname,
    avg(attendance) as average_attendance,
    count(*) as nr_of_trackings
    FROM tutorium t
    LEFT JOIN tutorium_attendance ta ON ta.tutorium_id = t.tutorium_id
    LEFT JOIN users u ON u.id = ta.tutor_id
    GROUP BY t.tutorium_id
    """)
    
    tutorial_infos = [dict(i) for i in cur.fetchall()]

    return render_template("tutorials.html", tutorial_infos=tutorial_infos)


@bp.route("/list")
@tutor_required
def tracking_list():

    filter = request.args.get("filter", type=str)

    if filter == "tutor":
        filter_val = session["user-id"]
        filter_string = "WHERE ta.tutor_id = ?"
        tutorview = True
    elif filter == "tutorium":
        filter_val = request.args.get("tutorium_id", type=int, default=1)
        filter_string = "WHERE ta.tutorium_id = ?"
        tutorview = False
    else:
        flash("Invalid filter")
        return redirect("/tutorials")
    
    cur = get_db().cursor()
    dbstring = f"""
    SELECT
    ta.tracking_id,
	ta.tutorium_id,
    ta.comments,
    ta.attendance,
    ta.tutor_id,
    ta.tutorial_date,
    t.description,
    u.vorname
    FROM tutorium_attendance ta
    LEFT JOIN tutorium t ON ta.tutorium_id = t.tutorium_id
    LEFT JOIN users u ON u.id = ta.tutor_id 
    """
    dbstring += filter_string
    cur.execute(dbstring, (filter_val,))
    
    tracking_infos = []
    cry = DES.new(current_app.config["ATTENDANCE_KEY"], mode=DES.MODE_ECB)

    for i in cur.fetchall():
        infos = dict(i)
        infos["attendance_code"] = cry.encrypt(struct.pack("<II", infos["tracking_id"], int(time.time())))
        infos["attendance_code"] = base64.b32encode(infos["attendance_code"]).rstrip(b"=").decode()

        tracking_infos.append(infos)

    code_base_link = "/tutorials/attendqr/" if qrcode else "/tutorials/attend/"
    return render_template("tutorials_tracking_list.html", tracking_infos=tracking_infos, tutorview=tutorview, tutor_id=session["user-id"], code_base_link=code_base_link)

def decrypt_attendance_code(attendance_code: str):
    attendance_code = attendance_code.strip()
    try:
        attendance_code_dec = base64.b32decode(attendance_code.replace("0","O") + "="*(len(attendance_code)%5))
    except:
        print(f"Attendance code: Base64 decoding failed: {attendance_code}")
        flash("Invalid Attendance-Code!")
        return None

    cry = DES.new(key=current_app.config["ATTENDANCE_KEY"], mode=DES.MODE_ECB)
    try:
        tracking_id, jtime = struct.unpack("<II", cry.decrypt(attendance_code_dec))
    except (struct.error, ValueError):
        print(f"Attendance code: Unpacking failed: {attendance_code_dec}")
        flash("Invalid Attendance-Code!")
        return None

    cur = get_db().cursor()
    cur.execute("""SELECT * FROM tutorium_attendance ta
                LEFT JOIN tutorium USING(tutorium_id)
                WHERE tracking_id=?""", (tracking_id,))

    if not (row := cur.fetchone()):
        flash("Invalid Attendance-Code!")
        return None

    return dict(row)

@bp.route("/attend", methods = ["GET", "POST"])
@login_required
def attend_list():
    cur = get_db().cursor()
    if request.method == "POST":
        tracking = decrypt_attendance_code(request.form.get("attendance_code", "").strip())
        if tracking is None:
            return redirect("/tutorials/attend")
        
        code_valid_until = datetime.datetime.strptime(tracking["tutorial_date"] + " 23:59", "%Y-%m-%d %H:%M").timestamp()
        if code_valid_until < time.time():
            flash("Attendance-Code expired!")
            return redirect(f"/tutorials/attend")

        try:
            cur.execute("""
            INSERT INTO tutorium_attendance_students (tracking_id, user_id) VALUES (?, ?)
                        """ , (tracking["tracking_id"], session["user-id"]))
        except:
            flash("Attendance-Code already used!")
            return redirect(f"/tutorials/attend")
        
        flash("Tracking successfully added", category="success")
        return redirect(f"/tutorials/attend")

    cur.execute("""
    SELECT * FROM tutorium_attendance_students
    JOIN tutorium_attendance USING(tracking_id)
    JOIN tutorium USING(tutorium_id)
    WHERE user_id = ?
    """, (session["user-id"],))

    trackings = [dict(i) for i in cur.fetchall()]
    return render_template("tutorials_tracking_attend.html", trackings=trackings)

@bp.route("/attend/<attendance_code>", methods = ["GET"])
@login_required
def attend(attendance_code: str):
    tracking = decrypt_attendance_code(attendance_code)
    if tracking is None:
        return redirect("/tutorials/attend")
    
    cur = get_db().cursor()
    if request.method == "GET":
        cur.execute("""
        SELECT * FROM tutorium_attendance_students tas
        LEFT JOIN users u ON u.id = tas.user_id
        WHERE tracking_id = ? and user_id = ?
        """, (tracking["tracking_id"],session["user-id"]))

        if cur.fetchone() is not None:
            flash("Attendance-Code already used!")
            return redirect(f"/tutorials/attend")

        return render_template("tutorials_tracking_attend.html", tracking=tracking, attendance_code=attendance_code)

@bp.route("/attendqr/<attendance_code>", methods = ["GET"])
@tutor_required
def attendqr(attendance_code: str):
	tut = decrypt_attendance_code(attendance_code)
	return render_template("tutorials_tracking_attendqr.html", attendance_code=attendance_code, tut=tut)

if qrcode:
	@bp.route("/attendqr/<attendance_code>/qr.png", methods = ["GET"])
	@tutor_required
	def attendqr_png(attendance_code: str):
		# TODO maybe don't rely on correct proxy setup. any more sane way to do this?
		qr = qrcode.make(f"https://{request.headers.get('X-Forwarded-Host')}/tutorials/attend/{attendance_code}")
		b = io.BytesIO()
		qr.save(b)
		return b.getvalue(), 200, {'Content-Type': 'image/png'}
else:
	@bp.route("/attendqr/<attendance_code>/qr.png", methods = ["GET"])
	@tutor_required
	def attendqr_png(attendance_code: str):
		return "qrcode module not installed"

@bp.route("/add", methods = ["POST", "GET"])
@tutor_required
def add_tracking():
    if request.method == "POST":
        cur = get_db().cursor()
        tutorium_id = request.form.get("tutorium_id", "").strip()
        date = request.form.get("date", "")
        if not date:
            flash("Please enter the date!")
            return redirect("/tutorials/add")
        comments = request.form.get("comments", "").strip()
        attendance = request.form.get("attendance", 0)

        cur.execute("""
        INSERT INTO tutorium_attendance (tutorium_id, attendance, comments, tutor_id, tutorial_date) VALUES (?, ?, ?, ?, ?)
        """, (tutorium_id, attendance, comments, session["user-id"], date))
        flash("Tracking successfully added", category="success")
        return redirect("/tutorials/list?filter=tutor")
    cur = get_db().cursor()
    cur.execute("SELECT * FROM tutorium ORDER BY tutor_id=? DESC NULLS LAST, tutorium_id ASC", (session['user-id'],))
    tutorials = [dict(i) for i in cur.fetchall()]
    return render_template("tutorials_tracking_add.html", tutorials=tutorials, edit=False)


def update_tracking(tracking_id):
    params = {k: request.form[k] for k in ["tutorium_id", "tutorial_date", "comments", "attendance"]}
    cur = get_db().cursor()
    cur.execute("SELECT tutor_id FROM tutorium_attendance WHERE tracking_id=?", (tracking_id,))
    tutor_id = cur.fetchone()[0]
    if not tutor_id == session["user-id"]:
        return False

    date = request.form.get("tutorial_date", "")
    if not date:
        flash("Please enter the date!")
        return redirect("/tutorials/edit/" + str(tracking_id))
    params["tutorial_date"] = date

    sql = "UPDATE tutorium_attendance SET {} WHERE tracking_id=:tracking_id".format(",".join(f"{k}=:{k}" for k in params.keys()), tracking_id)
    params["tracking_id"] = tracking_id
    cur.execute(sql, params)
    return True

@bp.route("/edit/<int:tracking_id>", methods=["GET", "POST"])
@tutor_required
def tracking_edit(tracking_id):
    if request.method == "POST":
        if not update_tracking(tracking_id):
            flash("Only the tutor that added the tracking is allowed to update it!")
        else:
            flash("Tracking successfully updated", category="success")
        return redirect("/tutorials")

    cur = get_db().cursor()
    cur.execute("""SELECT * FROM tutorium_attendance ta
                    LEFT JOIN tutorium USING(tutorium_id)
                    WHERE tracking_id=?""", (tracking_id,))
    curvals = dict(cur.fetchone())
    curvals["prevDate"] = curvals["tutorial_date"]
    cur.execute("SELECT * FROM tutorium")
    tutorials = [dict(i) for i in cur.fetchall()]

    cur.execute("""
    SELECT * FROM tutorium_attendance_students
    JOIN tutorium_attendance USING(tracking_id)
    JOIN tutorium USING(tutorium_id)
    JOIN users u ON u.id = user_id
    WHERE tracking_id = ?
    """, (tracking_id,))

    students = [dict(i) for i in cur.fetchall()]

    return render_template("tutorials_tracking_add.html", tutorials=tutorials, edit=True, data=curvals, students=students)


def delete_tracking(tracking_id):
    cur = get_db().cursor() 
    cur.execute("SELECT tutor_id FROM tutorium_attendance WHERE tracking_id=?", (tracking_id,))
    tutor_id = cur.fetchone()[0]
    if not tutor_id == session["user-id"]:
        return False
    cur.execute("DELETE FROM tutorium_attendance WHERE tracking_id=?", (tracking_id,))
    cur.execute("DELETE FROM tutorium_attendance_students WHERE tracking_id=?", (tracking_id,))
    return True

@bp.route("/delete/<int:tracking_id>", methods=["POST"])
@tutor_required
def tracking_delete(tracking_id):
    if not delete_tracking(tracking_id):
        flash("Only the tutor that created the tracking is allowed to delete it!")
    else:
        flash("Tracking successfully deleted", category="success")
    return redirect("/tutorials")
