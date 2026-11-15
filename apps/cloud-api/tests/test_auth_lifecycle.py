import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

CREDENTIALS = {"email": "lifecycle@example.com", "password": "strong-pass-1"}


def _client(**overrides) -> TestClient:
    settings = Settings(cloud_provider="mock", jwt_secret="test-secret", **overrides)
    return TestClient(create_app(settings))


@pytest.fixture()
def client():
    with _client() as test_client:
        yield test_client


def _register(client, **extra):
    payload = {**CREDENTIALS, **extra}
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_register_returns_refresh_token(client):
    data = _register(client)
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["refresh_expires_in"] > data["expires_in"]


def test_refresh_issues_new_pair_and_rotates_old_token(client):
    data = _register(client)
    refreshed = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["refresh_token"] != data["refresh_token"]

    # 旧的刷新令牌已被轮换作废
    replay = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["detail"] == "token_revoked"


def test_access_token_cannot_be_used_as_refresh_token(client):
    data = _register(client)
    response = client.post("/auth/refresh", json={"refresh_token": data["access_token"]})
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_refresh_token"


def test_refresh_rejects_garbage_token(client):
    response = client.post("/auth/refresh", json={"refresh_token": "not-a-token"})
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_refresh_token"


def test_logout_revokes_access_and_refresh_tokens(client):
    data = _register(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    logout = client.post(
        "/auth/logout", headers=headers, json={"refresh_token": data["refresh_token"]}
    )
    assert logout.status_code == 204, logout.text

    after = client.get("/intervention/current", headers=headers)
    assert after.status_code == 401
    assert after.json()["detail"] == "token_revoked"

    refresh = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refresh.status_code == 401
    assert refresh.json()["detail"] == "token_revoked"


def test_delete_account_removes_user_and_data(client):
    data = _register(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    client.post(
        "/assessment",
        headers=headers,
        json={
            "body_parts": ["neck"],
            "sedentary_minutes": 480,
            "available_minutes": 10,
            "pain_score": 2,
            "acute_discomfort": False,
        },
    )
    deleted = client.delete("/auth/account", headers=headers)
    assert deleted.status_code == 204, deleted.text

    login = client.post("/auth/login", json=CREDENTIALS)
    assert login.status_code == 401
    assert login.json()["detail"] == "invalid_credentials"

    again = client.delete("/auth/account", headers=headers)
    assert again.status_code == 404
    assert again.json()["detail"] == "user_not_found"


def test_auth_endpoints_are_rate_limited():
    with _client(rate_limit_auth_requests=1) as client:
        assert _register(client)["access_token"]
        blocked = client.post("/auth/login", json=CREDENTIALS)
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "rate_limited"
        assert blocked.headers["Retry-After"]


def test_capabilities_lists_interfaces_and_limits(client):
    response = client.get("/health/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["auth"] == {"refresh": True, "revoke": True, "account_delete": True}
    assert body["rate_limit"]["requests"] > 0
    assert body["store_backend"] == "memory"
    assert {item["name"] for item in body["dependencies"]} >= {"rds", "redis"}
