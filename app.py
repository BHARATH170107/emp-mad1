from flask import Flask
from config import Config
from models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()  # tables are created by code, not by hand

    @app.route("/")
    def home():
        return "EMP is running"

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
