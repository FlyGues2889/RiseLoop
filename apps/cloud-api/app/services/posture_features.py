"""关键点 → 可解释特征。纯函数，无 IO。"""

from __future__ import annotations

from math import atan2, degrees, hypot

from ..schemas.posture import (
    KEYPOINT_INDEX,
    UPPER_BODY_NAMES,
    UPPER_BODY_VISIBILITY_MIN,
    Keypoint,
    PostureBaseline,
    PostureFeatures,
)


def _raw_geometry(
    left: Keypoint, right: Keypoint, nose: Keypoint
) -> tuple[float, float, float, float]:
    width = hypot(right.x - left.x, right.y - left.y)
    tilt = 0.0
    if width > 0:
        angle = degrees(atan2(right.y - left.y, right.x - left.x))
        if angle > 90:
            angle -= 180
        if angle < -90:
            angle += 180
        tilt = angle

    neck_ratio = 0.0
    head_offset_ratio = 0.0
    if width > 0:
        shoulder_mid_x = (left.x + right.x) / 2
        shoulder_mid_y = (left.y + right.y) / 2
        neck_ratio = (shoulder_mid_y - nose.y) / width
        head_offset_ratio = (nose.x - shoulder_mid_x) / width
    return tilt, width, neck_ratio, head_offset_ratio


def baseline_from_keypoints(keypoints: list[Keypoint]) -> PostureBaseline:
    """从一帧中立坐姿提取基线；批量采集时取多帧中位数。"""

    points = {point.name.strip().lower(): point for point in keypoints}
    tilt, _, neck_ratio, head_offset_ratio = _raw_geometry(
        points["left_shoulder"], points["right_shoulder"], points["nose"]
    )
    return PostureBaseline(
        shoulder_tilt_deg=round(tilt, 2),
        neck_ratio=round(neck_ratio, 4),
        head_offset_ratio=round(head_offset_ratio, 4),
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


def keypoint_index(name: str) -> int:
    return KEYPOINT_INDEX[name]
