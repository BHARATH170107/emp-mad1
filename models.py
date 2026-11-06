from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """One table for Admin, Examiner and Student. role decides which."""
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin / examiner / student
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    examiner_profile = db.relationship("ExaminerProfile", backref="user", uselist=False)
    bookings = db.relationship("Booking", backref="student", lazy=True)

    @property
    def is_active(self):  # Flask-Login uses this
        return self.active


class ExaminerProfile(db.Model):
    __tablename__ = "examiner_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    department = db.Column(db.String(100))
    contact_details = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Pending")  # Pending / Approved / Deactivated

    examinations = db.relationship("Examination", backref="examiner", lazy=True)
    slots = db.relationship("ExaminationSlot", backref="examiner", lazy=True)


class Course(db.Model):
    __tablename__ = "courses"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="Active")  # Active / Inactive

    examinations = db.relationship("Examination", backref="course", lazy=True)


class Examination(db.Model):
    __tablename__ = "examinations"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("examiner_profiles.id"))  # assigned examiner
    name = db.Column(db.String(100), nullable=False)
    exam_type = db.Column(db.String(30), nullable=False)  # Viva / Practical / Project Demo / Assessment
    duration = db.Column(db.Integer, nullable=False)  # minutes
    max_marks = db.Column(db.Integer, nullable=False)
    slot_creation_start = db.Column(db.Date)
    slot_creation_end = db.Column(db.Date)
    booking_start = db.Column(db.Date)
    booking_end = db.Column(db.Date)
    # Draft / Slot Creation / Booking Open / Closed / Completed
    status = db.Column(db.String(20), default="Draft")
    results_published = db.Column(db.Boolean, default=False)

    rubrics = db.relationship("ExaminationRubric", backref="examination",
                              lazy=True, cascade="all, delete-orphan")
    slots = db.relationship("ExaminationSlot", backref="examination", lazy=True)
    bookings = db.relationship("Booking", backref="examination", lazy=True)


class ExaminationRubric(db.Model):
    __tablename__ = "examination_rubrics"
    id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey("examinations.id"), nullable=False)
    criterion_name = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)
    weightage = db.Column(db.Float, default=1.0)
    description = db.Column(db.Text)


class ExaminationSlot(db.Model):
    __tablename__ = "examination_slots"
    id = db.Column(db.Integer, primary_key=True)
    examination_id = db.Column(db.Integer, db.ForeignKey("examinations.id"), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("examiner_profiles.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="Available")  # Available / Full / Cancelled / Completed

    bookings = db.relationship("Booking", backref="slot", lazy=True)


class Booking(db.Model):
    __tablename__ = "bookings"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey("examination_slots.id"), nullable=False)
    # copied from the slot so duplicate checks are easy
    examination_id = db.Column(db.Integer, db.ForeignKey("examinations.id"), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="Booked")  # Booked / Cancelled / Completed

    evaluation = db.relationship("Evaluation", backref="booking", uselist=False)


class Evaluation(db.Model):
    """Marks and remarks for one booking."""
    __tablename__ = "evaluations"
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False)
    total_marks = db.Column(db.Float, default=0)
    remarks = db.Column(db.Text)
    evaluated_at = db.Column(db.DateTime, default=datetime.utcnow)

    scores = db.relationship("RubricScore", backref="evaluation",
                             lazy=True, cascade="all, delete-orphan")


class RubricScore(db.Model):
    """Marks given for one rubric criterion inside an evaluation."""
    __tablename__ = "rubric_scores"
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("evaluations.id"), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey("examination_rubrics.id"), nullable=False)
    marks = db.Column(db.Float, nullable=False)

    rubric = db.relationship("ExaminationRubric")
