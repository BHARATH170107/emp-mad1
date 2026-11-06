from flask import Blueprint, render_template
from utils import role_required

examiner_bp = Blueprint("examiner", __name__, url_prefix="/examiner")


@examiner_bp.route("/dashboard")
@role_required("examiner")
def dashboard():
    return render_template("examiner/dashboard.html")
