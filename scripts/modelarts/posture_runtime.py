"""ModelArts 推理包内的纯 Python 运行时（无 torch、无仓库依赖）。

这是 apps/cloud-api 特征逻辑的部署副本：ModelArts 只上传模型目录，不能 import
仓库内模块。副本与真值的差异由 parity 测试拦截，修改时两侧必须同步。
"""

from __future__ import annotations

from math import atan2, degrees, hypot, isfinite
from typing import Any, Mapping, Sequence

FEATURE_SPEC_VERSION = "v3"
FEATURE_ORDER = (
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
LABELS = ("baseline", "forward_head", "lateral_tilt", "undetermined")
UPPER_BODY_POINTS = (
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
    "left_shoulder",
    "right_shoulder",
)
UPPER_BODY_VISIBILITY_MIN = 0.5
REQUIRED_POINTS = ("nose", "left_shoulder", "right_shoulder")
MIN_MODEL_CONFIDENCE = 0.5
BASELINE_FIELDS = (
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
)
DEFAULT_BASELINE = {
    "shoulder_tilt_deg": 0.0,
    "neck_ratio": 0.65,
    "head_offset_ratio": 0.0,
    "head_scale": 0.3859,
    "eye_scale": 0.2082,
    "face_height": 0.1059,
    "ear_shoulder_y": 0.7748,
    "head_roll_deg": 1.2305,
    "nose_ear_y": 0.2679,
    "ear_mid_offset": -0.0045,
}
HEAD_GEOMETRY_ORDER = (
    "head_scale",
    "eye_scale",
    "face_height",
    "ear_shoulder_y",
    "head_roll_deg",
    "nose_ear_y",
    "ear_mid_offset",
)
MODEL_FEATURE_ORDER = FEATURE_ORDER + tuple(
    f"{name}_delta" for name in HEAD_GEOMETRY_ORDER
)


def _index(keypoints: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if len(keypoints) != 33:
        raise ValueError(f"需要 33 个关键点，实际 {len(keypoints)} 个")
    points: dict[str, Mapping[str, Any]] = {}
    for point in keypoints:
        try:
            name = str(point["name"]).strip().lower()
        except KeyError as exc:
            raise ValueError("关键点缺 name 字段") from exc
        if name in points:
            raise ValueError(f"关键点重复：{name}")
        points[name] = point
    missing = [name for name in REQUIRED_POINTS if name not in points]
    if missing:
        raise ValueError(f"关键点缺项：{', '.join(missing)}")
    return points


def _number(point: Mapping[str, Any], key: str) -> float:
    try:
        value = float(point[key])
    except KeyError as exc:
        raise ValueError(f"关键点 {point.get('name')} 缺字段 {key}") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"关键点 {point.get('name')} 的 {key} 不是数值") from exc
    if not isfinite(value):
        raise ValueError(f"关键点 {point.get('name')} 的 {key} 不是有限数值")
    return value


def _baseline(raw: Mapping[str, Any] | None) -> dict[str, float]:
    if raw is None:
        return dict(DEFAULT_BASELINE)
    if not isinstance(raw, Mapping):
        raise ValueError("baseline 必须是对象")
    baseline: dict[str, float] = {}
    for name in BASELINE_FIELDS:
        try:
            value = float(raw.get(name, DEFAULT_BASELINE[name]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"baseline {name} 不是数值") from exc
        if not isfinite(value):
            raise ValueError(f"baseline {name} 不是有限数值")
        baseline[name] = value
    return baseline


def _angle(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    angle = degrees(
        atan2(
            _number(right, "y") - _number(left, "y"),
            _number(right, "x") - _number(left, "x"),
        )
    )
    if angle > 90:
        angle -= 180
    if angle < -90:
        angle += 180
    return angle


def _raw_geometry(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    nose: Mapping[str, Any],
) -> tuple[float, float, float, float]:
    width = hypot(
        _number(right, "x") - _number(left, "x"),
        _number(right, "y") - _number(left, "y"),
    )
    tilt = 0.0
    neck_ratio = 0.0
    head_offset_ratio = 0.0
    if width > 0:
        tilt = _angle(left, right)
        shoulder_mid_x = (_number(left, "x") + _number(right, "x")) / 2
        shoulder_mid_y = (_number(left, "y") + _number(right, "y")) / 2
        neck_ratio = (shoulder_mid_y - _number(nose, "y")) / width
        head_offset_ratio = (_number(nose, "x") - shoulder_mid_x) / width
    return tilt, width, neck_ratio, head_offset_ratio


def _head_geometry(
    points: Mapping[str, Mapping[str, Any]], width: float
) -> dict[str, float]:
    if width <= 0:
        return {name: 0.0 for name in HEAD_GEOMETRY_ORDER}

    left_shoulder = points["left_shoulder"]
    right_shoulder = points["right_shoulder"]
    left_ear = points["left_ear"]
    right_ear = points["right_ear"]
    left_eye = points["left_eye"]
    right_eye = points["right_eye"]
    nose = points["nose"]

    ear_width = hypot(
        _number(right_ear, "x") - _number(left_ear, "x"),
        _number(right_ear, "y") - _number(left_ear, "y"),
    )
    ear_mid_x = (_number(left_ear, "x") + _number(right_ear, "x")) / 2
    ear_mid_y = (_number(left_ear, "y") + _number(right_ear, "y")) / 2
    shoulder_mid_x = (_number(left_shoulder, "x") + _number(right_shoulder, "x")) / 2
    shoulder_mid_y = (_number(left_shoulder, "y") + _number(right_shoulder, "y")) / 2

    return {
        "head_scale": ear_width / width,
        "eye_scale": hypot(
            _number(right_eye, "x") - _number(left_eye, "x"),
            _number(right_eye, "y") - _number(left_eye, "y"),
        )
        / width,
        "face_height": hypot(
            _number(nose, "x") - ear_mid_x, _number(nose, "y") - ear_mid_y
        )
        / width,
        "ear_shoulder_y": (shoulder_mid_y - ear_mid_y) / width,
        "head_roll_deg": _angle(left_ear, right_ear) - _angle(left_shoulder, right_shoulder),
        "nose_ear_y": (
            (_number(nose, "y") - ear_mid_y) / ear_width if ear_width >= 1e-3 else 0.0
        ),
        "ear_mid_offset": (ear_mid_x - shoulder_mid_x) / width,
    }


def _rounded_head_geometry(
    points: Mapping[str, Mapping[str, Any]], width: float
) -> dict[str, float]:
    values = _head_geometry(points, width)
    return {
        "head_scale": round(values["head_scale"], 4),
        "eye_scale": round(values["eye_scale"], 4),
        "face_height": round(values["face_height"], 4),
        "ear_shoulder_y": round(values["ear_shoulder_y"], 4),
        "head_roll_deg": round(values["head_roll_deg"], 2),
        "nose_ear_y": round(values["nose_ear_y"], 4),
        "ear_mid_offset": round(values["ear_mid_offset"], 4),
    }


def baseline_from_keypoints(
    keypoints: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    points = _index(keypoints)
    tilt, width, neck_ratio, head_offset_ratio = _raw_geometry(
        points["left_shoulder"], points["right_shoulder"], points["nose"]
    )
    return {
        "shoulder_tilt_deg": round(tilt, 2),
        "neck_ratio": round(neck_ratio, 4),
        "head_offset_ratio": round(head_offset_ratio, 4),
        **_rounded_head_geometry(points, width),
    }


def features_from_keypoints(
    keypoints: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    points = _index(keypoints)
    left, right = points["left_shoulder"], points["right_shoulder"]
    nose = points["nose"]
    reference = _baseline(baseline)

    tilt, width, neck_ratio, head_offset_ratio = _raw_geometry(left, right, nose)

    visible_upper = sum(
        1
        for name in UPPER_BODY_POINTS
        if _number(points[name], "visibility") >= UPPER_BODY_VISIBILITY_MIN
    )

    return {
        "shoulder_tilt_deg": round(tilt, 2),
        "shoulder_width": round(width, 4),
        "shoulder_visibility": round(
            min(_number(left, "visibility"), _number(right, "visibility")), 3
        ),
        "upper_body_visibility": round(visible_upper / len(UPPER_BODY_POINTS), 3),
        "neck_ratio": round(neck_ratio, 3),
        "head_offset_ratio": round(head_offset_ratio, 3),
        "neck_ratio_delta": round(neck_ratio - reference["neck_ratio"], 3),
        "head_offset_delta": round(
            head_offset_ratio - reference["head_offset_ratio"], 3
        ),
        "tilt_delta_deg": round(tilt - reference["shoulder_tilt_deg"], 2),
    }


def features_vector(features: Mapping[str, float]) -> list[float]:
    missing = [name for name in FEATURE_ORDER if name not in features]
    if missing:
        raise ValueError(f"特征缺字段：{', '.join(missing)}")
    return [float(features[name]) for name in FEATURE_ORDER]


def model_features_from_keypoints(
    keypoints: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    points = _index(keypoints)
    reference = _baseline(baseline)
    values = dict(features_from_keypoints(keypoints, baseline))
    _, width, _, _ = _raw_geometry(
        points["left_shoulder"], points["right_shoulder"], points["nose"]
    )
    head = _rounded_head_geometry(points, width)
    for name in HEAD_GEOMETRY_ORDER:
        values[f"{name}_delta"] = round(head[name] - reference[name], 4)
    return values


def model_features_vector(features: Mapping[str, float]) -> list[float]:
    missing = [name for name in MODEL_FEATURE_ORDER if name not in features]
    if missing:
        raise ValueError(f"模型特征缺字段：{', '.join(missing)}")
    return [float(features[name]) for name in MODEL_FEATURE_ORDER]


def build_response(probabilities: Mapping[str, float]) -> dict[str, Any]:
    missing = [label for label in LABELS if label not in probabilities]
    if missing:
        raise ValueError(f"概率缺类别：{', '.join(missing)}")
    scores = {label: float(probabilities[label]) for label in LABELS}
    posture, confidence = decide_posture(scores)
    return {"posture": posture, "confidence": confidence, "probabilities": scores}


def decide_posture(probabilities: Sequence[float] | Mapping[str, float]) -> tuple[str, float]:
    """线上与评估共用的决策规则：argmax，低于阈值改判 undetermined。"""
    if isinstance(probabilities, Mapping):
        scores = {label: float(probabilities[label]) for label in LABELS}
    else:
        values = [float(value) for value in probabilities]
        if len(values) != len(LABELS):
            raise ValueError(f"概率维度应为 {len(LABELS)}，实际 {len(values)}")
        scores = dict(zip(LABELS, values))
    posture = max(LABELS, key=lambda label: scores[label])
    confidence = scores[posture]
    if confidence < MIN_MODEL_CONFIDENCE:
        return "undetermined", confidence
    return posture, confidence
