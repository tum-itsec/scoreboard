from flask import Blueprint, render_template, request
from .util import *

bp = Blueprint("eastereggs", __name__, url_prefix="/eastereggs")

@bp.route("/add", methods=["POST"])
@admin_required
def easteregg_add():
    flag = request.form.get("flag")
    link = request.form.get("link")

    cur = get_db().cursor()
    cur.execute("insert into easteregg_flags (flag, link, counter, creator) values (?, ?, 0, ?)", (flag, link, session['user-id']))
    return redirect("./")

@bp.route("/delete", methods=["POST"])
@admin_required
def easteregg_delete():
    egg_id = int(request.form.get("id"))

    cur = get_db().cursor()
    cur.execute("DELETE FROM easteregg_flags WHERE easteregg_id = ?", (egg_id,))
    return redirect("./")

@bp.route("/")
@tutor_required
def eastereggs():
    cur = get_db().cursor()
    cur.execute("SELECT *, u.vorname || ' ' || u.nachname as creator_name FROM easteregg_flags LEFT JOIN users u ON creator=u.id")
    eggs = cur.fetchall()
    return render_template("eastereggs.html", eggs=eggs)
