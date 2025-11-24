from flask import Blueprint, render_template, send_from_directory, abort, request, jsonify, current_app
import re
import os
from collections import defaultdict

from .util import *

# We should think about more special characters in the comment part of the key. The function sshkey_try_load_public of OpenSSH looks
# like everything is fine if there is at least one whitespace/tab character between the comment and the newline / end-of-file
SSH_KEY_REGEX = re.compile("ssh-(?:ed25519|rsa) (?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?( [a-zA-Z0-9' .%\$\+&:=!\-@_]*)?")

bp = Blueprint("sshkeys", __name__, url_prefix="/sshkeys")

def get_user_identifier(user_id, team_id, role):
    if role in (1,2):
        user_identifier = f"tut-{user_id}"
    elif team_id is not None:
        user_identifier = f"team-{team_id}"
    else:
        user_identifier = f"stud-{user_id}"
    return user_identifier

@bp.route("", methods=["GET"])
@login_required
def sshkeys():
    cur = get_db().cursor()
    cur.execute("SELECT * FROM sshkeys WHERE user_id=?", (session["user-id"],))
    sshkeys = cur.fetchall()

    team_id = get_team_from_db()
    cur.execute("SELECT role FROM users WHERE id=?", (session["user-id"],))
    role, = cur.fetchone()
    user_identifier = get_user_identifier(session['user-id'], team_id, role)
    cmd = current_app.config["SSHKEY_CMD"].format(user=user_identifier)
    return render_template("sshkeys.html", sshkeys=sshkeys, cmd=cmd, key_available=True if sshkeys else False)

@bp.route("/add", methods = ["POST", "GET"])
@login_required
def add():
    if request.method == "POST":
        cur = get_db().cursor()
        key = request.form.get("sshkeys", "").strip()
        m = SSH_KEY_REGEX.fullmatch(key)
        if m:
            cur.execute("INSERT INTO sshkeys (user_id, ssh_key, added_date) VALUES (?, ?, strftime('%s','now'))", (session["user-id"], key))
            flash("Your SSH public key has been added!", category="success")
        else:
            flash("This doesn't seem to be a valid SSH public key. Please use an Ed25519 or RSA SSH public key!")

        return redirect("/sshkeys")
    return render_template("sshkeys_add.html")

@bp.route("/<int:key_id>/delete", methods = ["POST"])
@login_required
def delete(key_id):
    cur = get_db().cursor()
    cur.execute("DELETE FROM sshkeys WHERE user_id=? and key_id=?", (session["user-id"], key_id))
    return redirect("/sshkeys")

@bp.route("/getkeys")
def getkeys():
    if not (request.args.get("APIKEY", "") == current_app.config["SSHKEY_APIKEY"] or is_admin()):
        abort(403)
    cur = get_db().cursor()
    cur.execute("SELECT * FROM sshkeys s LEFT JOIN team_members m ON s.user_id = m.member_id LEFT JOIN users u ON s.user_id = u.id")
    ssh_data = defaultdict(list)
    for r in cur.fetchall():
        if r['role'] in (1,2):
            user_identifier = f"tut-{r['user_id']}"
        elif r["team_id"] is not None:
            user_identifier = f"team-{r['team_id']}"
        else:
            user_identifier = f"stud-{r['user_id']}"
        ssh_data[user_identifier].append(r["ssh_key"])
    return jsonify(ssh_data)
