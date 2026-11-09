"""关键点 → 可解释特征。纯函数，无 IO。"""

from __future__ import annotations

from math import atan2, degrees, hypot

from ..schemas.posture import KEYPOINT_INDEX, Keypoint, PostureFeatures

VISIBILITY_MIN = 0.5


def extract_features(keypoints: list[Keypoint]) -> PostureFeatures:
    """从 33 点中提取与姿态分类相关的几何特征。

    只做可解释的几何量，不做分类决策；分类由云端模型负责。
    """
    points = {point.name.strip().lower(): point for point in keypoints}
    left = points["left_shoulder"]
    right = points["right_shoulder"]
    nose = points["nose"]
    left_hip = points["left_hip"]
    right_hip = points["right_hip"]

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

    shoulder_mid_x = (left.x + right.x) / 2
    shoulder_mid_y = (left.y + right.y) / 2
    hip_mid_x = (left_hip.x + right_hip.x) / 2
    hip_mid_y = (left_hip.y + right_hip.y) / 2
    lean = 0.0
    if hypot(shoulder_mid_x - hip_mid_x, hip_mid_y - shoulder_mid_y) > 0.02:
        lean = round(degrees(atan2(shoulder_mid_x - hip_mid_x, hip_mid_y - shoulder_mid_y)), 2)

    visible = sum(1 for point in keypoints if point.visibility >= VISIBILITY_MIN)
    visible_ratio = round(visible / max(1, len(keypoints)), 3)

    return PostureFeatures(
        shoulder_tilt_deg=tilt,
        shoulder_width=round(width, 4),
        shoulder_visibility=round(shoulder_visibility, 3),
        head_forward_ratio=head_forward,
        torso_lean_deg=lean,
        visible_ratio=visible_ratio,
    )


def keypoint_index(name: str) -> int:
    return KEYPOINT_INDEX[name]
