"""姿态摘要落库：RDS 存事实、DCS 存实时（mock 下用进程内缓存兜底）。"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.db.models import PostureSummary
from app.schemas.posture import MEDIAPIPE_33
from app.services.posture_infer import reset_posture_write_state


@pytest.fixture()
def client():
    reset_posture_write_state()
    settings = Settings(cloud_provider="mock", jwt_secret="test-secret")
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    reset_posture_write_state()


@pytest.fixture()
def auth_headers(client):
    response = client.post(
        "/auth/register", json={"email": "persist@example.com", "password": "strong-pass-1"}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _pose(**overrides):
    points = {
        "nose": {"x": 0.50, "y": 0.18, "z": 0.0, "visibility": 0.99},
        "left_shoulder": {"x": 0.40, "y": 0.42, "z": 0.0, "visibility": 0.98},
        "right_shoulder": {"x": 0.60, "y": 0.42, "z": 0.0, "visibility": 0.98},
        "left_hip": {"x": 0.43, "y": 0.70, "z": 0.0, "visibility": 0.9},
        "right_hip": {"x": 0.57, "y": 0.70, "z": 0.0, "visibility": 0.9},
    }
    for name, patch in overrides.items():
        points.setdefault(name, {"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9})
        points[name].update(patch)
    return [
        {"name": name, **points.get(name, {"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9})}
        for name in MEDIAPIPE_33
    ]


def _infer(client, headers, keypoints=None):
    payload = {
        "keypoints": keypoints or _pose(),
        "sitting_minutes": 10,
        "daily_sitting_minutes": 40,
        "minutes_since_last_break": 5,
        "pain_score": 1,
        "body_parts": ["neck"],
        "plan": "standard",
    }
    response = client.post("/posture/infer", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _summaries(client, user_id):
    return client.app.state.store._posture_summaries.get(user_id, [])


def test_rds_table_definition_is_importable():
    """huawei 模式下 SqlStore 才会加载该模型，这里提前挡住语法/映射错误。"""
    columns = set(PostureSummary.__table__.columns.keys())
    assert columns >= {
        "id",
        "user_id",
        "posture_class",
        "confidence",
        "risk_level",
        "brli",
        "duration_minutes",
        "source",
        "model_name",
        "created_at",
    }


def test_first_inference_is_persisted_without_keypoints(client, auth_headers):
    body = _infer(client, auth_headers)
    assert body["recorded"] is True

    user_id = client.app.state.store._emails["persist@example.com"]
    rows = _summaries(client, user_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["posture_class"] == body["posture"]
    assert row["risk_level"] == body["risk"]["risk_level"]
    assert row["source"] == "mock"
    # 隐私红线：摘要里不得出现关键点序列
    assert "keypoints" not in row
    assert set(row) >= {
        "posture_class",
        "confidence",
        "risk_level",
        "brli",
        "duration_minutes",
        "source",
    }


def test_repeated_same_posture_is_throttled(client, auth_headers):
    _infer(client, auth_headers)
    second = _infer(client, auth_headers)
    assert second["recorded"] is False

    user_id = client.app.state.store._emails["persist@example.com"]
    assert len(_summaries(client, user_id)) == 1


def test_posture_change_is_persisted_immediately(client, auth_headers):
    _infer(client, auth_headers)
    _infer(client, auth_headers, keypoints=_pose(right_shoulder={"y": 0.48}))

    user_id = client.app.state.store._emails["persist@example.com"]
    rows = _summaries(client, user_id)
    assert len(rows) == 2
    assert [row["posture_class"] for row in rows] == ["baseline", "lateral_tilt"]


def test_weekly_review_reads_posture_facts(client, auth_headers):
    _infer(client, auth_headers, keypoints=_pose(right_shoulder={"y": 0.48}))
    review = client.get("/review/weekly", headers=auth_headers)
    assert review.status_code == 200, review.text
    posture = review.json()["posture"]
    assert posture["samples"] >= 1
    assert posture["dominant"] in {"baseline", "lateral_tilt", "forward_head", "undetermined"}
    assert 0.0 <= posture["high_risk_ratio"] <= 1.0
