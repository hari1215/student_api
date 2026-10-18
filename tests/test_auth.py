import pytest
from app import create_app, db


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def register_and_login(client, username, password):
    response = client.post("/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


@pytest.fixture
def accounts(client):
    admin = register_and_login(client, "admin", "adminpass123")
    viewer = register_and_login(client, "viewer", "viewerpass123")
    return admin, viewer


def test_admin_can_reset_user_password(client, accounts):
    admin = accounts[0]

    response = client.post(
        "/auth/reset-password",
        json={"username": "viewer", "new_password": "newpass456"},
        headers=admin,
    )

    assert response.status_code == 200
    assert response.get_json()["username"] == "viewer"
    assert client.post(
        "/auth/login", json={"username": "viewer", "password": "viewerpass123"}
    ).status_code == 401
    assert client.post(
        "/auth/login", json={"username": "viewer", "password": "newpass456"}
    ).status_code == 200


def test_only_admin_can_reset_password(client, accounts):
    viewer = accounts[1]

    response = client.post(
        "/auth/reset-password",
        json={"username": "viewer", "new_password": "newpass456"},
        headers=viewer,
    )

    assert response.status_code == 403


def test_reset_password_requires_authentication(client):
    response = client.post(
        "/auth/reset-password",
        json={"username": "viewer", "new_password": "newpass456"},
    )

    assert response.status_code == 401


def test_reset_password_validates_target_and_password(client, accounts):
    admin = accounts[0]

    response = client.post(
        "/auth/reset-password",
        json={"username": "viewer", "new_password": "short"},
        headers=admin,
    )
    assert response.status_code == 400

    response = client.post(
        "/auth/reset-password",
        json={"username": "missing", "new_password": "newpass456"},
        headers=admin,
    )
    assert response.status_code == 404


def test_user_can_change_own_password(client, accounts):
    viewer = accounts[1]

    response = client.post(
        "/auth/change-password",
        json={"old_password": "viewerpass123", "new_password": "newpass456"},
        headers=viewer,
    )

    assert response.status_code == 200
    assert client.post(
        "/auth/login", json={"username": "viewer", "password": "viewerpass123"}
    ).status_code == 401
    assert client.post(
        "/auth/login", json={"username": "viewer", "password": "newpass456"}
    ).status_code == 200


def test_change_password_rejects_incorrect_current_password(client, accounts):
    viewer = accounts[1]

    response = client.post(
        "/auth/change-password",
        json={"old_password": "wrongpass123", "new_password": "newpass456"},
        headers=viewer,
    )

    assert response.status_code == 401


def test_change_password_requires_authentication_and_valid_new_password(client, accounts):
    viewer = accounts[1]

    response = client.post(
        "/auth/change-password",
        json={"old_password": "viewerpass123", "new_password": "short"},
    )
    assert response.status_code == 401

    response = client.post(
        "/auth/change-password",
        json={"old_password": "viewerpass123", "new_password": "short"},
        headers=viewer,
    )
    assert response.status_code == 400
