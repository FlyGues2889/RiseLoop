"""训练侧契约与云端实现的一致性；合并训练包后必须全绿，不允许 skip。"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

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
        "framing": "upper_body",
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
    assert contract.FRAMINGS == ("upper_body", "full_body")
    assert len(contract.UPPER_BODY_POINTS) == 13
    assert contract.FEATURE_SPEC_VERSION == "v3"
    assert contract.FEATURE_ORDER == (
        "shoulder_tilt_deg",
        "shoulder_width",
        "shoulder_visibility",
        "upper_body_visibility",
        "neck_ratio",
        "head_offset_ratio",
        "neck_ratio_delta",
        "head_offset_delta",
        "tilt_delta_deg",
    )
    assert contract.BASELINE_ORDER == (
        "shoulder_tilt_deg",
        "neck_ratio",
        "head_offset_ratio",
    )


def test_upper_body_only_framing_still_labels():
    keypoints = _pose(random.Random(20261123))
    fixed = {
        "nose": (0.5, 0.18, 0.0),
        "left_shoulder": (0.4, 0.42, 0.0),
        "right_shoulder": (0.6, 0.42, 0.0),
    }
    for point in keypoints:
        if point["name"] in fixed:
            point["x"], point["y"], point["z"] = fixed[point["name"]]
    upper = set(contract.UPPER_BODY_POINTS)
    for point in keypoints:
        point["visibility"] = 0.95 if point["name"] in upper else 0.05
    features = contract.features_from_keypoints(keypoints)
    assert features["upper_body_visibility"] == 1.0
    assert label_policy.prelabel(features) == "baseline"

    for point in keypoints:
        if point["name"] in ("left_shoulder", "right_shoulder"):
            point["visibility"] = 0.1
    hidden = contract.features_from_keypoints(keypoints)
    assert hidden["upper_body_visibility"] < 1.0
    assert label_policy.prelabel(hidden) == "undetermined"


def test_runtime_copy_matches_cloud_features():
    assert runtime.FEATURE_SPEC_VERSION == contract.FEATURE_SPEC_VERSION
    assert runtime.LABELS == contract.LABELS
    rng = random.Random(20261119)
    for _ in range(300):
        keypoints = _pose(rng)
        expected = contract.features_from_keypoints(keypoints)
        actual = runtime.features_from_keypoints(keypoints)
        assert actual == pytest.approx(expected, abs=1e-12)


def test_runtime_copy_matches_cloud_features_with_baseline():
    keypoints = _pose(random.Random(20261126))
    baseline = {"shoulder_tilt_deg": 1.5, "neck_ratio": 0.72, "head_offset_ratio": -0.01}
    expected = contract.features_from_keypoints(keypoints, baseline)
    actual = runtime.features_from_keypoints(keypoints, baseline)
    assert actual == pytest.approx(expected, abs=1e-12)
    assert expected["neck_ratio_delta"] == pytest.approx(
        expected["neck_ratio"] - baseline["neck_ratio"], abs=1e-3
    )


def test_runtime_vector_order_is_schema_order():
    features = _frame()["features"]
    assert runtime.features_vector(features) == contract.features_vector(features)
    assert len(contract.features_vector(features)) == 9
    assert len(contract.coordinates_vector(_frame()["keypoints"])) == 132
    assert runtime.UPPER_BODY_POINTS == contract.UPPER_BODY_POINTS


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

    low = runtime.build_response(
        {"baseline": 0.4, "forward_head": 0.3, "lateral_tilt": 0.2, "undetermined": 0.1}
    )
    assert low["posture"] == "undetermined"
    assert low["confidence"] == pytest.approx(0.4)


def test_decide_posture_is_shared_by_eval_and_serving():
    label, confidence = runtime.decide_posture([0.1, 0.7, 0.1, 0.1])
    assert label == "forward_head"
    assert confidence == pytest.approx(0.7)

    label, confidence = runtime.decide_posture(
        {"baseline": 0.4, "forward_head": 0.3, "lateral_tilt": 0.2, "undetermined": 0.1}
    )
    assert label == "undetermined"
    assert confidence == pytest.approx(0.4)
    assert runtime.MIN_MODEL_CONFIDENCE == 0.5


def test_synthetic_generator_is_stable_across_hash_seeds(tmp_path):
    script = Path(contract.__file__).with_name("generate_synthetic_frames.py")
    outputs = []
    for hash_seed in ("0", "1"):
        out_path = tmp_path / f"frames-{hash_seed}.jsonl"
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        subprocess.run(
            [
                sys.executable,
                str(script),
                "--out",
                str(out_path),
                "--subjects",
                "3",
                "--frames-per-subject",
                "20",
                "--seed",
                "11",
            ],
            check=True,
            capture_output=True,
            env=env,
        )
        outputs.append(out_path.read_bytes())
    assert outputs[0] == outputs[1]


def test_dataset_check_accepts_valid_file(tmp_path):
    report = dataset_check.check_dataset(_write(tmp_path, [_frame(), _frame("lateral_tilt")]))
    assert report.ok, report.errors
    assert report.frames == 2
    assert report.subjects == {"s1"}
    assert report.framings == {"upper_body": 2}


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
        "upper_body_visibility": 1.0,
        "neck_ratio": 0.65,
        "head_offset_ratio": 0.0,
        "neck_ratio_delta": 0.0,
        "head_offset_delta": 0.0,
        "tilt_delta_deg": 0.0,
    }
    assert label_policy.prelabel(base) == "baseline"
    assert label_policy.prelabel({**base, "shoulder_tilt_deg": 12.0}) == "lateral_tilt"
    assert label_policy.prelabel({**base, "neck_ratio_delta": -0.2}) == "forward_head"
    assert label_policy.prelabel({**base, "shoulder_tilt_deg": 7.0}) == "undetermined"
    assert label_policy.prelabel({**base, "shoulder_visibility": 0.3}) == "undetermined"
    assert label_policy.prelabel({**base, "upper_body_visibility": 0.3}) == "undetermined"
    assert label_policy.describe()["version"] == "v3"
