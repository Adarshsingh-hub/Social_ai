"""app/__init__.py — Flask application factory"""

import logging
import os

from flask import Flask
from app.models import db


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    app.config["SECRET_KEY"]                  = os.environ["FLASK_SECRET_KEY"]
    app.config["SQLALCHEMY_DATABASE_URI"]     = os.getenv("DATABASE_URL", "sqlite:///social_ai.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"]   = {"pool_pre_ping": True}

    db.init_app(app)

    from app.routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()

    logging.basicConfig(
        level=logging.DEBUG if os.getenv("FLASK_ENV") == "development" else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    return app