from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from sqlalchemy import or_
from models import db, User, Course, Examination, ExaminationSlot, Booking
from utils import to_int, booking_open, can_cancel_booking

student_bp = Blueprint("student", __name__, url_prefix="/student")

EXAM_TYPES = ["Viva", "Practical", "Project Demo", "Assessment"]


@student_bp.before_request
def student_only():
    """Runs before EVERY student route: must be a logged-in student."""
    if not current_user.is_authenticated:
        flash("Please log in first.", "warning")
        return redirect(url_for("auth.login"))
    if current_user.role != "student":
        flash("You are not allowed to open that page.", "danger")
        return redirect(url_for("auth.dashboard_redirect"))


@student_bp.errorhandler(403)
def forbidden(e):
    flash("That booking belongs to another student.", "danger")
    return redirect(url_for("student.dashboard"))


def my_bookings():
    """Only THIS student's bookings."""
    return Booking.query.filter_by(student_id=current_user.id)


def active_booking(exam_id):
    """A Booked or Completed booking for this exam (cancelled ones don't count)."""
    return (my_bookings()
            .filter(Booking.examination_id == exam_id, Booking.status != "Cancelled")
            .first())


def upcoming_bookings():
    rows = (my_bookings()
            .join(ExaminationSlot, Booking.slot_id == ExaminationSlot.id)
            .filter(Booking.status == "Booked", ExaminationSlot.date >= date.today())
            .order_by(ExaminationSlot.date, ExaminationSlot.start_time).all())
    return rows


def published_results():
    return [b for b in my_bookings().order_by(Booking.id.desc())
            if b.evaluation and b.examination.results_published]


# ---------- dashboard ----------
@student_bp.route("/dashboard")
def dashboard():
    today = date.today()
    open_exams = [e for e in Examination.query.filter_by(status="Booking Open") if booking_open(e)]
    slot_count = sum(1 for e in open_exams for s in e.slots
                     if s.status == "Available" and s.available_seats > 0 and s.date >= today)
    upcoming = upcoming_bookings()
    cards = [
        ("Available Examinations", len(open_exams), url_for("student.exams", open=1)),
        ("Available Slots", slot_count, url_for("student.exams", open=1)),
        ("Upcoming Examinations", len(upcoming), url_for("student.schedule")),
        ("My Bookings", my_bookings().count(), url_for("student.bookings")),
        ("Published Results", len(published_results()), url_for("student.results")),
    ]
    return render_template("student/dashboard.html", cards=cards, upcoming=upcoming)


# ---------- profile ----------
@student_bp.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        clash = User.query.filter_by(email=email).first()
        error = None
        if not (full_name and email):
            error = "Name and email are required."
        elif clash and clash.id != current_user.id:
            error = "That email is used by another account."
        if error:
            flash(error, "danger")
            return render_template("student/profile.html", f=request.form)
        current_user.full_name, current_user.email, current_user.phone = full_name, email, phone
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("student.profile"))
    f = {"full_name": current_user.full_name, "email": current_user.email,
         "phone": current_user.phone or ""}
    return render_template("student/profile.html", f=f)


# ---------- examinations: search / filter ----------
@student_bp.route("/exams")
def exams():
    q = request.args.get("q", "").strip()
    etype = request.args.get("type", "")
    course_id = to_int(request.args.get("course"))
    only_open = request.args.get("open") == "1"

    query = (Examination.query
             .join(Course, Examination.course_id == Course.id)
             .filter(Examination.status != "Draft"))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Examination.name.ilike(like),
                                 Course.code.ilike(like), Course.name.ilike(like)))
    if etype in EXAM_TYPES:
        query = query.filter(Examination.exam_type == etype)
    if course_id:
        query = query.filter(Examination.course_id == course_id)

    rows = [(e, booking_open(e), active_booking(e.id)) for e in query.order_by(Examination.id.desc())]
    if only_open:
        rows = [r for r in rows if r[1]]
    courses = Course.query.filter_by(status="Active").order_by(Course.code).all()
    return render_template("student/exams.html", rows=rows, courses=courses,
                           exam_types=EXAM_TYPES, q=q, etype=etype,
                           course_id=course_id, only_open=only_open)


@student_bp.route("/exams/<int:exam_id>")
def exam_detail(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    if exam.status == "Draft":
        abort(404)
    today = date.today()
    slots = (ExaminationSlot.query
             .filter(ExaminationSlot.examination_id == exam.id,
                     ExaminationSlot.status != "Cancelled",
                     ExaminationSlot.date >= today)
             .order_by(ExaminationSlot.date, ExaminationSlot.start_time).all())
    return render_template("student/exam_detail.html", exam=exam, slots=slots,
                           is_open=booking_open(exam), mine=active_booking(exam.id))


# ---------- book ----------
@student_bp.route("/slots/<int:slot_id>/book", methods=["POST"])
def book(slot_id):
    slot = db.get_or_404(ExaminationSlot, slot_id)
    exam = slot.examination
    back = redirect(url_for("student.exam_detail", exam_id=exam.id))

    # ---- every rule is checked on the server ----
    if not booking_open(exam):
        flash("Slot booking is closed for this examination.", "danger")
        return back
    if slot.status == "Cancelled" or slot.date < date.today():
        flash("This slot is not available.", "danger")
        return back
    if slot.status == "Full" or slot.available_seats <= 0:
        flash("This slot is full.", "danger")
        return back
    if active_booking(exam.id):
        flash("You already have a booking for this examination.", "danger")
        return back
    for b in my_bookings().filter(Booking.status == "Booked"):
        o = b.slot
        if o.date == slot.date and slot.start_time < o.end_time and slot.end_time > o.start_time:
            flash("This overlaps another examination you have booked.", "danger")
            return back

    db.session.add(Booking(student_id=current_user.id, slot_id=slot.id,
                           examination_id=exam.id, status="Booked"))
    slot.available_seats -= 1
    if slot.available_seats == 0:
        slot.status = "Full"  # auto-close when capacity is reached
    db.session.commit()
    flash("Slot booked successfully!", "success")
    return redirect(url_for("student.bookings"))


# ---------- cancel ----------
@student_bp.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
def cancel(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.student_id != current_user.id:
        abort(403)
    if not can_cancel_booking(booking):
        flash("This booking can no longer be cancelled (deadline passed or already completed).", "danger")
        return redirect(url_for("student.bookings"))

    booking.status = "Cancelled"
    slot = booking.slot
    slot.available_seats += 1
    if slot.status == "Full":
        slot.status = "Available"  # a seat is free again
    db.session.commit()
    flash("Booking cancelled.", "success")
    return redirect(url_for("student.bookings"))


# ---------- my bookings / history / schedule / results ----------
@student_bp.route("/bookings")
def bookings():
    rows = [(b, can_cancel_booking(b)) for b in my_bookings().order_by(Booking.id.desc())]
    return render_template("student/bookings.html", rows=rows)


@student_bp.route("/schedule")
def schedule():
    return render_template("student/schedule.html", bookings=upcoming_bookings())


@student_bp.route("/results")
def results():
    return render_template("student/results.html", bookings=published_results())
