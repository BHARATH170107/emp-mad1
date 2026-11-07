from datetime import date
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user, logout_user


def role_required(role):
    """Allow only logged-in users with the given role.
    Examiners must also be Approved by the Admin."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in first.", "warning")
                return redirect(url_for("auth.login"))
            if current_user.role != role:
                flash("You are not allowed to open that page.", "danger")
                return redirect(url_for("auth.dashboard_redirect"))
            if role == "examiner":
                profile = current_user.examiner_profile
                if not profile or profile.status != "Approved":
                    logout_user()
                    flash("Your examiner account is not approved.", "danger")
                    return redirect(url_for("auth.login"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _in_window(start, end):
    today = date.today()
    if start and today < start:
        return False
    if end and today > end:
        return False
    return True


def slot_creation_open(exam):
    """Examiners may create slots only when Admin set status 'Slot Creation'
    AND today is inside the slot creation dates."""
    return exam.status == "Slot Creation" and _in_window(exam.slot_creation_start, exam.slot_creation_end)


def booking_open(exam):
    """Students may book only when status is 'Booking Open'
    AND today is inside the booking dates."""
    return exam.status == "Booking Open" and _in_window(exam.booking_start, exam.booking_end)


def slots_editable(exam):
    """Slots can be updated/removed only before student booking starts."""
    return exam.status in ("Draft", "Slot Creation")


def can_cancel_booking(booking):
    """A student may cancel only a 'Booked' booking, and only before the
    booking deadline (the exam's booking end date)."""
    if booking.status != "Booked":
        return False
    exam = booking.examination
    if exam.booking_end:
        return date.today() <= exam.booking_end
    return exam.status == "Booking Open"
