"""关键点 → 可解释特征。纯函数，无 IO。"""

from __future__ import annotations

from math import atan2, degrees, hypot

from ..schemas.posture import (
    KEYPOINT_INDEX,
    UPPER_BODY_NAMES,
    UPPER_BODY_VISIBILITY_MIN,
    Keypoint,
    PostureFeatures,
)


def extract_features(keypoints: list[Keypoint]) -> PostureFeatures:
    """从 33 点中提取与姿态分类相关的几何特征。

    只做可解释的几何量，不做分类决策；分类由云端模型负责。
    特征只依赖鼻与双肩，髋部与腿出画不影响结果。
    """
    points = {point.name.strip().lower(): point for point in keypoints}
    left = points["left_shoulder"]
    right = points["right_shoulder"]
    nose = points["nose"]

    width = hypot(right.x - left.x, right.y - left.y)
    tilt = 0.0
    if width > 0:
        angle = degrees(atan2(right.y - left.y, right.x - left.x))
        if angle > 90:
            angle -= 180
        if angle < -90:
            angle += 180
        tilt = round(angle, 2)

    shoulder_visibility = min(left.visibility, right.visibility)

    head_forward = 0.0
    if width > 0:
        shoulder_mid_z = (left.z + right.z) / 2
        head_forward = round((shoulder_mid_z - nose.z) / width, 3)

    visible_upper = sum(
        1
        for name in UPPER_BODY_NAMES
        if points[name].visibility >= UPPER_BODY_VISIBILITY_MIN
    )
    upper_body_visibility = round(visible_upper / len(UPPER_BODY_NAMES), 3)

    return PostureFeatures(
        shoulder_tilt_deg=tilt,
        shoulder_width=round(width, 4),
        shoulder_visibility=round(shoulder_visibility, 3),
        head_forward_ratio=head_forward,
        upper_body_visibility=upper_body_visibility,
    )


def keypoint_index(name: str) -> int:
    return KEYPOINT_INDEX[name]
