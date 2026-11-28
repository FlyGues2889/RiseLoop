"""关键点 → 可解释特征。纯函数，无 IO。"""

from __future__ import annotations

from math import atan2, degrees, hypot
from statistics import median

from ..schemas.posture import (
    KEYPOINT_INDEX,
    UPPER_BODY_NAMES,
    UPPER_BODY_VISIBILITY_MIN,
    Keypoint,
    PostureBaseline,
    PostureFeatures,
)

HEAD_GEOMETRY_ORDER = (
    "head_scale",
    "eye_scale",
    "face_height",
    "ear_shoulder_y",
    "head_roll_deg",
    "nose_ear_y",
    "ear_mid_offset",
)
MODEL_FEATURE_ORDER = tuple(PostureFeatures.model_fields) + tuple(
    f"{name}_delta" for name in HEAD_GEOMETRY_ORDER
)


def _angle(left: Keypoint, right: Keypoint) -> float:
    angle = degrees(atan2(right.y - left.y, right.x - left.x))
    if angle > 90:
        angle -= 180
    if angle < -90:
        angle += 180
    return angle


def _raw_geometry(
    left: Keypoint, right: Keypoint, nose: Keypoint
) -> tuple[float, float, float, float]:
    width = hypot(right.x - left.x, right.y - left.y)
    tilt = 0.0
    neck_ratio = 0.0
    head_offset_ratio = 0.0
    if width > 0:
        tilt = _angle(left, right)
        shoulder_mid_x = (left.x + right.x) / 2
        shoulder_mid_y = (left.y + right.y) / 2
        neck_ratio = (shoulder_mid_y - nose.y) / width
        head_offset_ratio = (nose.x - shoulder_mid_x) / width
    return tilt, width, neck_ratio, head_offset_ratio


def _head_geometry(
    points: dict[str, Keypoint], width: float
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

    ear_width = hypot(right_ear.x - left_ear.x, right_ear.y - left_ear.y)
    ear_mid_x = (left_ear.x + right_ear.x) / 2
    ear_mid_y = (left_ear.y + right_ear.y) / 2
    shoulder_mid_x = (left_shoulder.x + right_shoulder.x) / 2
    shoulder_mid_y = (left_shoulder.y + right_shoulder.y) / 2

    return {
        "head_scale": ear_width / width,
        "eye_scale": hypot(right_eye.x - left_eye.x, right_eye.y - left_eye.y) / width,
        "face_height": hypot(nose.x - ear_mid_x, nose.y - ear_mid_y) / width,
        "ear_shoulder_y": (shoulder_mid_y - ear_mid_y) / width,
        "head_roll_deg": _angle(left_ear, right_ear) - _angle(left_shoulder, right_shoulder),
        "nose_ear_y": (
            (nose.y - ear_mid_y) / ear_width if ear_width >= 1e-3 else 0.0
        ),
        "ear_mid_offset": (ear_mid_x - shoulder_mid_x) / width,
    }


def _rounded_head_geometry(points: dict[str, Keypoint], width: float) -> dict[str, float]:
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


def baseline_from_keypoints(keypoints: list[Keypoint]) -> PostureBaseline:
    """从一帧中立坐姿提取基线；批量采集时取多帧中位数。"""

    points = {point.name.strip().lower(): point for point in keypoints}
    tilt, width, neck_ratio, head_offset_ratio = _raw_geometry(
        points["left_shoulder"], points["right_shoulder"], points["nose"]
    )
    return PostureBaseline(
        shoulder_tilt_deg=round(tilt, 2),
        neck_ratio=round(neck_ratio, 4),
        head_offset_ratio=round(head_offset_ratio, 4),
        **_rounded_head_geometry(points, width),
    )


def baseline_from_frames(frames: list[list[Keypoint]]) -> PostureBaseline:
    """多帧中立位的中位数；单帧抖动不改变个人基线。"""

    samples = [baseline_from_keypoints(frame) for frame in frames]
    angles = {"shoulder_tilt_deg", "head_roll_deg"}
    return PostureBaseline(
        **{
            name: round(
                median(getattr(sample, name) for sample in samples),
                2 if name in angles else 4,
            )
            for name in PostureBaseline.model_fields
        }
    )


def extract_features(
    keypoints: list[Keypoint], baseline: PostureBaseline | None = None
) -> PostureFeatures:
    """提取 2D 几何特征与相对个人中立位的偏差。

    只做可解释的几何量，不做分类决策；分类由云端模型负责。
    不使用 MediaPipe 的 z：真实摄像头上该通道的尺度随距离漂移，无法
    稳定区分头前伸。相对量在没有校准数据时回退到总体中立位。
    """

    points = {point.name.strip().lower(): point for point in keypoints}
    left = points["left_shoulder"]
    right = points["right_shoulder"]
    nose = points["nose"]
    reference = baseline or PostureBaseline()

    tilt, width, neck_ratio, head_offset_ratio = _raw_geometry(left, right, nose)

    shoulder_visibility = min(left.visibility, right.visibility)

    visible_upper = sum(
        1
        for name in UPPER_BODY_NAMES
        if points[name].visibility >= UPPER_BODY_VISIBILITY_MIN
    )
    upper_body_visibility = round(visible_upper / len(UPPER_BODY_NAMES), 3)

    return PostureFeatures(
        shoulder_tilt_deg=round(tilt, 2),
        shoulder_width=round(width, 4),
        shoulder_visibility=round(shoulder_visibility, 3),
        upper_body_visibility=upper_body_visibility,
        neck_ratio=round(neck_ratio, 3),
        head_offset_ratio=round(head_offset_ratio, 3),
        neck_ratio_delta=round(neck_ratio - reference.neck_ratio, 3),
        head_offset_delta=round(head_offset_ratio - reference.head_offset_ratio, 3),
        tilt_delta_deg=round(tilt - reference.shoulder_tilt_deg, 2),
    )


def model_features_from_keypoints(
    keypoints: list[Keypoint], baseline: PostureBaseline | None = None
) -> dict[str, float]:
    """模型输入：公开 9 特征 + 7 个头部几何量相对个人基线的偏差。"""

    points = {point.name.strip().lower(): point for point in keypoints}
    reference = baseline or PostureBaseline()
    features = extract_features(keypoints, reference)
    _, width, _, _ = _raw_geometry(
        points["left_shoulder"], points["right_shoulder"], points["nose"]
    )
    head = _rounded_head_geometry(points, width)

    values = features.model_dump()
    for name in HEAD_GEOMETRY_ORDER:
        values[f"{name}_delta"] = round(head[name] - getattr(reference, name), 4)
    return values


def keypoint_index(name: str) -> int:
    return KEYPOINT_INDEX[name]
