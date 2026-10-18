from werkzeug.security import generate_password_hash, check_password_hash
from . import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="viewer")  # admin or viewer

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)   # never store the real password

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    age = db.Column(db.Integer, nullable=False)
    marks = db.relationship("Mark", backref="student", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email, "age": self.age}


class Mark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Float, nullable=False)

    __table_args__ = (db.UniqueConstraint("student_id", "subject"),)   # one score per subject

    def to_dict(self):
        return {"id": self.id, "subject": self.subject, "score": self.score}