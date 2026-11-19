"""训练侧契约与云端实现的一致性；合并训练包后必须全绿，不允许 skip。"""

from __future__ import annotations

import json
import random

import pytest

import dataset_check
import label_policy
import posture_contract as contract
import posture_runtime as runtime


def _pose(rng: random.Random) -> list[dict]:
    offsets = {
        "nose": (0.50, 0.18, 0.00),
        "left_shoulder": (0.40, 0.42, 0.00),
        "right_shoulder": (0.60, 0.42, 0.00),
        "left_hip": (0.43, 0.70, 0.00),
        "right_hip": (0.57, 0.70, 0.00),
    }
    points = []
    for name in contract.KEYPOINT_ORDER:
        x, y, z = offsets.get(name, (0.5, 0.5, 0.0))
        points.append(
            {
                "name": name,
                "x": round(min(1.0, max(0.0, x + rng.uniform(-0.05, 0.05))), 4),
                "y": round(min(1.0, max(0.0, y + rng.uniform(-0.05, 0.05))), 4),
                "z": round(z + rng.uniform(-0.2, 0.2), 4),
                "visibility": round(rng.uniform(0.0, 1.0), 3),
            }
        )
    return points


def _frame(label: str = "baseline") -> dict:
    keypoints = _pose(random.Random(7))
    return {
        "frame_id": "t-0001",
        "ts": "2026-11-19T10:00:00+08:00",
        "device": "unit-test",
        "subject": "s1",
        "scene": "desk",
        "keypoints": keypoints,
        "features": contract.features_from_keypoints(keypoints),
        "label": label,
        "label_source": "prelabel",
        "origin": "synthetic",
    }


def _write(tmp_path, frames):
    path = tmp_path / "frames.jsonl"
    path.write_text(
        "\n".join(json.dumps(frame, ensure_ascii=False) for frame in frames) + "\n",
        encoding="utf-8",
    )
    return path


def test_constants_follow_cloud_api():
    assert contract.KEYPOINT_ORDER == contract.MEDIAPIPE_33
    assert len(contract.KEYPOINT_ORDER) == 33
    assert contract.LABELS == ("baseline", "forward_head", "lateral_tilt", "undetermined")
    assert contract.FEATURE_ORDER == (
        "shoulder_tilt_deg",
        "shoulder_width",
        "shoulder_visibility",
        "head_forward_ratio",
        "torso_lean_deg",
        "visible_ratio",
    )


def test_runtime_copy_matches_cloud_features():
    assert runtime.FEATURE_SPEC_VERSION == contract.FEATURE_SPEC_VERSION
    assert runtime.LABELS == contract.LABELS
    rng = random.Random(20261119)
    for _ in range(300):
        keypoints = _pose(rng)
        expected = contract.features_from_keypoints(keypoints)
        actual = runtime.features_from_keypoints(keypoints)
        assert actual == pytest.approx(expected, abs=1e-12)


def test_runtime_vector_order_is_schema_order():
    features = _frame()["features"]
    assert runtime.features_vector(features) == contract.features_vector(features)
    assert len(contract.coordinates_vector(_frame()["keypoints"])) == 132


def test_runtime_rejects_incomplete_input():
    with pytest.raises(ValueError):
        runtime.features_from_keypoints(_pose(random.Random(1))[:-1])
    duplicated = _pose(random.Random(2))
    duplicated[1] = dict(duplicated[0])
    with pytest.raises(ValueError):
        runtime.features_from_keypoints(duplicated)


def test_build_response_returns_native_floats():
    response = runtime.build_response(
        {"baseline": 0.1, "forward_head": 0.7, "lateral_tilt": 0.1, "undetermined": 0.1}
    )
    assert response["posture"] == "forward_head"
    assert isinstance(response["confidence"], float)
    assert all(isinstance(value, float) for value in response["probabilities"].values())


def test_dataset_check_accepts_valid_file(tmp_path):
    report = dataset_check.check_dataset(_write(tmp_path, [_frame(), _frame("lateral_tilt")]))
    assert report.ok, report.errors
    assert report.frames == 2
    assert report.subjects == {"s1"}


def test_dataset_check_flags_feature_drift(tmp_path):
    frame = _frame()
    frame["features"]["shoulder_tilt_deg"] += 0.5
    report = dataset_check.check_dataset(_write(tmp_path, [frame]))
    assert not report.ok
    assert any("shoulder_tilt_deg" in item["error"] for item in report.errors)


def test_dataset_check_flags_keypoint_order(tmp_path):
    frame = _frame()
    frame["keypoints"][0], frame["keypoints"][1] = frame["keypoints"][1], frame["keypoints"][0]
    report = dataset_check.check_dataset(_write(tmp_path, [frame]))
    assert not report.ok
    assert any("顺序不符" in item["error"] for item in report.errors)


def test_dataset_check_flags_image_payload(tmp_path):
    frame = _frame()
    frame["image"] = "data:image/jpeg;base64,AAAA"
    report = dataset_check.check_dataset(_write(tmp_path, [frame]))
    assert not report.ok
    assert any("禁止字段" in item["error"] for item in report.errors)


def test_dataset_check_flags_unknown_label(tmp_path):
    report = dataset_check.check_dataset(_write(tmp_path, [_frame("slouch")]))
    assert not report.ok
    assert any("未知类别" in item["error"] for item in report.errors)


def test_prelabel_policy_covers_four_classes():
    base = {
        "shoulder_tilt_deg": 0.0,
        "shoulder_width": 0.2,
        "shoulder_visibility": 0.98,
        "head_forward_ratio": 0.0,
        "torso_lean_deg": 0.0,
        "visible_ratio": 1.0,
    }
    assert label_policy.prelabel(base) == "baseline"
    assert label_policy.prelabel({**base, "shoulder_tilt_deg": 12.0}) == "lateral_tilt"
    assert label_policy.prelabel({**base, "head_forward_ratio": 0.4}) == "forward_head"
    assert label_policy.prelabel({**base, "shoulder_tilt_deg": 7.0}) == "undetermined"
    assert label_policy.prelabel({**base, "shoulder_visibility": 0.3}) == "undetermined"
    assert set(label_policy.describe()) >= {"version", "tilt_threshold_deg"}
