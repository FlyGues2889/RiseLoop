"""Generate deterministic synthetic MediaPipe-33 frames.

Why this exists
---------------
The repository had no captured posture frames when this package was built, and
the task forbids recording images.  This generator produces *keypoint-only*
synthetic frames so the full pipeline (contract -> features -> labels -> split
-> training -> evaluation -> serving) can be exercised and reviewed.

Rules:
* every frame is ``origin="synthetic"`` and ``label_source="prelabel"``;
* labels are produced by :func:`label_policy.prelabel`, the same rubric that
  would be used as a human annotation guideline;
* these numbers are **not** delivery accuracy and must never be presented as
  real-capture metrics.

The geometry is intentionally varied across subjects: body scale, camera yaw
(side cameras), image position, baseline head-forward/tilt offsets, visibility
profiles, desk/hair occlusions and transition frames.

The target setting is a seated laptop camera: only the head and both shoulders
are in frame.  Frames therefore default to ``framing="upper_body"``; hip and
leg landmarks sit outside the image with low visibility, matching what
MediaPipe emits when the lower body is not visible.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from label_policy import prelabel
from posture_contract import (
    KEYPOINT_ORDER as MEDIAPIPE_33,
    LABELS as LABEL_ORDER,
    features_from_keypoints as compute_features,
)

DEVICES = (
    "demo-laptop-cam0",
    "usb-cam-1080p",
    "phone-front-cam",
    "laptop-cam-side",
)
FRAMING = "upper_body"
SCENES = (
    "office-chair-desk",
    "home-sofa",
    "library-desk",
    "meeting-room",
    "standing-desk",
)

FACE = {
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
}
UPPER = {
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
}
LOWER = {
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
}

PREFIX = {"left": "left_", "right": "right_"}


def _rotate(dx: float, dy: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    cos_value = math.cos(radians)
    sin_value = math.sin(radians)
    return dx * cos_value - dy * sin_value, dx * sin_value + dy * cos_value


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _point(
    name: str,
    x: float,
    y: float,
    z: float,
    visibility: float,
    *,
    clamp: bool = True,
) -> dict[str, Any]:
    if clamp:
        x = _clip(x, -0.04, 1.04)
        y = _clip(y, -0.04, 1.04)
    return {
        "name": name,
        "x": round(x, 6),
        "y": round(y, 6),
        "z": round(_clip(z, -2.0, 2.0), 6),
        "visibility": round(_clip(visibility, 0.0, 1.0), 6),
    }


def build_pose(
    *,
    rng: random.Random,
    profile: dict[str, Any],
    tilt_deg: float,
    head_forward_ratio: float,
    lean_deg: float,
    occlusion: str | None = None,
    framing: str = "upper_body",
) -> list[dict[str, Any]]:
    """Build one canonical 33-landmark frame in image coordinates."""

    scale = profile["body_scale"]
    yaw = math.radians(profile["yaw_deg"])
    cx = profile["cx"]
    hip_y = profile["hip_y"]
    zoom = profile["zoom"]

    torso_len = 0.31 * scale
    shoulder_y = hip_y - torso_len
    shoulder_mid_x = cx + math.tan(math.radians(lean_deg)) * torso_len

    shoulder_width = 0.20 * scale
    hip_width = 0.13 * scale

    raw: dict[str, tuple[float, float, float]] = {}

    # Hips and legs.
    raw["left_hip"] = (cx + hip_width / 2.0, hip_y, 0.0)
    raw["right_hip"] = (cx - hip_width / 2.0, hip_y, 0.0)
    raw["left_knee"] = (cx + hip_width * 0.45, hip_y + 0.20 * scale, 0.035)
    raw["right_knee"] = (cx - hip_width * 0.45, hip_y + 0.20 * scale, 0.035)
    raw["left_ankle"] = (cx + hip_width * 0.35, hip_y + 0.38 * scale, 0.075)
    raw["right_ankle"] = (cx - hip_width * 0.35, hip_y + 0.38 * scale, 0.075)
    raw["left_heel"] = (cx + hip_width * 0.35, hip_y + 0.40 * scale, 0.09)
    raw["right_heel"] = (cx - hip_width * 0.35, hip_y + 0.40 * scale, 0.09)
    raw["left_foot_index"] = (cx + hip_width * 0.42, hip_y + 0.42 * scale, 0.10)
    raw["right_foot_index"] = (cx - hip_width * 0.42, hip_y + 0.42 * scale, 0.10)

    # Shoulders, rotated around the shoulder midpoint by the target tilt.
    shoulders = {
        "left_shoulder": (shoulder_width / 2.0, 0.0),
        "right_shoulder": (-shoulder_width / 2.0, 0.0),
    }
    for name, (offset_x, offset_y) in shoulders.items():
        rotated_x, rotated_y = _rotate(offset_x, offset_y, tilt_deg)
        raw[name] = (
            shoulder_mid_x + rotated_x,
            shoulder_y + rotated_y,
            0.0,
        )

    # Arms: offsets follow the shoulder tilt.
    arm_offsets = {
        "left_elbow": (0.045, 0.14),
        "right_elbow": (-0.045, 0.14),
        "left_wrist": (0.020, 0.27),
        "right_wrist": (-0.020, 0.27),
    }
    for name, (offset_x, offset_y) in arm_offsets.items():
        side = "left" if name.startswith("left") else "right"
        sx, sy, _ = raw[f"{side}_shoulder"]
        rotated_x, rotated_y = _rotate(offset_x * scale, offset_y * scale, tilt_deg)
        raw[name] = (sx + rotated_x, sy + rotated_y, 0.03 if "elbow" in name else -0.04)

    hand_offsets = {
        "left_pinky": (0.035, 0.305),
        "left_index": (0.005, 0.315),
        "left_thumb": (0.050, 0.295),
        "right_pinky": (-0.035, 0.305),
        "right_index": (-0.005, 0.315),
        "right_thumb": (-0.050, 0.295),
    }
    for name, (offset_x, offset_y) in hand_offsets.items():
        side = "left" if name.startswith("left") else "right"
        sx, sy, _ = raw[f"{side}_shoulder"]
        rotated_x, rotated_y = _rotate(offset_x * scale, offset_y * scale, tilt_deg)
        raw[name] = (sx + rotated_x, sy + rotated_y, -0.06)

    # Head: centred over the shoulder midpoint.  Head-forward is depth-only.
    head_y = shoulder_y - 0.105 * scale
    nose_z = -head_forward_ratio * shoulder_width
    raw["nose"] = (shoulder_mid_x, head_y, nose_z)
    face_offsets = {
        "left_eye_inner": (-0.011, -0.013, -0.008),
        "left_eye": (-0.021, -0.014, -0.010),
        "left_eye_outer": (-0.031, -0.012, -0.008),
        "right_eye_inner": (0.011, -0.013, -0.008),
        "right_eye": (0.021, -0.014, -0.010),
        "right_eye_outer": (0.031, -0.012, -0.008),
        "left_ear": (-0.045, -0.004, 0.005),
        "right_ear": (0.045, -0.004, 0.005),
        "mouth_left": (-0.014, 0.020, -0.006),
        "mouth_right": (0.014, 0.020, -0.006),
    }
    for name, (offset_x, offset_y, offset_z) in face_offsets.items():
        raw[name] = (
            shoulder_mid_x + offset_x * scale,
            head_y + offset_y * scale,
            nose_z + offset_z * scale,
        )

    # Laptop framing: hips and legs fall below the image.  MediaPipe still
    # returns extrapolated coordinates for them; keep them off-frame instead of
    # clamping to the bottom edge.
    if framing == "upper_body":
        for name in LOWER:
            x, y, z = raw[name]
            raw[name] = (x, y + 0.55 * scale, z)

    # Visibility profile before occlusion.
    visibility: dict[str, float] = {}
    for name in MEDIAPIPE_33:
        if name in FACE:
            base = 0.975
        elif name in ("left_shoulder", "right_shoulder"):
            base = 0.97
        elif name in UPPER:
            base = 0.90
        elif name in ("left_hip", "right_hip"):
            base = 0.94 if framing == "full_body" else rng.uniform(0.03, 0.22)
        elif name in LOWER:
            base = 0.84 if framing == "full_body" else rng.uniform(0.02, 0.18)
        else:
            base = 0.90
        visibility[name] = _clip(base + rng.gauss(0.0, 0.012), 0.0, 1.0)

    if occlusion == "shoulder":
        for name in ("left_shoulder", "right_shoulder"):
            visibility[name] = rng.uniform(0.20, 0.46)
        for name in ("left_elbow", "right_elbow", "left_wrist", "right_wrist"):
            visibility[name] = rng.uniform(0.25, 0.55)
    elif occlusion == "desk":
        for name in MEDIAPIPE_33:
            if name in LOWER or name in ("left_hip", "right_hip"):
                visibility[name] = rng.uniform(0.12, 0.45)
        for name in ("left_wrist", "right_wrist", "left_pinky", "right_pinky",
                     "left_index", "right_index", "left_thumb", "right_thumb"):
            visibility[name] = rng.uniform(0.20, 0.50)
    elif occlusion == "hair":
        for name in ("left_ear", "right_ear", "left_eye", "right_eye",
                     "left_eye_outer", "right_eye_outer"):
            visibility[name] = rng.uniform(0.20, 0.46)
    elif occlusion == "low_light":
        factor = rng.uniform(0.32, 0.55)
        for name in MEDIAPIPE_33:
            visibility[name] = _clip(visibility[name] * factor, 0.0, 1.0)

    # Random small dropouts (real detectors are not perfectly stable).
    for name in rng.sample(MEDIAPIPE_33, k=rng.randint(0, 2)):
        visibility[name] = rng.uniform(0.20, 0.45)

    # Project to a yawed camera, zoom, then add landmark noise.
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    xy_sigma = profile["xy_sigma"]
    z_sigma = profile["z_sigma"]

    points: list[dict[str, Any]] = []
    for name in MEDIAPIPE_33:
        x, y, z = raw[name]
        dx = x - cx
        projected_x = cx + dx * cos_yaw + z * sin_yaw
        projected_z = -dx * sin_yaw + z * cos_yaw
        projected_x = 0.5 + (projected_x - 0.5) * zoom
        projected_y = 0.5 + (y - 0.5) * zoom
        projected_x += rng.gauss(0.0, xy_sigma)
        projected_y += rng.gauss(0.0, xy_sigma)
        projected_z += rng.gauss(0.0, z_sigma)
        clamp = not (framing == "upper_body" and name in LOWER)
        points.append(
            _point(name, projected_x, projected_y, projected_z, visibility[name], clamp=clamp)
        )
    return points


def _scenario_params(kind: str, rng: random.Random, profile: dict[str, Any]) -> dict[str, float]:
    base_tilt = profile["tilt_offset"]
    base_ratio = profile["ratio_offset"]
    sign = 1.0 if rng.random() < 0.5 else -1.0

    if kind == "baseline":
        return {
            "tilt": base_tilt + rng.gauss(0.0, 2.0),
            "ratio": _clip(base_ratio + rng.gauss(0.0, 0.035), 0.0, 0.20),
            "lean": rng.gauss(0.0, 2.0),
            "occlusion": None,
        }
    if kind == "forward":
        return {
            "tilt": base_tilt + rng.gauss(0.0, 1.6),
            "ratio": 0.30 + rng.uniform(0.0, 0.24),
            "lean": rng.gauss(0.0, 2.0),
            "occlusion": None,
        }
    if kind == "lateral":
        return {
            "tilt": sign * rng.uniform(10.0, 24.0),
            "ratio": _clip(base_ratio + rng.gauss(0.0, 0.045), -0.05, 0.22),
            "lean": sign * rng.uniform(3.0, 9.0),
            "occlusion": None,
        }
    if kind == "mixed":
        return {
            "tilt": sign * rng.uniform(9.0, 20.0),
            "ratio": 0.30 + rng.uniform(0.0, 0.20),
            "lean": sign * rng.uniform(2.0, 8.0),
            "occlusion": None,
        }
    if kind == "grey":
        return {
            "tilt": sign * rng.uniform(6.2, 9.8),
            "ratio": rng.uniform(0.205, 0.295),
            "lean": rng.gauss(0.0, 3.0),
            "occlusion": None,
        }
    if kind == "near":
        return {
            "tilt": sign * rng.uniform(6.5, 10.5),
            "ratio": rng.uniform(0.17, 0.24),
            "lean": sign * rng.uniform(0.0, 4.0),
            "occlusion": None,
        }
    if kind in ("occluded_shoulder", "occluded_desk", "occluded_hair", "low_light"):
        base = _scenario_params(rng.choice(["baseline", "forward"]), rng, profile)
        base["occlusion"] = {
            "occluded_shoulder": "shoulder",
            "occluded_desk": "desk",
            "occluded_hair": "hair",
            "low_light": "low_light",
        }[kind]
        return base
    if kind == "transition":
        start = _scenario_params(rng.choice(["baseline", "forward"]), rng, profile)
        target = _scenario_params(rng.choice(["forward", "lateral", "mixed"]), rng, profile)
        t = rng.uniform(0.15, 0.85)
        return {
            "tilt": start["tilt"] * (1 - t) + target["tilt"] * t,
            "ratio": start["ratio"] * (1 - t) + target["ratio"] * t,
            "lean": start["lean"] * (1 - t) + target["lean"] * t,
            "occlusion": None,
        }
    raise ValueError(f"unknown scenario {kind!r}")


SCENARIO_KINDS = (
    "baseline",
    "forward",
    "lateral",
    "mixed",
    "grey",
    "near",
    "occluded_shoulder",
    "occluded_desk",
    "occluded_hair",
    "low_light",
    "transition",
)
SCENARIO_WEIGHTS = (0.26, 0.19, 0.15, 0.06, 0.08, 0.05, 0.04, 0.035, 0.025, 0.02, 0.065)


def generate(
    *,
    subjects: int,
    frames_per_subject: int,
    seed: int,
    out_path: Path,
) -> dict[str, Any]:
    master = random.Random(seed)
    rows: list[dict[str, Any]] = []
    start = datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)))

    for subject_index in range(subjects):
        subject_rng = random.Random(master.randrange(2**31))
        subject = f"s{subject_index + 1:02d}"
        device = DEVICES[subject_index % len(DEVICES)]
        scene = SCENES[subject_index % len(SCENES)]
        profile = {
            "body_scale": subject_rng.uniform(0.86, 1.14),
            "yaw_deg": subject_rng.choice(
                [subject_rng.uniform(-12.0, 12.0), subject_rng.uniform(22.0, 42.0),
                 subject_rng.uniform(-42.0, -22.0)]
            ),
            "cx": subject_rng.uniform(0.45, 0.55),
            "hip_y": subject_rng.uniform(0.57, 0.65),
            "zoom": subject_rng.uniform(0.92, 1.08),
            "tilt_offset": subject_rng.gauss(0.0, 1.2),
            "ratio_offset": max(0.0, subject_rng.gauss(0.12, 0.025)),
            "xy_sigma": subject_rng.uniform(0.0025, 0.0045),
            "z_sigma": subject_rng.uniform(0.006, 0.012),
        }

        for frame_index in range(frames_per_subject):
            kind = subject_rng.choices(SCENARIO_KINDS, weights=SCENARIO_WEIGHTS, k=1)[0]
            params = _scenario_params(kind, subject_rng, profile)
            points = build_pose(
                rng=subject_rng,
                profile=profile,
                tilt_deg=params["tilt"],
                head_forward_ratio=params["ratio"],
                lean_deg=params["lean"],
                occlusion=params["occlusion"],
                framing=FRAMING,
            )
            features = compute_features(points)
            label = prelabel(features)
            timestamp = start + timedelta(
                days=subject_index, minutes=frame_index, seconds=subject_index
            )
            rows.append(
                {
                    "frame_id": f"{subject}-{frame_index:06d}",
                    "ts": timestamp.isoformat(timespec="seconds"),
                    "device": device,
                    "subject": subject,
                    "scene": scene,
                    "framing": FRAMING,
                    "keypoints": points,
                    "features": {name: round(value, 6) for name, value in features.items()},
                    "label": label,
                    "label_source": "prelabel",
                    "origin": "synthetic",
                    "note": f"synthetic_rubric:{kind}",
                }
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    counts = {label: 0 for label in LABEL_ORDER}
    for row in rows:
        counts[row["label"]] += 1
    return {
        "path": str(out_path),
        "frames": len(rows),
        "subjects": subjects,
        "frames_per_subject": frames_per_subject,
        "seed": seed,
        "label_counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--subjects", type=int, default=12)
    parser.add_argument("--frames-per-subject", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20261117)
    args = parser.parse_args()

    summary = generate(
        subjects=args.subjects,
        frames_per_subject=args.frames_per_subject,
        seed=args.seed,
        out_path=args.out,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
