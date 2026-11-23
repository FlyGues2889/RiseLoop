"""标注口径（软约束），只用于合成数据生成与人工预标注。

不是服务端契约：模型训练后可以推翻这里的分界。阈值引用 mock 实现的常量，
避免出现第二份 8°/0.25；门控只统计头肩 13 点，髋与腿出画不参与判定。
"""

from __future__ import annotations

from typing import Mapping, Union

import posture_contract
from app.cloud.modelarts import HEAD_FORWARD_THRESHOLD, TILT_THRESHOLD_DEG
from app.schemas.posture import PostureFeatures
from posture_runtime import MIN_MODEL_CONFIDENCE

POLICY_VERSION = "v2"
TILT_GRAY_DEG = 2.0
HEAD_FORWARD_GRAY = 0.05
MIN_SHOULDER_VISIBILITY = 0.5
MIN_UPPER_BODY_VISIBILITY = posture_contract.MIN_UPPER_BODY_VISIBILITY


def prelabel(features: Union[PostureFeatures, Mapping[str, float]]) -> str:
    data = features.model_dump() if isinstance(features, PostureFeatures) else features
    if (
        float(data["shoulder_visibility"]) < MIN_SHOULDER_VISIBILITY
        or float(data["upper_body_visibility"]) < MIN_UPPER_BODY_VISIBILITY
    ):
        return "undetermined"

    tilt = abs(float(data["shoulder_tilt_deg"]))
    head = float(data["head_forward_ratio"])
    tilt_strong = tilt >= TILT_THRESHOLD_DEG + TILT_GRAY_DEG
    tilt_gray = TILT_THRESHOLD_DEG - TILT_GRAY_DEG <= tilt < TILT_THRESHOLD_DEG + TILT_GRAY_DEG
    head_strong = head >= HEAD_FORWARD_THRESHOLD + HEAD_FORWARD_GRAY
    head_gray = (
        HEAD_FORWARD_THRESHOLD - HEAD_FORWARD_GRAY
        <= head
        < HEAD_FORWARD_THRESHOLD + HEAD_FORWARD_GRAY
    )

    if tilt_strong:
        return "lateral_tilt"
    if head_strong:
        return "forward_head"
    if tilt_gray or head_gray:
        return "undetermined"
    return "baseline"


def describe() -> dict[str, float | str]:
    return {
        "version": POLICY_VERSION,
        "tilt_threshold_deg": TILT_THRESHOLD_DEG,
        "tilt_gray_deg": TILT_GRAY_DEG,
        "head_forward_threshold": HEAD_FORWARD_THRESHOLD,
        "head_forward_gray": HEAD_FORWARD_GRAY,
        "min_shoulder_visibility": MIN_SHOULDER_VISIBILITY,
        "min_upper_body_visibility": MIN_UPPER_BODY_VISIBILITY,
        "min_model_confidence": MIN_MODEL_CONFIDENCE,
    }
