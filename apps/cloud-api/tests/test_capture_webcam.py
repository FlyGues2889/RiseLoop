"""Capture tool tests: contract shape, label-specific self-test poses, pipeline."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import capture_webcam
import collect_frames
import dataset_check
import posture_contract as contract


def _landmarks(x=0.123456, y=-0.2, z=0.987654, visibility=1.5):
    return [
        SimpleNamespace(x=x, y=y, z=z, visibility=visibility)
        for _ in contract.KEYPOINT_ORDER
    ]


def test_normalise_landmarks_rounds_and_clamps():
    points = capture_webcam.normalise_landmarks(_landmarks())

    assert len(points) == 33
    assert points[0] == {
        "name": contract.KEYPOINT_ORDER[0],
        "x": 0.1235,
        "y": -0.2,
        "z": 0.9877,
        "visibility": 1.0,
    }
    assert points[-1]["name"] == contract.KEYPOINT_ORDER[-1]


def test_normalise_landmarks_rejects_wrong_count():
    with pytest.raises(contract.ContractError):
        capture_webcam.normalise_landmarks(_landmarks()[:32])


def test_normalise_landmarks_accepts_off_frame_joints():
    points = capture_webcam.normalise_landmarks(_landmarks(y=2.86, z=-1.4))
    assert points[0]["y"] == 2.86
    assert points[0]["z"] == -1.4


def test_normalise_landmarks_rejects_extreme_values():
    with pytest.raises(contract.ContractError):
        capture_webcam.normalise_landmarks(_landmarks(y=4.4))


def test_collect_skips_out_of_range_row_without_aborting(tmp_path):
    good = capture_webcam.make_record(
        capture_webcam.self_test_pose("baseline"),
        subject="s01",
        device="unit-cam",
        scene="desk",
        label="baseline",
    )
    bad = json.loads(json.dumps(good))
    bad["keypoints"][0]["y"] = 9.0

    raw = tmp_path / "raw.jsonl"
    raw.write_text(
        "\n".join(json.dumps(row) for row in (good, bad)) + "\n", encoding="utf-8"
    )
    frames = tmp_path / "frames.jsonl"

    assert collect_frames.main(["--input", str(raw), "--out", str(frames)]) == 0

    report = dataset_check.check_dataset(frames)
    assert report.ok
    assert report.frames == 1


@pytest.mark.parametrize(
    ("label", "check"),
    [
        ("baseline", lambda f: abs(f["shoulder_tilt_deg"]) < 6 and f["head_forward_ratio"] < 0.2),
        ("forward_head", lambda f: f["head_forward_ratio"] >= 0.3),
        ("lateral_tilt", lambda f: abs(f["shoulder_tilt_deg"]) >= 10),
        ("undetermined", lambda f: f["shoulder_visibility"] < 0.5),
    ],
)
def test_self_test_poses_match_their_label(label, check):
    features = contract.features_from_keypoints(capture_webcam.self_test_pose(label))
    assert check(features)


def test_self_test_to_collect_and_dataset_check(tmp_path):
    raw = tmp_path / "raw.jsonl"
    frames = tmp_path / "frames.jsonl"

    assert (
        capture_webcam.main(
            [
                "--self-test",
                "--out",
                str(raw),
                "--subject",
                "s01",
                "--device",
                "unit-cam",
                "--scene",
                "desk",
                "--label",
                "baseline",
            ]
        )
        == 0
    )
    assert (
        collect_frames.main(["--input", str(raw), "--out", str(frames), "--append"])
        == 0
    )

    report = dataset_check.check_dataset(frames)
    assert report.ok
    assert report.frames == 3
    assert report.origins == {"capture": 3}
    assert report.framings == {"upper_body": 3}
    assert report.labels == {"baseline": 3}
    assert report.subjects == {"s01"}

    first = json.loads(raw.read_text(encoding="utf-8").splitlines()[0])
    assert first["framing"] == "upper_body"
    assert first["label_source"] == "human"
    assert first["origin"] == "capture"
    assert len(first["keypoints"]) == 33
    assert not {"image", "video", "base64", "pixel"} & set(first)


def test_ascii_model_path_keeps_ascii_paths(tmp_path):
    source = tmp_path / "pose.task"
    source.write_bytes(b"abc")
    assert capture_webcam.ascii_model_path(source) == source


def test_ascii_model_path_copies_non_ascii_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_webcam.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    source = tmp_path / "模型" / "pose.task"
    source.parent.mkdir()
    source.write_bytes(b"landmarker")

    target = capture_webcam.ascii_model_path(source)

    assert str(target).isascii()
    assert target.name == "pose.task"
    assert target.read_bytes() == b"landmarker"


def test_make_record_has_no_media_fields():
    record = capture_webcam.make_record(
        capture_webcam.self_test_pose("baseline"),
        subject="s02",
        device="laptop-cam",
        scene="office",
        label="baseline",
        note="unit-test",
    )

    assert set(record) == {
        "ts",
        "device",
        "subject",
        "scene",
        "framing",
        "label",
        "label_source",
        "origin",
        "note",
        "keypoints",
    }
    assert record["framing"] == "upper_body"
    assert record["label_source"] == "human"
    assert record["origin"] == "capture"
    assert len(record["keypoints"]) == 33


def test_make_record_rejects_unknown_framing():
    with pytest.raises(contract.ContractError):
        capture_webcam.make_record(
            capture_webcam.self_test_pose("baseline"),
            subject="s02",
            device="laptop-cam",
            scene="office",
            framing="close_up",
            label="baseline",
        )
