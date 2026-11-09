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
        "/auth/register", json={"email": "posture@example.com", "password": "strong-pass-1"}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _assessment(client, headers):
    response = client.post(
        "/assessment",
        json={
            "body_parts": ["neck", "shoulder"],
            "sedentary_minutes": 480,
            "available_minutes": 10,
            "pain_score": 2,
            "acute_discomfort": False,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _risk(client, headers, **overrides):
    payload = {
        "posture_class": "baseline",
        "confidence": 0.9,
        "deviation_deg": 3,
        "posture_duration_minutes": 5,
        "sitting_minutes": 10,
        "daily_sitting_minutes": 30,
        "minutes_since_last_break": 5,
        "pain_score": 0,
        "body_parts": ["neck", "shoulder"],
        "plan": "standard",
    }
    payload.update(overrides)
    return client.post("/posture/risk", json=payload, headers=headers)


def test_low_risk_does_not_interrupt(client, auth_headers):
    _assessment(client, auth_headers)
    response = _risk(client, auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["risk_level"] == "low"
    assert body["recommended_plan"] == "maintain"
    assert body["actions"] == []


def test_high_risk_returns_plan_matched_actions(client, auth_headers):
    _assessment(client, auth_headers)
    response = _risk(
        client,
        auth_headers,
        posture_class="forward_head",
        deviation_deg=30,
        posture_duration_minutes=30,
        sitting_minutes=60,
        daily_sitting_minutes=300,
        minutes_since_last_break=60,
        pain_score=8,
        plan="quick",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["risk_level"] in {"high", "very_high"}
    assert body["recommended_plan"] == "quick"
    assert body["actions"], body
    assert body["actions"][0]["intensity"] == "gentle"
    assert body["actions"][0]["match_reason"]
    assert body["citations"], body
    assert any(item["evidence_id"].startswith(("pmid-", "url-")) for item in body["citations"])


def test_red_flags_are_blocked_before_risk(client, auth_headers):
    _assessment(client, auth_headers)
    response = _risk(client, auth_headers, red_flags=["radiating_pain"])
    assert response.status_code == 403
    assert response.json()["error"] == "safety_short_circuit"


def test_posture_risk_in_openapi(client):
    schema = client.get("/openapi.json").json()
    assert "/posture/risk" in schema["paths"]
