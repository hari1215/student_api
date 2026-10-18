from functools import wraps
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt, get_jwt_identity, verify_jwt_in_request,
)
from . import db
from .models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def admin_required(fn):
    """Decorator: only tokens carrying role=admin may call the route."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()                       # 401 if no valid token
        if get_jwt().get("role") != "admin":
            return jsonify(error="Admin access required"), 403
        return fn(*args, **kwargs)
    return wrapper


def _tokens(user):
    claims = {"role": user.role}                      # role is stored inside the token
    return {
        "access_token": create_access_token(identity=str(user.id), additional_claims=claims),
        "refresh_token": create_refresh_token(identity=str(user.id), additional_claims=claims),
    }


@auth_bp.post("/register")
def register():
    d = request.get_json(silent=True) or {}
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    if len(username) < 3 or len(password) < 8:
        return jsonify(error="username >= 3 chars and password >= 8 chars required"), 400
    if User.query.filter_by(username=username).first():
        return jsonify(error="Username already taken"), 409
    role = "admin" if User.query.count() == 0 else "viewer"   # first user is admin
    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(message="Registered", username=username, role=role), 201


@auth_bp.post("/login")
def login():
    d = request.get_json(silent=True) or {}
    user = User.query.filter_by(username=d.get("username", "")).first()
    if not user or not user.check_password(d.get("password", "")):
        return jsonify(error="Invalid credentials"), 401     # same message for both cases
    return jsonify(**_tokens(user))


@auth_bp.post("/reset-password")
@admin_required
def reset_password():
    d = request.get_json(silent=True) or {}
    username = d.get("username")
    new_password = d.get("new_password")
    if not isinstance(username, str) or not username.strip():
        return jsonify(error="username is required"), 400
    if not isinstance(new_password, str) or len(new_password) < 8:
        return jsonify(error="new_password must be at least 8 characters"), 400

    user = User.query.filter_by(username=username.strip()).first()
    if not user:
        return jsonify(error="User not found"), 404

    user.set_password(new_password)
    db.session.commit()
    return jsonify(message="Password reset successfully", username=user.username)


@auth_bp.post("/change-password")
@jwt_required()
def change_password():
    d = request.get_json(silent=True) or {}
    old_password = d.get("old_password")
    new_password = d.get("new_password")
    if not isinstance(old_password, str) or not old_password:
        return jsonify(error="old_password is required"), 400
    if not isinstance(new_password, str) or len(new_password) < 8:
        return jsonify(error="new_password must be at least 8 characters"), 400

    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return jsonify(error="User no longer exists"), 401
    if not user.check_password(old_password):
        return jsonify(error="Current password is incorrect"), 401

    user.set_password(new_password)
    db.session.commit()
    return jsonify(message="Password changed successfully")


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return jsonify(error="User no longer exists"), 401
    return jsonify(access_token=_tokens(user)["access_token"])