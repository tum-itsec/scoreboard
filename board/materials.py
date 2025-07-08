from flask import Blueprint, render_template, send_from_directory, abort, request
import os

from .util import *

bp = Blueprint("materialien", __name__, url_prefix="/materialien")

@bp.route("", methods=["POST", "GET"])
@login_required
def materialien():
    if request.method == "POST":
        if "fileupload" not in request.files:
            flash("Keine Datei hochgeladen!")
            return redirect("/materialien")
        if not is_admin():
            return redirect("/materialien")
        f = request.files["fileupload"]
        final_path = os.path.join("materialien", f.filename)
        f.save(final_path)

    files = [x for x in os.listdir("materialien/") if not x.startswith(".")]
    files = sorted(files)
    return render_template("materialien.html", files=files)

@bp.route("/<filename>")
@login_required
def materialien_dl(filename):
    if not filename.startswith("."):
        return send_from_directory("materialien", filename, as_attachment=True)
    else:
        abort(404)
