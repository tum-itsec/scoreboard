from flask import Blueprint, render_template, abort, request, jsonify, current_app

from .util import *

bp = Blueprint("users", __name__, url_prefix="/users")

@bp.route("", methods=["GET"])
@admin_required
def users():
    cur = get_db().cursor()
    cur.execute("""
        SELECT
            u.*,
            tm.team as team,
            tm.team_id as team_id,
            (SELECT COUNT(*) FROM sshkeys k WHERE k.user_id = u.id) as ssh_key
        FROM users u
        LEFT JOIN
            (SELECT
                m.member_id,
                CASE WHEN t.teamname IS NULL THEN 'Team ' || t.team_id ELSE t.teamname END as team,
                t.team_id as team_id
            FROM team_members m
            LEFT JOIN teams t ON t.team_id = m.team_id
            WHERE t.deleted IS NULL) tm
            ON tm.member_id = u.id
            ORDER BY nachname, vorname
        """)
    users = cur.fetchall()
    return render_template("user_admin.html", users=users)
