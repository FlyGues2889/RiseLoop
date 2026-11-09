"""久坐累积负荷与风险融合（BRLI V1）。

纯函数：不访问数据库、网络或文件。权重与阈值可配置；默认值只是工程初值，
必须经小样本测试与运康专业审核后才能冻结。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import RedFlag

DISCLAIMER = (
    "本产品为健康行为指导工具，不提供医疗诊断或治疗建议。"
    "如出现持续疼痛、放射痛、麻木加重、肢体无力或外伤后剧痛，请及时就医。"
)

POSTURE_EVIDENCE = ("pmid-40111906", "pmid-37775083")
SITTING_EVIDENCE = ("pmid-35147898", "pmid-22374636", "pmid-33054341")
RECOVERY_EVIDENCE = ("pmid-33906239", "pmid-31742666")
SYMPTOM_EVIDENCE = ("pmid-38219373", "pmid-32438853")

class PostureClass(StrEnum):
    BASELINE = "baseline"
    FORWARD_HEAD = "forward_head"
    LATERAL_TILT = "lateral_tilt"
    UNDETERMINED = "undetermined"


class BodyPart(StrEnum):
    NECK = "neck"
    SHOULDER = "shoulder"
    UPPER_BACK = "upper_back"
    LOWER_BACK = "lower_back"
    WRIST = "wrist"
    OTHER = "other"


POSTURE_SEVERITY: dict[PostureClass, float] = {
    PostureClass.BASELINE: 0.0,
    PostureClass.FORWARD_HEAD: 0.55,
    PostureClass.LATERAL_TILT: 0.65,
    PostureClass.UNDETERMINED: 0.0,
}


class RiskInput(BaseModel):
    """单个评估窗口的姿态、久坐、恢复与症状特征。"""

    model_config = ConfigDict(frozen=True)

    posture_class: PostureClass = PostureClass.UNDETERMINED
    posture_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    deviation_deg: float = Field(default=0.0, ge=0.0, le=90.0)
    posture_duration_minutes: float = Field(default=0.0, ge=0.0)

    continuous_sitting_minutes: float = Field(default=0.0, ge=0.0)
    daily_sitting_minutes: float = Field(default=0.0, ge=0.0)
    minutes_since_last_break: float = Field(default=0.0, ge=0.0)

    micro_activity_minutes: float = Field(default=0.0, ge=0.0)
    rest_minutes: float = Field(default=0.0, ge=0.0)
    activity_density_2h: float = Field(default=0.0, ge=0.0)

    pain_score: int = Field(default=0, ge=0, le=10)
    fatigue_score: int = Field(default=0, ge=0, le=10)
    body_parts: tuple[BodyPart, ...] = ()
    red_flags: tuple[RedFlag, ...] = ()

    window_minutes: float = Field(default=1.0, gt=0.0, le=60.0)


class BrliConfig(BaseModel):
    """BRLI 权重与归一化上限；默认值待校准，不是临床阈值。"""

    model_config = ConfigDict(frozen=True)

    alpha: float = Field(default=0.35, ge=0.0, le=1.0)
    beta: float = Field(default=0.35, ge=0.0, le=1.0)
    gamma: float = Field(default=0.10, ge=0.0, le=1.0)
    delta: float = Field(default=0.20, ge=0.0, le=1.0)

    posture_cap_minutes: float = Field(default=30.0, gt=0.0)
    sitting_cap_minutes: float = Field(default=45.0, gt=0.0)
    daily_sitting_cap: float = Field(default=480.0, gt=0.0)
    break_gap_cap_minutes: float = Field(default=60.0, gt=0.0)
    recovery_cap_minutes: float = Field(default=15.0, gt=0.0)
    activity_density_cap: float = Field(default=60.0, gt=0.0)

    low_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    medium_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    high_threshold: float = Field(default=0.75, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _thresholds_are_ordered(self) -> "BrliConfig":
        if not (self.low_threshold < self.medium_threshold < self.high_threshold):
            raise ValueError("阈值必须满足 low < medium < high")
        return self


class RiskFactor(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: Literal["posture", "sitting", "recovery", "symptom"]
    value: float = Field(ge=0.0, le=1.0)
    weight: float
    contribution: float
    evidence_ids: tuple[str, ...] = ()


class BrliOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    brli: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high", "very_high"]
    short_term_risk: float = Field(ge=0.0, le=1.0)
    daily_load: float = Field(ge=0.0)
    window_minutes: float
    factors: tuple[RiskFactor, ...]
    needs_medical_advice: bool
    disclaimer: str = DISCLAIMER


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _ratio(value: float, cap: float) -> float:
    return _clamp01(value / cap) if cap > 0 else 0.0


def posture_component(payload: RiskInput, config: BrliConfig) -> float:
    if payload.posture_class is PostureClass.UNDETERMINED:
        return 0.0
    severity = POSTURE_SEVERITY[payload.posture_class] * payload.posture_confidence
    deviation = _ratio(payload.deviation_deg, 45.0)
    persistence = _ratio(payload.posture_duration_minutes, config.posture_cap_minutes)
    return _clamp01(0.5 * severity + 0.25 * deviation + 0.25 * persistence)


def sitting_component(payload: RiskInput, config: BrliConfig) -> float:
    continuous = _ratio(payload.continuous_sitting_minutes, config.sitting_cap_minutes)
    daily = _ratio(payload.daily_sitting_minutes, config.daily_sitting_cap)
    since_break = _ratio(payload.minutes_since_last_break, config.break_gap_cap_minutes)
    return _clamp01(0.5 * continuous + 0.3 * daily + 0.2 * since_break)


def recovery_component(payload: RiskInput, config: BrliConfig) -> float:
    micro = _ratio(payload.micro_activity_minutes, config.recovery_cap_minutes)
    rest = _ratio(payload.rest_minutes, config.recovery_cap_minutes)
    density = _ratio(payload.activity_density_2h, config.activity_density_cap)
    return _clamp01(0.4 * micro + 0.3 * rest + 0.3 * density)


def symptom_component(payload: RiskInput) -> float:
    if payload.red_flags:
        return 1.0
    pain = payload.pain_score / 10.0
    fatigue = payload.fatigue_score / 10.0
    parts = _clamp01(len(set(payload.body_parts)) / 3.0)
    return _clamp01(0.5 * pain + 0.3 * fatigue + 0.2 * parts)


def risk_level_for(brli: float, config: BrliConfig | None = None) -> Literal["low", "medium", "high", "very_high"]:
    cfg = config or BrliConfig()
    if brli < cfg.low_threshold:
        return "low"
    if brli < cfg.medium_threshold:
        return "medium"
    if brli < cfg.high_threshold:
        return "high"
    return "very_high"


def compute_brli(payload: RiskInput, config: BrliConfig | None = None) -> BrliOutput:
    cfg = config or BrliConfig()
    posture = posture_component(payload, cfg)
    sitting = sitting_component(payload, cfg)
    recovery = recovery_component(payload, cfg)
    symptom = symptom_component(payload)

    brli = _clamp01(
        cfg.alpha * posture
        + cfg.beta * sitting
        - cfg.gamma * recovery
        + cfg.delta * symptom
    )
    level = risk_level_for(brli, cfg)
    needs_medical_advice = bool(payload.red_flags) or (
        level == "very_high" and (payload.pain_score >= 7 or payload.fatigue_score >= 8)
    )

    factors = (
        RiskFactor(
            code="posture",
            value=round(posture, 4),
            weight=cfg.alpha,
            contribution=round(cfg.alpha * posture, 4),
            evidence_ids=POSTURE_EVIDENCE,
        ),
        RiskFactor(
            code="sitting",
            value=round(sitting, 4),
            weight=cfg.beta,
            contribution=round(cfg.beta * sitting, 4),
            evidence_ids=SITTING_EVIDENCE,
        ),
        RiskFactor(
            code="recovery",
            value=round(recovery, 4),
            weight=-cfg.gamma,
            contribution=round(-cfg.gamma * recovery, 4),
            evidence_ids=RECOVERY_EVIDENCE,
        ),
        RiskFactor(
            code="symptom",
            value=round(symptom, 4),
            weight=cfg.delta,
            contribution=round(cfg.delta * symptom, 4),
            evidence_ids=SYMPTOM_EVIDENCE,
        ),
    )

    return BrliOutput(
        brli=round(brli, 4),
        risk_level=level,
        short_term_risk=round(brli, 4),
        daily_load=round(brli * payload.window_minutes, 4),
        window_minutes=payload.window_minutes,
        factors=factors,
        needs_medical_advice=needs_medical_advice,
    )


def cumulative_load(values: Sequence[float], interval_minutes: float = 1.0) -> float:
    """按窗口累加当日负荷：Σ BRLI · Δt。"""
    if interval_minutes <= 0:
        raise ValueError("interval_minutes 必须为正数")
    return round(sum(max(0.0, min(1.0, value)) * interval_minutes for value in values), 4)


def short_term_risk(values: Sequence[float], window: int = 30) -> float:
    """近窗简单平均；window 为纳入的最近窗口数。"""
    if window <= 0:
        raise ValueError("window 必须为正整数")
    recent = list(values)[-window:]
    if not recent:
        return 0.0
    return round(sum(max(0.0, min(1.0, value)) for value in recent) / len(recent), 4)
