from flask import Blueprint, render_template
from utils import role_required

student_bp = Blueprint("student", __name__, url_prefix="/student")


@student_bp.route("/dashboard")
@role_required("student")
def dashboard():
    return render_template("student/dashboard.html")
