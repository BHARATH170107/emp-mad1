from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import or_
from werkzeug.security import generate_password_hash
from models import (db, User, ExaminerProfile, Course, Examination,
                    ExaminationRubric, ExaminationSlot, Booking, RubricScore)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

EXAM_TYPES = ["Viva", "Practical", "Project Demo", "Assessment"]
EXAM_STATUSES = ["Draft", "Slot Creation", "Booking Open", "Closed", "Completed"]


@admin_bp.before_request
def admin_only():
    """Runs before EVERY route in this blueprint: only the Admin gets in."""
    if not current_user.is_authenticated:
        flash("Please log in first.", "warning")
        return redirect(url_for("auth.login"))
    if current_user.role != "admin":
        flash("You are not allowed to open that page.", "danger")
        return redirect(url_for("auth.dashboard_redirect"))


# ---------- small helpers ----------
def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_date(value):
    """'' -> None, '2026-11-20' -> date. Raises ValueError if badly formed."""
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def iso(d):
    return d.isoformat() if d else ""


# ---------- dashboard ----------
@admin_bp.route("/dashboard")
def dashboard():
    cards = [
        ("Courses", Course.query.count(), "admin.courses"),
        ("Examinations", Examination.query.count(), "admin.exams"),
        ("Examiners", ExaminerProfile.query.count(), "admin.examiners"),
        ("Students", User.query.filter_by(role="student").count(), "admin.students"),
        ("Exam Slots", ExaminationSlot.query.count(), "admin.slots"),
        ("Bookings", Booking.query.count(), "admin.bookings"),
    ]
    pending = ExaminerProfile.query.filter_by(status="Pending").count()
    return render_template("admin/dashboard.html", cards=cards, pending=pending)


# ---------- courses ----------
@admin_bp.route("/courses")
def courses():
    return render_template("admin/courses.html",
                           courses=Course.query.order_by(Course.code).all())


def _course_form(course):
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        status = request.form.get("status", "Active")

        error = None
        if not code or not name:
            error = "Course code and name are required."
        elif status not in ("Active", "Inactive"):
            error = "Invalid status."
        else:
            clash = Course.query.filter_by(code=code).first()
            if clash and (course is None or clash.id != course.id):
                error = "A course with this code already exists."
        if error:
            flash(error, "danger")
            return render_template("admin/course_form.html", f=request.form, course=course)

        if course is None:
            course = Course()
            db.session.add(course)
        course.code, course.name = code, name
        course.description, course.status = description, status
        db.session.commit()
        flash("Course saved.", "success")
        return redirect(url_for("admin.courses"))

    f = {} if course is None else {"code": course.code, "name": course.name,
                                   "description": course.description or "",
                                   "status": course.status}
    return render_template("admin/course_form.html", f=f, course=course)


@admin_bp.route("/courses/new", methods=["GET", "POST"])
def course_new():
    return _course_form(None)


@admin_bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def course_edit(course_id):
    return _course_form(db.get_or_404(Course, course_id))


@admin_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
def course_delete(course_id):
    course = db.get_or_404(Course, course_id)
    if course.examinations:
        flash("Cannot delete: this course has examinations. Set it to Inactive instead.", "danger")
    else:
        db.session.delete(course)
        db.session.commit()
        flash("Course deleted.", "success")
    return redirect(url_for("admin.courses"))


# ---------- examinations ----------
@admin_bp.route("/exams")
def exams():
    return render_template("admin/exams.html",
                           exams=Examination.query.order_by(Examination.id.desc()).all())


