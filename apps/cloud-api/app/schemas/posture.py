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

# 久坐机位只看得到头肩：鼻、眼、耳、嘴共 11 点，加双肩 2 点。
# 可见比例只按这 13 点统计，髋与腿出画不再拖垮门控。
UPPER_BODY_NAMES: tuple[str, ...] = MEDIAPIPE_33[:13]
UPPER_BODY_VISIBILITY_MIN = 0.5


class Keypoint(BaseModel):
    """单个归一化关键点；坐标系 0–1，含可见度，不含像素。

    MediaPipe 对画面外的关节会给外推坐标，坐着时腿部常到 y≈2.8，
    因此边界留到 [-2, 4]；超出即视为异常帧。
    """

    name: str
    x: float = Field(ge=-2.0, le=4.0)
    y: float = Field(ge=-2.0, le=4.0)
    z: float = Field(ge=-4.0, le=4.0)
    visibility: float = Field(ge=0.0, le=1.0)


class PostureBaseline(BaseModel):
    """同一受试者的中立坐姿参考值；缺省值只作无校准时的兜底。"""

    shoulder_tilt_deg: float = Field(default=0.0, ge=-90.0, le=90.0)
    neck_ratio: float = Field(default=0.65, ge=-6.0, le=6.0)
    head_offset_ratio: float = Field(default=0.0, ge=-6.0, le=6.0)
    # 头部几何量：模型内部使用，不进公开 PostureFeatures 契约。
    head_scale: float = Field(default=0.3859, ge=-100.0, le=100.0)
    eye_scale: float = Field(default=0.2082, ge=-100.0, le=100.0)
    face_height: float = Field(default=0.1059, ge=-100.0, le=100.0)
    ear_shoulder_y: float = Field(default=0.7748, ge=-100.0, le=100.0)
    head_roll_deg: float = Field(default=1.2305, ge=-180.0, le=180.0)
    nose_ear_y: float = Field(default=0.2679, ge=-100.0, le=100.0)
    ear_mid_offset: float = Field(default=-0.0045, ge=-100.0, le=100.0)


class PostureFeatures(BaseModel):
    """从关键点派生的 2D 可解释特征；相对量需要 `PostureBaseline`。"""

    shoulder_tilt_deg: float
    shoulder_width: float
    shoulder_visibility: float
    upper_body_visibility: float
    neck_ratio: float
    head_offset_ratio: float
    neck_ratio_delta: float
    head_offset_delta: float
    tilt_delta_deg: float


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
    baseline: PostureBaseline | None = None
    source: Literal["mediapipe-pose-33"] = "mediapipe-pose-33"
    captured_at: datetime | None = None
    posture_duration_minutes: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _validate_keypoints(self) -> "PostureInferRequest":
        _validate_keypoint_sequence(self.keypoints)
        return self


def _validate_keypoint_sequence(keypoints: list[Keypoint]) -> None:
    names = [point.name.strip().lower() for point in keypoints]
    if len(names) != len(MEDIAPIPE_33):
        raise ValueError(f"需要 {len(MEDIAPIPE_33)} 个关键点，实际收到 {len(names)} 个")
    for index, (actual, expected) in enumerate(zip(names, MEDIAPIPE_33)):
        if actual != expected:
            raise ValueError(
                f"关键点顺序不符：索引 {index} 应为 {expected}，实际为 {actual}"
            )


class PostureBaselineRequest(BaseModel):
    """10 秒中立位校准：多帧 33 点，服务端取逐字段中位数。"""

    frames: list[list[Keypoint]] = Field(min_length=3, max_length=120)

    @model_validator(mode="after")
    def _validate_frames(self) -> "PostureBaselineRequest":
        for index, frame in enumerate(self.frames):
            try:
                _validate_keypoint_sequence(frame)
            except ValueError as exc:
                raise ValueError(f"第 {index + 1} 帧：{exc}") from exc
        return self


class PostureBaselineResponse(BaseModel):
    baseline: PostureBaseline
    frames: int


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
