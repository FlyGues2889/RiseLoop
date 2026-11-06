import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def client():
    settings = Settings(cloud_provider="mock", jwt_secret="test-secret")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client):
    response = client.post(
        "/auth/register", json={"email": "user@example.com", "password": "strong-pass-1"}
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _assessment(client, headers, **overrides):
    payload = {
        "body_parts": ["neck", "shoulder"],
        "sedentary_minutes": 480,
        "available_minutes": 10,
        "pain_score": 2,
        "acute_discomfort": False,
    }
    payload.update(overrides)
    return client.post("/assessment", json=payload, headers=headers)


def test_register_requires_unique_email(client):
    first = client.post("/auth/register", json={"email": "a@b.com", "password": "12345678"})
    second = client.post("/auth/register", json={"email": "a@b.com", "password": "12345678"})
    assert first.status_code == 201
    assert second.status_code == 409


def test_login_rejects_wrong_password(client):
    client.post("/auth/register", json={"email": "a@b.com", "password": "12345678"})
    response = client.post("/auth/login", json={"email": "a@b.com", "password": "bad-pass"})
    assert response.status_code == 401


def test_protected_route_requires_token(client):
    response = client.post(
        "/assessment",
        json={
            "body_parts": ["neck"],
            "sedentary_minutes": 60,
            "available_minutes": 5,
            "pain_score": 1,
        },
    )
    assert response.status_code == 401


def test_assessment_acute_goes_s0(client, auth_headers):
    response = _assessment(client, auth_headers, pain_score=8, acute_discomfort=True)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["initial_state"] == "S0"
    assert body["state_name"] == "急性缓解"
    assert body["risk_level"] == "high"
    assert body["intensity"] == "gentle"
    assert "不提供医疗诊断" in body["disclaimer"]


def test_assessment_without_symptoms_starts_s1(client, auth_headers):
    body = _assessment(client, auth_headers).json()
    assert body["initial_state"] == "S1"
    assert body["risk_level"] == "low"
    assert body["plan"]["push_threshold_minutes"] == 45


def test_heartbeat_below_threshold(client, auth_headers):
    _assessment(client, auth_headers)
    response = client.post(
        "/sitting/heartbeat", json={"sitting_minutes": 20, "threshold_minutes": 45}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["triggered"] is False
    assert body["reason"] == "below_threshold"
    assert body["next_check_minutes"] == 25


def test_heartbeat_triggers_then_cooldown(client, auth_headers):
    _assessment(client, auth_headers)
    first = client.post(
        "/sitting/heartbeat", json={"sitting_minutes": 50, "threshold_minutes": 45}, headers=auth_headers
    ).json()
    assert first["triggered"] is True
    assert first["action"]["duration_minutes"] <= 5

    second = client.post(
        "/sitting/heartbeat", json={"sitting_minutes": 55, "threshold_minutes": 45}, headers=auth_headers
    ).json()
    assert second["triggered"] is False
    assert second["reason"] == "cooldown"


def test_heartbeat_threshold_validation(client, auth_headers):
    response = client.post(
        "/sitting/heartbeat", json={"sitting_minutes": 50, "threshold_minutes": 90}, headers=auth_headers
    )
    assert response.status_code == 422


def test_feedback_upgrade_path(client, auth_headers):
    _assessment(client, auth_headers, pain_score=5)
    client.post(
        "/sitting/heartbeat", json={"sitting_minutes": 50, "threshold_minutes": 45}, headers=auth_headers
    )
    action_id = client.get("/intervention/current", headers=auth_headers).json()["id"]

    response = client.post(
        "/intervention/feedback",
        json={"action_id": action_id, "completion": "completed", "feeling": "better", "pain_score": 2},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["from_state"] == "S0"
    assert body["transition_type"] in {"hold", "upgrade"}
    assert body["disclaimer"]


def test_feedback_red_flag_is_blocked_by_middleware(client, auth_headers):
    _assessment(client, auth_headers)
    response = client.post(
        "/intervention/feedback",
        json={
            "action_id": "s1-stand-break",
            "completion": "partial",
            "feeling": "worse",
            "pain_score": 6,
            "red_flags": ["radiating_pain"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 403
    body = response.json()
    assert body["stop_exercise"] is True
    assert body["to_state"] == "S0"
    assert body["medical_advice"] is True


def test_feedback_free_text_red_flag_blocked(client, auth_headers):
    _assessment(client, auth_headers)
    response = client.post(
        "/intervention/feedback",
        json={
            "action_id": "s1-stand-break",
            "completion": "skipped",
            "feeling": "same",
            "pain_score": 3,
            "note": "做完以后手麻加重，还串电到手指",
        },
        headers=auth_headers,
    )
    assert response.status_code == 403
    assert "numbness_worse" in response.json()["red_flags"]


def test_actions_endpoint_filters_by_state(client, auth_headers):
    _assessment(client, auth_headers)
    response = client.get("/actions/S1", headers=auth_headers)
    assert response.status_code == 200
    actions = response.json()
    assert actions and all(action["id"].startswith("s1") for action in actions)


def test_wearable_ingest_is_reserved(client, auth_headers):
    response = client.post("/ingest/wearable", json={}, headers=auth_headers)
    assert response.status_code == 501


def test_openapi_schema_available(client):
    schema = client.get("/openapi.json").json()
    assert "/assessment" in schema["paths"]
    assert "/sitting/heartbeat" in schema["paths"]
    assert "/intervention/feedback" in schema["paths"]