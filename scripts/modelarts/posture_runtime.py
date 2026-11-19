"""ModelArts 推理包内的纯 Python 运行时（无 torch、无仓库依赖）。

这是 apps/cloud-api 特征逻辑的部署副本：ModelArts 只上传模型目录，不能 import
仓库内模块。副本与真值的差异由 parity 测试拦截，修改时两侧必须同步。
"""

from __future__ import annotations

from math import atan2, degrees, hypot
from typing import Any, Mapping, Sequence

FEATURE_SPEC_VERSION = "v1"
FEATURE_ORDER = (
    "shoulder_tilt_deg",
    "shoulder_width",
    "shoulder_visibility",
    "head_forward_ratio",
    "torso_lean_deg",
    "visible_ratio",
)
LABELS = ("baseline", "forward_head", "lateral_tilt", "undetermined")
VISIBILITY_MIN = 0.5
REQUIRED_POINTS = ("nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip")


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
    left_hip, right_hip = points["left_hip"], points["right_hip"]
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

    shoulder_mid_x = (_number(left, "x") + _number(right, "x")) / 2
    shoulder_mid_y = (_number(left, "y") + _number(right, "y")) / 2
    hip_mid_x = (_number(left_hip, "x") + _number(right_hip, "x")) / 2
    hip_mid_y = (_number(left_hip, "y") + _number(right_hip, "y")) / 2
    lean = 0.0
    if hypot(shoulder_mid_x - hip_mid_x, hip_mid_y - shoulder_mid_y) > 0.02:
        lean = round(degrees(atan2(shoulder_mid_x - hip_mid_x, hip_mid_y - shoulder_mid_y)), 2)

    visible = sum(
        1 for point in keypoints if _number(point, "visibility") >= VISIBILITY_MIN
    )

    return {
        "shoulder_tilt_deg": tilt,
        "shoulder_width": round(width, 4),
        "shoulder_visibility": round(min(_number(left, "visibility"), _number(right, "visibility")), 3),
        "head_forward_ratio": head_forward,
        "torso_lean_deg": lean,
        "visible_ratio": round(visible / max(1, len(keypoints)), 3),
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
    posture = max(scores, key=scores.get)
    return {"posture": posture, "confidence": scores[posture], "probabilities": scores}
