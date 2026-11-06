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
