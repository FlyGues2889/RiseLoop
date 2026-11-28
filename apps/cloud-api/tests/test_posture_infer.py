import statistics

import pytest
from fastapi.testclient import TestClient

from app.cloud.modelarts import ModelArtsError
from app.core.config import Settings
from app.main import create_app
from app.schemas.posture import MEDIAPIPE_33, Keypoint
from app.services.posture_features import baseline_from_keypoints, extract_features


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
    response = _infer(client, auth_headers, keypoints=_pose(nose={"y": 0.34}))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["posture"] == "forward_head"
    assert body["features"]["neck_ratio"] < 0.5
    assert body["features"]["neck_ratio_delta"] < -0.08
    assert body["deviation_deg"] > 0


def test_infer_uses_personal_baseline(client, auth_headers):
    pose = _pose(nose={"y": 0.34})
    default = _infer(client, auth_headers, keypoints=pose)
    assert default.json()["posture"] == "forward_head"

    baseline = {"shoulder_tilt_deg": 0.0, "neck_ratio": 0.4, "head_offset_ratio": 0.0}
    personal = _infer(client, auth_headers, keypoints=pose, baseline=baseline)
    assert personal.status_code == 200, personal.text
    body = personal.json()
    assert body["posture"] == "baseline"
    assert abs(body["features"]["neck_ratio_delta"]) < 0.01


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


def test_infer_works_when_only_head_and_shoulders_are_visible(client, auth_headers):
    points = _pose()
    upper = set(MEDIAPIPE_33[:13])
    for point in points:
        point["visibility"] = 0.95 if point["name"] in upper else 0.0
    response = _infer(client, auth_headers, keypoints=points)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["posture"] == "baseline"
    assert body["features"]["upper_body_visibility"] == 1.0


def test_infer_marks_undetermined_when_upper_body_is_mostly_hidden(client, auth_headers):
    points = _pose()
    for point in points:
        if point["name"] in MEDIAPIPE_33[3:11]:
            point["visibility"] = 0.1
    response = _infer(client, auth_headers, keypoints=points)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["features"]["upper_body_visibility"] < 0.5
    assert body["posture"] == "undetermined"


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


def test_infer_returns_503_when_mock_disabled():
    settings = Settings(
        cloud_provider="mock",
        posture_mock_policy="unavailable",
        jwt_secret="test-secret",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/auth/register",
            json={"email": "mockoff@example.com", "password": "strong-pass-1"},
        )
        assert response.status_code == 201, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        response = client.post("/posture/infer", json=_payload(), headers=headers)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "modelarts_unavailable"
    assert detail["reason"] == "mock_disabled"


def test_infer_in_openapi(client):
    schema = client.get("/openapi.json").json()
    assert "/posture/infer" in schema["paths"]
    assert "/posture/baseline" in schema["paths"]


def test_baseline_endpoint_returns_median_of_frames(client, auth_headers):
    poses = [_pose(nose={"y": 0.18 + delta}) for delta in (0.0, 0.005, -0.005, 0.01)]
    response = client.post(
        "/posture/baseline", json={"frames": poses}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["frames"] == len(poses)
    assert set(body["baseline"]) == {
        "shoulder_tilt_deg",
        "neck_ratio",
        "head_offset_ratio",
        "head_scale",
        "eye_scale",
        "face_height",
        "ear_shoulder_y",
        "head_roll_deg",
        "nose_ear_y",
        "ear_mid_offset",
    }
    values = [
        baseline_from_keypoints([Keypoint(**point) for point in pose]).neck_ratio
        for pose in poses
    ]
    assert body["baseline"]["neck_ratio"] == pytest.approx(
        statistics.median(values), abs=1e-4
    )


def test_baseline_endpoint_rejects_too_few_frames(client, auth_headers):
    response = client.post(
        "/posture/baseline", json={"frames": [_pose(), _pose()]}, headers=auth_headers
    )
    assert response.status_code == 422


def test_baseline_endpoint_rejects_wrong_keypoint_order(client, auth_headers):
    pose = _pose()
    pose[0], pose[1] = pose[1], pose[0]
    response = client.post(
        "/posture/baseline", json={"frames": [pose, pose, pose]}, headers=auth_headers
    )
    assert response.status_code == 422
    assert "关键点顺序不符" in response.text


def test_baseline_endpoint_requires_auth(client):
    response = client.post("/posture/baseline", json={"frames": [_pose()] * 3})
    assert response.status_code == 401


def test_mock_predict_zero_shoulder_width_is_undetermined():
    from app.cloud.modelarts import mock_predict
    from app.schemas.posture import PostureFeatures

    features = PostureFeatures(
        shoulder_tilt_deg=0.0,
        shoulder_width=0.0,
        shoulder_visibility=1.0,
        upper_body_visibility=1.0,
        neck_ratio=0.0,
        head_offset_ratio=0.0,
        neck_ratio_delta=0.0,
        head_offset_delta=0.0,
        tilt_delta_deg=0.0,
    )
    posture, confidence = mock_predict(features)
    assert posture.value == "undetermined"
    assert confidence == 0.0


def test_extract_features_rejects_nothing_but_is_deterministic():
    keypoints = [Keypoint(**point) for point in _pose()]
    first = extract_features(keypoints)
    second = extract_features(keypoints)
    assert first == second
    assert first.shoulder_width > 0
