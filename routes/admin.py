from flask import Blueprint, render_template
from utils import role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard")
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html")
