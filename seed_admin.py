from werkzeug.security import generate_password_hash
from app import create_app
from models import db, User

app = create_app()

with app.app_context():
    if User.query.filter_by(role="admin").first():
        print("Admin already exists.")
    else:
        admin = User(
            username="admin",
            email="admin@emp.com",
            password_hash=generate_password_hash("admin123"),
            role="admin",
            full_name="System Admin",
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin created: admin / admin123")
