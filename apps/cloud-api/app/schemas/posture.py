from datetime import datetime
from typing import Literal

from intervention_engine import BodyPart, PostureClass, RedFlag
from intervention_engine.risk import RiskFactor
from pydantic import BaseModel, Field, model_validator

from .sitting import ActionPayload
from ..services.guidelines import GuidelineCitation

# MediaPipe Pose Landmarker 的 33 点顺序；顺序即契约，端侧与服务端必须一致。
MEDIAPIPE_33: tuple[str, ...] = (
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
)

KEYPOINT_INDEX: dict[str, int] = {name: index for index, name in enumerate(MEDIAPIPE_33)}


class Keypoint(BaseModel):
    """单个归一化关键点；坐标 0–1，含可见度，不含像素。"""

    name: str
    x: float = Field(ge=-0.5, le=1.5)
    y: float = Field(ge=-0.5, le=1.5)
    z: float = Field(ge=-2.0, le=2.0)
    visibility: float = Field(ge=0.0, le=1.0)


class PostureFeatures(BaseModel):
    """从关键点派生的可解释特征，同时作为模型输入与响应解释项。"""

    shoulder_tilt_deg: float
    shoulder_width: float
    shoulder_visibility: float
    head_forward_ratio: float
    torso_lean_deg: float
    visible_ratio: float


class PostureContext(BaseModel):
    """端侧与云端共享的久坐/症状上下文。"""

    sitting_minutes: float = Field(default=0.0, ge=0.0)
    daily_sitting_minutes: float = Field(default=0.0, ge=0.0)
    minutes_since_last_break: float = Field(default=0.0, ge=0.0)
    micro_activity_minutes: float = Field(default=0.0, ge=0.0)
    rest_minutes: float = Field(default=0.0, ge=0.0)
    activity_density_2h: float = Field(default=0.0, ge=0.0)

    pain_score: int = Field(default=0, ge=0, le=10)
    fatigue_score: int = Field(default=0, ge=0, le=10)
    body_parts: list[BodyPart] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)

    plan: Literal["quick", "standard", "intense"] = "standard"


class PostureRiskRequest(PostureContext):
    """端侧姿态特征 + 久坐/症状上下文；不包含原始图像。"""

    posture_class: PostureClass
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    deviation_deg: float = Field(default=0.0, ge=0.0, le=90.0)
    posture_duration_minutes: float = Field(default=0.0, ge=0.0)


class PostureRiskResponse(BaseModel):
    brli: float
    risk_level: Literal["low", "medium", "high", "very_high"]
    recommended_plan: Literal["maintain", "quick", "standard", "intense"]
    actions: list[ActionPayload] = Field(default_factory=list)
    factors: list[RiskFactor] = Field(default_factory=list)
    citations: list[GuidelineCitation] = Field(default_factory=list)
    needs_medical_advice: bool = False
    reason: str
    disclaimer: str


class PostureInferRequest(PostureContext):
    """端侧上传 33 个归一化关键点，由云端完成姿态分类；不包含原始画面。"""

    keypoints: list[Keypoint]
    source: Literal["mediapipe-pose-33"] = "mediapipe-pose-33"
    captured_at: datetime | None = None
    posture_duration_minutes: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _validate_keypoints(self) -> "PostureInferRequest":
        names = [point.name.strip().lower() for point in self.keypoints]
        if len(names) != len(MEDIAPIPE_33):
            raise ValueError(f"需要 {len(MEDIAPIPE_33)} 个关键点，实际收到 {len(names)} 个")
        for index, (actual, expected) in enumerate(zip(names, MEDIAPIPE_33)):
            if actual != expected:
                raise ValueError(
                    f"关键点顺序不符：索引 {index} 应为 {expected}，实际为 {actual}"
                )
        return self


class PostureGuidance(BaseModel):
    message: str
    overlay: Literal["baseline_guide", "tilt_guide", "align_guide", "undetermined_guide"]
    disclaimer: str


class PostureInferResponse(BaseModel):
    posture: PostureClass
    confidence: float
    deviation_deg: float
    source: Literal["mock", "huawei"]
    model: str
    latency_ms: float
    recorded: bool = False
    guidance: PostureGuidance
    features: PostureFeatures
    risk: PostureRiskResponse