def _exam_form(exam):
    courses = Course.query.filter_by(status="Active").order_by(Course.code).all()
    examiners = ExaminerProfile.query.filter_by(status="Approved").all()

    def render(f):
        return render_template("admin/exam_form.html", f=f, exam=exam, courses=courses,
                               examiners=examiners, exam_types=EXAM_TYPES)

    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        exam_type = form.get("exam_type", "")
        course_id = to_int(form.get("course_id"))
        examiner_id = to_int(form.get("examiner_id"))
        duration = to_int(form.get("duration"))
        max_marks = to_int(form.get("max_marks"))

        error = None
        try:
            sc_start = to_date(form.get("slot_creation_start"))
            sc_end = to_date(form.get("slot_creation_end"))
            bk_start = to_date(form.get("booking_start"))
            bk_end = to_date(form.get("booking_end"))
        except ValueError:
            sc_start = sc_end = bk_start = bk_end = None
            error = "One of the dates is not valid."

        if error:
            pass
        elif not name:
            error = "Examination name is required."
        elif exam_type not in EXAM_TYPES:
            error = "Choose a valid examination type."
        elif not course_id or not db.session.get(Course, course_id):
            error = "Choose a course."
        elif not duration or duration <= 0:
            error = "Duration must be a positive number of minutes."
        elif not max_marks or max_marks <= 0:
            error = "Maximum marks must be a positive number."
        elif sc_start and sc_end and sc_start > sc_end:
            error = "Slot creation end date cannot be before its start date."
        elif bk_start and bk_end and bk_start > bk_end:
            error = "Booking end date cannot be before its start date."
        elif sc_end and bk_start and bk_start < sc_start:
            error = "Booking cannot start before slot creation starts."
        elif examiner_id and not ExaminerProfile.query.filter_by(id=examiner_id, status="Approved").first():
            error = "Choose an approved examiner."
        elif exam and exam.rubrics and max_marks < sum(r.max_marks for r in exam.rubrics):
            error = "Maximum marks cannot be less than the total of the rubric marks."

        if error:
            flash(error, "danger")
            return render(form)

        if exam is None:
            exam = Examination(status="Draft")
            db.session.add(exam)
        exam.name, exam.exam_type, exam.course_id = name, exam_type, course_id
        exam.examiner_id = examiner_id
        exam.duration, exam.max_marks = duration, max_marks
        exam.slot_creation_start, exam.slot_creation_end = sc_start, sc_end
        exam.booking_start, exam.booking_end = bk_start, bk_end
        db.session.commit()
        flash("Examination saved.", "success")
        return redirect(url_for("admin.exam_detail", exam_id=exam.id))

    f = {}
    if exam:
        f = {"name": exam.name, "exam_type": exam.exam_type, "course_id": exam.course_id,
             "examiner_id": exam.examiner_id or "", "duration": exam.duration,
             "max_marks": exam.max_marks,
             "slot_creation_start": iso(exam.slot_creation_start),
             "slot_creation_end": iso(exam.slot_creation_end),
             "booking_start": iso(exam.booking_start),
             "booking_end": iso(exam.booking_end)}
    return render(f)


@admin_bp.route("/exams/new", methods=["GET", "POST"])
def exam_new():
    return _exam_form(None)


@admin_bp.route("/exams/<int:exam_id>/edit", methods=["GET", "POST"])
def exam_edit(exam_id):
    return _exam_form(db.get_or_404(Examination, exam_id))


