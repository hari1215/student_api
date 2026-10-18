import pytest
from app import create_app, db


@pytest.fixture
def client():
    # in-memory database: fast, and thrown away after every test
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def register_login(client, username, password="password123"):
    client.post("/auth/register", json={"username": username, "password": password})
    r = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


@pytest.fixture
def admin(client):
    return register_login(client, "admin")      # first user becomes admin


@pytest.fixture
def viewer(client, admin):
    return register_login(client, "viewer")     # second user is a viewer


def add_student(client, headers, name="Asha", email="asha@x.com", age=20):
    return client.post("/students", json={"name": name, "email": email, "age": age}, headers=headers)


# ---- authentication ----
def test_requires_token(client):
    assert client.get("/students").status_code == 401


def test_bad_login(client, admin):
    r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_viewer_cannot_create_but_can_read(client, admin, viewer):
    assert add_student(client, viewer).status_code == 403
    assert client.get("/students", headers=viewer).status_code == 200


# ---- validation ----
@pytest.mark.parametrize("payload", [
    {"name": "", "email": "a@b.com", "age": 20},
    {"name": "A", "email": "not-an-email", "age": 20},
    {"name": "A", "email": "a@b.com", "age": 2},
    {"name": "A", "email": "a@b.com", "age": "20"},
])
def test_invalid_student_rejected(client, admin, payload):
    assert client.post("/students", json=payload, headers=admin).status_code == 400


def test_duplicate_email(client, admin):
    add_student(client, admin)
    assert add_student(client, admin, name="Other").status_code == 409


# ---- pagination and sorting ----
def test_pagination_and_sort(client, admin):
    for i in range(25):
        add_student(client, admin, name=f"S{i:02d}", email=f"s{i}@x.com")
    r = client.get("/students?page=3&limit=10&sort=name", headers=admin).get_json()
    assert r["total"] == 25 and r["pages"] == 3 and len(r["data"]) == 5
    r = client.get("/students?limit=3&sort=-name", headers=admin).get_json()
    assert r["data"][0]["name"] == "S24"


# ---- marks and stats ----
def test_stats_topper(client, admin):
    a = add_student(client, admin, "Asha", "a@x.com").get_json()["id"]
    b = add_student(client, admin, "Ravi", "r@x.com").get_json()["id"]
    for sid, scores in ((a, (90, 80)), (b, (60, 70))):
        for subject, score in zip(("maths", "science"), scores):
            client.post(f"/students/{sid}/marks", json={"subject": subject, "score": score}, headers=admin)
    r = client.get("/stats", headers=admin).get_json()
    assert r["topper"][0]["id"] == a and r["class_average"] == 75.0


# ---- csv ----
def test_csv_admin_only(client, admin, viewer):
    assert client.get("/students/export.csv", headers=viewer).status_code == 403
    r = client.get("/students/export.csv", headers=admin)
    assert r.mimetype == "text/csv"