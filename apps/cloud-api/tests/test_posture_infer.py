import pytest
from fastapi.testclient import TestClient

from app.cloud.modelarts import ModelArtsError
from app.core.config import Settings
from app.main import create_app
from app.schemas.posture import MEDIAPIPE_33, Keypoint
from app.services.posture_features import extract_features


@pytest.fixture()
def client():
    settings = Settings(cloud_provider="mock", jwt_secret="test-secret")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client):
    response = client.post(
        "/auth/register", json={"email": "infer@example.com", "password": "strong-pass-1"}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _pose(**overrides):
    """构造一组合成的 33 点；overrides 形如 {"nose": {"z": -0.1}}。"""
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

    keypoints = []
    for name in MEDIAPIPE_33:
        base = points.get(name, {"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9})
        keypoints.append({"name": name, **base})
    return keypoints


def _payload(**overrides):
    payload = {
        "keypoints": _pose(),
        "sitting_minutes": 10,
        "daily_sitting_minutes": 30,
        "minutes_since_last_break": 5,
        "pain_score": 0,
        "body_parts": ["neck", "shoulder"],
        "plan": "standard",
    }
    payload.update(overrides)
    return payload


def _infer(client, headers, **overrides):
    return client.post("/posture/infer", json=_payload(**overrides), headers=headers)


def test_infer_baseline_uses_mock_model(client, auth_headers):
    client.post(
        "/assessment",
        json={
            "body_parts": ["neck", "shoulder"],
            "sedentary_minutes": 480,
            "available_minutes": 10,
            "pain_score": 2,
            "acute_discomfort": False,
        },
        headers=auth_headers,
    )
    response = _infer(client, auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["posture"] == "baseline"
    assert body["source"] == "mock"
    assert body["guidance"]["overlay"] == "baseline_guide"
    assert body["features"]["shoulder_tilt_deg"] == pytest.approx(0.0, abs=0.01)
    assert body["risk"]["risk_level"] in {"low", "medium", "high", "very_high"}
    assert body["risk"]["disclaimer"]


def test_infer_detects_lateral_tilt(client, auth_headers):
    response = _infer(client, auth_headers, keypoints=_pose(right_shoulder={"y": 0.48}))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["posture"] == "lateral_tilt"
    assert body["guidance"]["overlay"] == "tilt_guide"
    assert body["deviation_deg"] > 8


def test_infer_detects_forward_head(client, auth_headers):
    response = _infer(client, auth_headers, keypoints=_pose(nose={"z": -0.12}))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["posture"] == "forward_head"
    assert body["features"]["head_forward_ratio"] > 0.25
    assert body["deviation_deg"] > 0


def test_infer_marks_undetermined_when_shoulders_hidden(client, auth_headers):
    response = _infer(
        client,
        auth_headers,
        keypoints=_pose(left_shoulder={"visibility": 0.1}, right_shoulder={"visibility": 0.1}),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["posture"] == "undetermined"
    assert body["guidance"]["overlay"] == "undetermined_guide"


def test_infer_rejects_wrong_keypoint_count(client, auth_headers):
    response = _infer(client, auth_headers, keypoints=_pose()[:-1])
    assert response.status_code == 422


def test_infer_rejects_wrong_keypoint_order(client, auth_headers):
    points = _pose()
    points[0], points[1] = points[1], points[0]
    response = _infer(client, auth_headers, keypoints=points)
    assert response.status_code == 422
    assert "关键点顺序不符" in response.text


def test_infer_blocks_red_flags_before_model(client, auth_headers):
    response = _infer(client, auth_headers, red_flags=["radiating_pain"])
    assert response.status_code == 403
    assert response.json()["error"] == "safety_short_circuit"


def test_infer_returns_503_when_modelarts_unavailable(client, auth_headers):
    class FailingModelArts:
        async def predict(self, **kwargs):
            raise ModelArtsError("timeout")

        async def close(self):
            return None

    client.app.state.cloud.modelarts = FailingModelArts()
    response = _infer(client, auth_headers)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "modelarts_unavailable"
    assert detail["reason"] == "timeout"


def test_infer_in_openapi(client):
    schema = client.get("/openapi.json").json()
    assert "/posture/infer" in schema["paths"]


def test_extract_features_rejects_nothing_but_is_deterministic():
    keypoints = [Keypoint(**point) for point in _pose()]
    first = extract_features(keypoints)
    second = extract_features(keypoints)
    assert first == second
    assert first.shoulder_width > 0
