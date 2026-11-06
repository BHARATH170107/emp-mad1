from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user
from config import Config
from models import db, User

login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.examiner import examiner_bp
    from routes.student import student_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(examiner_bp)
    app.register_blueprint(student_bp)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("auth.dashboard_redirect"))
        return redirect(url_for("auth.login"))

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
