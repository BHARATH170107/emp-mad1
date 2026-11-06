from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, ExaminerProfile

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/dashboard")
@login_required
def dashboard_redirect():
    """Send each role to its own dashboard."""
    return redirect(url_for(f"{current_user.role}.dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard_redirect"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html")

        if not user.active:
            flash("This account is deactivated.", "danger")
            return render_template("auth/login.html")

        if user.role == "examiner":
            status = user.examiner_profile.status if user.examiner_profile else None
            if status == "Pending":
                flash("Your account is waiting for Admin approval.", "warning")
                return render_template("auth/login.html")
            if status != "Approved":
                flash("Your examiner account is not active.", "danger")
                return render_template("auth/login.html")

        login_user(user)
        return redirect(url_for("auth.dashboard_redirect"))

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("auth.dashboard_redirect"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        role = request.form.get("role", "student")
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        department = request.form.get("department", "").strip()

        # ---- backend validation ----
        error = None
        if role not in ("student", "examiner"):
            error = "Invalid role."
        elif not (full_name and username and email and password):
            error = "Please fill all required fields."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif User.query.filter_by(username=username).first():
            error = "Username already taken."
        elif User.query.filter_by(email=email).first():
            error = "Email already registered."
        elif role == "examiner" and not department:
            error = "Department is required for examiners."

        if error:
            flash(error, "danger")
            return render_template("auth/register.html", form=request.form)

        user = User(username=username, email=email, full_name=full_name,
                    phone=phone, role=role,
                    password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.flush()  # gives user.id

        if role == "examiner":
            db.session.add(ExaminerProfile(user_id=user.id, department=department,
                                           contact_details=phone, status="Pending"))
        db.session.commit()

        if role == "examiner":
            flash("Registered! You can log in after the Admin approves you.", "success")
        else:
            flash("Registered! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form={})


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
