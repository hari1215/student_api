import csv
import io
import re
from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from . import db
from .auth import admin_required
from .models import Mark, Student

students_bp = Blueprint("students", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SORT_FIELDS = {"name": Student.name, "age": Student.age, "email": Student.email, "id": Student.id}


def validate_student(d, partial=False):
    """Return a dict of {field: problem}. Empty dict means the data is valid."""
    errors = {}
    if not partial or "name" in d:
        if not isinstance(d.get("name"), str) or not d["name"].strip():
            errors["name"] = "required, non-empty string"
    if not partial or "email" in d:
        if not isinstance(d.get("email"), str) or not EMAIL_RE.match(d["email"]):
            errors["email"] = "must be a valid email"
    if not partial or "age" in d:
        age = d.get("age")
        if not isinstance(age, int) or isinstance(age, bool) or not 3 <= age <= 100:
            errors["age"] = "must be an integer between 3 and 100"
    return errors


@students_bp.get("/students")
@jwt_required()                                   # any logged-in user
def list_students():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        limit = min(max(int(request.args.get("limit", 10)), 1), 100)   # cap at 100
    except ValueError:
        return jsonify(error="page and limit must be integers"), 400

    sort = request.args.get("sort", "id")
    desc = sort.startswith("-")                   # "-age" means descending
    column = SORT_FIELDS.get(sort.lstrip("-"))
    if column is None:
        return jsonify(error=f"sort must be one of {sorted(SORT_FIELDS)}"), 400

    query = Student.query
    if q := request.args.get("q"):                # optional name search
        query = query.filter(Student.name.ilike(f"%{q}%"))

    result = query.order_by(column.desc() if desc else column.asc()).paginate(
        page=page, per_page=limit, error_out=False
    )
    return jsonify(
        data=[s.to_dict() for s in result.items],
        page=result.page, limit=limit, total=result.total, pages=result.pages,
    )


@students_bp.post("/students")
@admin_required                                   # admins only
def create_student():
    d = request.get_json(silent=True) or {}
    errors = validate_student(d)
    if errors:
        return jsonify(error="Validation failed", fields=errors), 400
    if Student.query.filter_by(email=d["email"].lower()).first():
        return jsonify(error="Email already exists"), 409
    s = Student(name=d["name"].strip(), email=d["email"].lower(), age=d["age"])
    db.session.add(s)
    db.session.commit()
    return jsonify(s.to_dict()), 201


@students_bp.get("/students/<int:sid>")
@jwt_required()
def get_student(sid):
    return jsonify(db.get_or_404(Student, sid).to_dict())


@students_bp.put("/students/<int:sid>")
@admin_required
def update_student(sid):
    s = db.get_or_404(Student, sid)
    d = request.get_json(silent=True) or {}
    errors = validate_student(d, partial=True)    # partial: only validate fields sent
    if errors:
        return jsonify(error="Validation failed", fields=errors), 400
    if "email" in d:
        other = Student.query.filter_by(email=d["email"].lower()).first()
        if other and other.id != s.id:
            return jsonify(error="Email already exists"), 409
        s.email = d["email"].lower()
    if "name" in d:
        s.name = d["name"].strip()
    if "age" in d:
        s.age = d["age"]
    db.session.commit()
    return jsonify(s.to_dict())


@students_bp.delete("/students/<int:sid>")
@admin_required
def delete_student(sid):
    db.session.delete(db.get_or_404(Student, sid))
    db.session.commit()
    return "", 204

def validate_mark(d):
    errors = {}
    if not isinstance(d.get("subject"), str) or not d["subject"].strip():
        errors["subject"] = "required, non-empty string"
    s = d.get("score")
    if not isinstance(s, (int, float)) or isinstance(s, bool) or not 0 <= s <= 100:
        errors["score"] = "must be a number between 0 and 100"
    return errors


# ---------- Marks ----------

@students_bp.get("/students/<int:sid>/marks")
@jwt_required()
def get_marks(sid):
    s = db.get_or_404(Student, sid)
    scores = [m.score for m in s.marks]
    avg = round(sum(scores) / len(scores), 2) if scores else None
    return jsonify(student=s.to_dict(), marks=[m.to_dict() for m in s.marks], average=avg)


@students_bp.post("/students/<int:sid>/marks")
@admin_required
def add_mark(sid):
    s = db.get_or_404(Student, sid)
    d = request.get_json(silent=True) or {}
    errors = validate_mark(d)
    if errors:
        return jsonify(error="Validation failed", fields=errors), 400
    subject = d["subject"].strip().title()        # "maths" and "Maths" are the same subject
    if Mark.query.filter_by(student_id=s.id, subject=subject).first():
        return jsonify(error=f"Marks for {subject} already exist; use PUT to change"), 409
    m = Mark(student_id=s.id, subject=subject, score=d["score"])
    db.session.add(m)
    db.session.commit()
    return jsonify(m.to_dict()), 201


@students_bp.put("/students/<int:sid>/marks/<subject>")
@admin_required
def update_mark(sid, subject):
    m = Mark.query.filter_by(student_id=sid, subject=subject.title()).first_or_404()
    d = request.get_json(silent=True) or {}
    errors = validate_mark({"subject": m.subject, "score": d.get("score")})
    if errors:
        return jsonify(error="Validation failed", fields=errors), 400
    m.score = d["score"]
    db.session.commit()
    return jsonify(m.to_dict())


# ---------- Stats ----------

@students_bp.get("/stats")
@jwt_required()
def stats():
    # One SQL query: average score per student (only students who have marks)
    rows = (
        db.session.query(Student.id, Student.name, func.avg(Mark.score), func.count(Mark.id))
        .join(Mark).group_by(Student.id).all()
    )
    if not rows:
        return jsonify(students_with_marks=0, class_average=None, topper=None, subjects={})

    ranking = sorted(
        ({"id": i, "name": n, "average": round(a, 2), "subjects": c} for i, n, a, c in rows),
        key=lambda r: r["average"], reverse=True,
    )
    top_score = ranking[0]["average"]
    subjects = {
        sub: round(avg, 2)
        for sub, avg in db.session.query(Mark.subject, func.avg(Mark.score)).group_by(Mark.subject)
    }
    return jsonify(
        students_with_marks=len(ranking),
        class_average=round(sum(r["average"] for r in ranking) / len(ranking), 2),
        topper=[r for r in ranking if r["average"] == top_score],   # a list, so ties work
        ranking=ranking,
        subjects=subjects,
    )


# ---------- CSV export ----------

def _csv_safe(value):
    """Excel runs cells starting with = + - @ as formulas; a leading ' makes them plain text."""
    return "'" + value if isinstance(value, str) and value[:1] in "=+-@" else value


@students_bp.get("/students/export.csv")
@admin_required
def export_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "name", "email", "age", "average"])
    for s in Student.query.order_by(Student.id):
        scores = [m.score for m in s.marks]
        avg = round(sum(scores) / len(scores), 2) if scores else ""
        w.writerow([s.id, _csv_safe(s.name), _csv_safe(s.email), s.age, avg])
    return Response(
        out.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=students.csv"},
    )