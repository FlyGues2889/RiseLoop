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
        "/auth/register", json={"email": "qa@example.com", "password": "strong-pass-1"}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _start_session(client, headers):
    client.post(
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


def test_qa_returns_cited_answer(client, auth_headers):
    _start_session(client, auth_headers)
    response = client.post(
        "/qa/ask",
        json={"question": "开会时颈肩紧张，怎么快速缓解？"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "knowledge:neck-shoulder-break" in body["citations"]
    assert body["answer"]
    assert body["state_hint"] == "S1"
    assert "不提供医疗诊断" in body["disclaimer"]


def test_qa_without_match_does_not_invent(client, auth_headers):
    _start_session(client, auth_headers)
    response = client.post(
        "/qa/ask", json={"question": "今天基金收益怎么样？"}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert "资料中没有直接对应的条目" in body["answer"]


def test_qa_red_flag_short_circuits(client, auth_headers):
    _start_session(client, auth_headers)
    response = client.post(
        "/qa/ask",
        json={"question": "my numbness worse and radiating pain is severe"},
        headers=auth_headers,
    )
    assert response.status_code == 403
    body = response.json()
    assert body["stop_exercise"] is True
    assert "numbness_worse" in body["red_flags"]


def test_qa_requires_auth(client):
    response = client.post("/qa/ask", json={"question": "久坐腰酸怎么办"})
    assert response.status_code == 401


def test_weekly_review_empty(client, auth_headers):
    _start_session(client, auth_headers)
    response = client.get("/review/weekly", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["interventions"]["total"] == 0
    assert body["interventions"]["completion_rate"] == 0
    assert body["pain"]["trend"] == "unknown"
    assert body["highlights"]
    assert body["current_state"] == "S1"


def test_weekly_review_counts_feedback(client, auth_headers):
    _start_session(client, auth_headers)
    client.post(
        "/sitting/heartbeat",
        json={"sitting_minutes": 50, "threshold_minutes": 45},
        headers=auth_headers,
    )
    action_id = client.get("/intervention/current", headers=auth_headers).json()["id"]
    client.post(
        "/intervention/feedback",
        json={
            "action_id": action_id,
            "completion": "completed",
            "feeling": "better",
            "pain_score": 2,
        },
        headers=auth_headers,
    )

    body = client.get("/review/weekly?days=7", headers=auth_headers).json()
    assert body["interventions"]["total"] == 1
    assert body["interventions"]["completed"] == 1
    assert body["interventions"]["completion_rate"] == 100.0
    assert body["pain"]["latest"] == 2


def test_weekly_review_rejects_bad_window(client, auth_headers):
    response = client.get("/review/weekly?days=0", headers=auth_headers)
    assert response.status_code == 422