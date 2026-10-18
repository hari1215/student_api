import os
from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()      # database handle, shared by all files
jwt = JWTManager()     # login-token handler, shared by all files


def create_app(config=None):
    app = Flask(__name__)

    # Settings come from environment variables, with safe defaults for development
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///students.db")
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-only-secret-change-me-in-production-0123456789")
    if config:
        app.config.update(config)      # tests pass their own settings here

    db.init_app(app)
    jwt.init_app(app)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    from . import models   # noqa: F401  (importing registers the tables)
    from .auth import auth_bp
    from .students import students_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)

    with app.app_context():
        db.create_all()                # creates tables that don't exist yet

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify(error="Authentication required", detail=reason), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify(error="Invalid token", detail=reason), 401

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return jsonify(error="Token expired"), 401
    return app