@admin_bp.route("/exams/<int:exam_id>")
def exam_detail(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    total = sum(r.max_marks for r in exam.rubrics)
    return render_template("admin/exam_detail.html", exam=exam,
                           statuses=EXAM_STATUSES, rubric_total=total)


@admin_bp.route("/exams/<int:exam_id>/status", methods=["POST"])
def exam_status(exam_id):
    """Opening/closing slot creation and booking is just changing the status."""
    exam = db.get_or_404(Examination, exam_id)
    status = request.form.get("status")
    if status not in EXAM_STATUSES:
        flash("Invalid status.", "danger")
    else:
        exam.status = status
        db.session.commit()
        flash(f"Status changed to {status}.", "success")
    return redirect(url_for("admin.exam_detail", exam_id=exam.id))


@admin_bp.route("/exams/<int:exam_id>/publish", methods=["POST"])
def exam_publish(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    exam.results_published = not exam.results_published
    db.session.commit()
    flash("Results published." if exam.results_published else "Results hidden.", "success")
    return redirect(url_for("admin.exam_detail", exam_id=exam.id))


@admin_bp.route("/exams/<int:exam_id>/delete", methods=["POST"])
def exam_delete(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    if exam.slots or exam.bookings:
        flash("Cannot delete: this examination already has slots or bookings.", "danger")
        return redirect(url_for("admin.exams"))
    db.session.delete(exam)  # its rubrics are deleted with it
    db.session.commit()
    flash("Examination deleted.", "success")
    return redirect(url_for("admin.exams"))


# ---------- rubrics ----------
def _rubric_form(exam, rubric):
    def render(f):
        return render_template("admin/rubric_form.html", f=f, exam=exam, rubric=rubric)

    if request.method == "POST":
        criterion = request.form.get("criterion_name", "").strip()
        max_marks = to_int(request.form.get("max_marks"))
        description = request.form.get("description", "").strip()
        try:
            weightage = float(request.form.get("weightage") or 1)
        except ValueError:
            weightage = -1

        others = sum(r.max_marks for r in exam.rubrics if not rubric or r.id != rubric.id)
        error = None
        if not criterion:
            error = "Criterion name is required."
        elif not max_marks or max_marks <= 0:
            error = "Maximum marks must be a positive number."
        elif weightage < 0:
            error = "Weightage must be zero or more."
        elif others + max_marks > exam.max_marks:
            error = (f"Rubric marks would total {others + max_marks}, "
                     f"more than the examination maximum of {exam.max_marks}.")
        if error:
            flash(error, "danger")
            return render(request.form)

        if rubric is None:
            rubric = ExaminationRubric(examination_id=exam.id)
            db.session.add(rubric)
        rubric.criterion_name, rubric.max_marks = criterion, max_marks
        rubric.weightage, rubric.description = weightage, description
        db.session.commit()
        flash("Rubric saved.", "success")
        return redirect(url_for("admin.exam_detail", exam_id=exam.id))

    f = {}
    if rubric:
        f = {"criterion_name": rubric.criterion_name, "max_marks": rubric.max_marks,
             "weightage": rubric.weightage, "description": rubric.description or ""}
    else:
        f = {"weightage": 1}
    return render(f)


@admin_bp.route("/exams/<int:exam_id>/rubrics/new", methods=["GET", "POST"])
def rubric_new(exam_id):
    return _rubric_form(db.get_or_404(Examination, exam_id), None)


@admin_bp.route("/rubrics/<int:rubric_id>/edit", methods=["GET", "POST"])
def rubric_edit(rubric_id):
    rubric = db.get_or_404(ExaminationRubric, rubric_id)
    return _rubric_form(rubric.examination, rubric)


@admin_bp.route("/rubrics/<int:rubric_id>/delete", methods=["POST"])
def rubric_delete(rubric_id):
    rubric = db.get_or_404(ExaminationRubric, rubric_id)
    exam_id = rubric.examination_id
    if RubricScore.query.filter_by(rubric_id=rubric.id).first():
        flash("Cannot delete: marks have already been given using this rubric.", "danger")
    else:
        db.session.delete(rubric)
        db.session.commit()
        flash("Rubric deleted.", "success")
    return redirect(url_for("admin.exam_detail", exam_id=exam_id))


# ---------- examiners ----------
@admin_bp.route("/examiners")
def examiners():
    return render_template("admin/examiners.html",
                           examiners=ExaminerProfile.query.order_by(ExaminerProfile.id.desc()).all())


@admin_bp.route("/examiners/new", methods=["GET", "POST"])
def examiner_new():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        department = request.form.get("department", "").strip()
        password = request.form.get("password", "")

        error = None
        if not (full_name and username and email and department and password):
            error = "Please fill all required fields."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif User.query.filter_by(username=username).first():
            error = "Username already taken."
        elif User.query.filter_by(email=email).first():
            error = "Email already registered."
        if error:
            flash(error, "danger")
            return render_template("admin/examiner_form.html", f=request.form)

        user = User(username=username, email=email, full_name=full_name, phone=phone,
                    role="examiner", password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.flush()
        db.session.add(ExaminerProfile(user_id=user.id, department=department,
                                       contact_details=phone, status="Approved"))
        db.session.commit()
        flash("Examiner added and approved.", "success")
        return redirect(url_for("admin.examiners"))
    return render_template("admin/examiner_form.html", f={})


@admin_bp.route("/examiners/<int:profile_id>/status", methods=["POST"])
def examiner_status(profile_id):
    profile = db.get_or_404(ExaminerProfile, profile_id)
    status = request.form.get("status")
    if status not in ("Approved", "Deactivated"):
        flash("Invalid status.", "danger")
    else:
        profile.status = status
        db.session.commit()
        flash(f"{profile.user.full_name} is now {status}.", "success")
    return redirect(url_for("admin.examiners"))


# ---------- students, slots, bookings (view all) ----------
@admin_bp.route("/students")
def students():
    return render_template("admin/students.html",
                           students=User.query.filter_by(role="student").order_by(User.id).all())


@admin_bp.route("/slots")
def slots():
    return render_template("admin/slots.html",
                           slots=ExaminationSlot.query.order_by(ExaminationSlot.date.desc()).all())


@admin_bp.route("/bookings")
def bookings():
    return render_template("admin/bookings.html",
                           bookings=Booking.query.order_by(Booking.id.desc()).all())


# ---------- search ----------
@admin_bp.route("/search")
def search():
    q = request.args.get("q", "").strip()
    kind = request.args.get("type", "students")
    results = []
    if q:
        like = f"%{q}%"
        is_id = q.isdigit()
        if kind == "students":
            cond = or_(User.full_name.ilike(like), User.username.ilike(like))
            if is_id:
                cond = or_(cond, User.id == int(q))
            results = User.query.filter(User.role == "student", cond).all()
        elif kind == "examiners":
            cond = or_(User.full_name.ilike(like), User.username.ilike(like))
            if is_id:
                cond = or_(cond, ExaminerProfile.id == int(q))
            results = (ExaminerProfile.query
                       .join(User, ExaminerProfile.user_id == User.id).filter(cond).all())
        elif kind == "exams":
            cond = Examination.name.ilike(like)
            if is_id:
                cond = or_(cond, Examination.id == int(q))
            results = Examination.query.filter(cond).all()
        elif kind == "bookings":
            cond = or_(User.full_name.ilike(like), Examination.name.ilike(like))
            if is_id:
                cond = or_(cond, Booking.id == int(q))
            results = (Booking.query
                       .join(User, Booking.student_id == User.id)
                       .join(Examination, Booking.examination_id == Examination.id)
                       .filter(cond).all())
    return render_template("admin/search.html", q=q, kind=kind, results=results)
