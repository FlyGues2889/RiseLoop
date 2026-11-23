"""ModelArts 推理包内的纯 Python 运行时（无 torch、无仓库依赖）。

这是 apps/cloud-api 特征逻辑的部署副本：ModelArts 只上传模型目录，不能 import
仓库内模块。副本与真值的差异由 parity 测试拦截，修改时两侧必须同步。
"""

from __future__ import annotations

from math import atan2, degrees, hypot
from typing import Any, Mapping, Sequence

FEATURE_SPEC_VERSION = "v2"
FEATURE_ORDER = (
    "shoulder_tilt_deg",
    "shoulder_width",
    "shoulder_visibility",
    "head_forward_ratio",
    "upper_body_visibility",
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
        return float(point[key])
    except KeyError as exc:
        raise ValueError(f"关键点 {point.get('name')} 缺字段 {key}") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"关键点 {point.get('name')} 的 {key} 不是数值") from exc


def features_from_keypoints(keypoints: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    points = _index(keypoints)
    left, right = points["left_shoulder"], points["right_shoulder"]
    nose = points["nose"]

    width = hypot(_number(right, "x") - _number(left, "x"), _number(right, "y") - _number(left, "y"))
    tilt = 0.0
    if width > 0:
        angle = degrees(atan2(_number(right, "y") - _number(left, "y"), _number(right, "x") - _number(left, "x")))
        if angle > 90:
            angle -= 180
        if angle < -90:
            angle += 180
        tilt = round(angle, 2)

    head_forward = 0.0
    if width > 0:
        shoulder_mid_z = (_number(left, "z") + _number(right, "z")) / 2
        head_forward = round((shoulder_mid_z - _number(nose, "z")) / width, 3)

    visible_upper = sum(
        1
        for name in UPPER_BODY_POINTS
        if _number(points[name], "visibility") >= UPPER_BODY_VISIBILITY_MIN
    )

    return {
        "shoulder_tilt_deg": tilt,
        "shoulder_width": round(width, 4),
        "shoulder_visibility": round(min(_number(left, "visibility"), _number(right, "visibility")), 3),
        "head_forward_ratio": head_forward,
        "upper_body_visibility": round(visible_upper / len(UPPER_BODY_POINTS), 3),
    }


def features_vector(features: Mapping[str, float]) -> list[float]:
    missing = [name for name in FEATURE_ORDER if name not in features]
    if missing:
        raise ValueError(f"特征缺字段：{', '.join(missing)}")
    return [float(features[name]) for name in FEATURE_ORDER]


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

