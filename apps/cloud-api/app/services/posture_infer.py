"""姿态推理编排：关键点 → ModelArts → 风险融合 → 摘要落库。

存储分工（遵守架构红线）：
- RDS：姿态摘要事实（类别、置信度、风险等级、BRLI、时长、来源），不存关键点序列；
- DCS：最近一次摘要的实时缓存（TTL 10 分钟），同时用于写入节流，避免每 2 秒写一行事实。

降级口径：ModelArts 不可用时抛 `InferenceUnavailable`，由路由返回 503；
端侧据此显式提示云端不可用并回退到端侧模式，服务端不伪造分类结果。
"""

from __future__ import annotations

import json
import logging
from time import time

from intervention_engine import PostureClass
from intervention_engine.risk import DISCLAIMER

from ..cloud.modelarts import ModelArtsError
from ..cloud.registry import CloudRegistry
from ..repositories.store import Store
from ..schemas.posture import (
    PostureFeatures,
    PostureGuidance,
    PostureInferRequest,
    PostureInferResponse,
    PostureRiskRequest,
)
from .posture import handle_posture_risk
from .posture_features import extract_features

logger = logging.getLogger("riseloop.posture")

GUIDANCE: dict[PostureClass, tuple[str, str]] = {
    PostureClass.BASELINE: ("姿态接近基准线，保持当前坐姿即可。", "baseline_guide"),
    PostureClass.LATERAL_TILT: (
        "肩线有倾斜，调整坐高或重心，让双肩回到水平位置。",
        "tilt_guide",
    ),
    PostureClass.FORWARD_HEAD: (
        "检测到头前伸，收下巴并把屏幕上沿抬到视线高度。",
        "align_guide",
    ),
    PostureClass.UNDETERMINED: (
        "关键点不足（可能被遮挡或光线不足），请正对摄像头坐好。",
        "undetermined_guide",
    ),
}

POSTURE_CACHE_PREFIX = "posture:latest:"
POSTURE_CACHE_TTL_SECONDS = 600
POSTURE_WRITE_INTERVAL_SECONDS = 60

# DCS 不可用时（本地 mock、单机演示）的进程内兜底，只用于写入节流。
_local_latest: dict[str, dict] = {}


class InferenceUnavailable(RuntimeError):
    """模型服务不可用，必须显式降级。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def reset_posture_write_state() -> None:
    """清空进程内缓存；仅测试使用。"""
    _local_latest.clear()


def deviation_for(posture: PostureClass, features: PostureFeatures) -> float:
    """把分类结果折算成 0–90 度的偏差量，供 BRLI 的姿势分量使用。"""
    if posture is PostureClass.LATERAL_TILT:
        return round(min(90.0, abs(features.shoulder_tilt_deg)), 2)
    if posture is PostureClass.FORWARD_HEAD:
        return round(min(90.0, max(0.0, features.head_forward_ratio) * 45), 2)
    return 0.0


def _cache_key(user_id: str) -> str:
    return f"{POSTURE_CACHE_PREFIX}{user_id}"


async def _read_latest(redis, user_id: str) -> dict | None:
    if redis is not None:
        try:
            raw = await redis.get(_cache_key(user_id))
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return _local_latest.get(user_id)


async def _write_latest(redis, user_id: str, latest: dict) -> None:
    _local_latest[user_id] = latest
    if redis is None:
        return
    try:
        await redis.set(
            _cache_key(user_id),
            json.dumps(latest, ensure_ascii=False),
            ttl_seconds=POSTURE_CACHE_TTL_SECONDS,
        )
    except Exception:
        pass


def should_persist(last: dict | None, posture: PostureClass, now: float | None = None) -> bool:
    """姿态类别变化或距上次写入满 60 秒才落一条事实。"""
    if last is None:
        return True
    if last.get("posture") != posture.value:
        return True
    try:
        previous = float(last.get("at", 0.0))
    except (TypeError, ValueError):
        return True
    return (now if now is not None else time()) - previous >= POSTURE_WRITE_INTERVAL_SECONDS


async def handle_posture_infer(
    store: Store,
    user_id: str,
    request: PostureInferRequest,
    cloud: CloudRegistry,
) -> PostureInferResponse:
    features = extract_features(request.keypoints)

    try:
        prediction = await cloud.modelarts.predict(
            keypoints=[point.model_dump() for point in request.keypoints],
            features=features,
        )
    except ModelArtsError as exc:
        raise InferenceUnavailable(exc.reason) from exc

    deviation = deviation_for(prediction.posture, features)
    risk = await handle_posture_risk(
        store,
        user_id,
        PostureRiskRequest(
            posture_class=prediction.posture,
            confidence=prediction.confidence,
            deviation_deg=deviation,
            posture_duration_minutes=request.posture_duration_minutes,
            sitting_minutes=request.sitting_minutes,
            daily_sitting_minutes=request.daily_sitting_minutes,
            minutes_since_last_break=request.minutes_since_last_break,
            micro_activity_minutes=request.micro_activity_minutes,
            rest_minutes=request.rest_minutes,
            activity_density_2h=request.activity_density_2h,
            pain_score=request.pain_score,
            fatigue_score=request.fatigue_score,
            body_parts=request.body_parts,
            red_flags=request.red_flags,
            plan=request.plan,
        ),
    )

    redis = getattr(cloud, "redis", None)
    now = time()
    recorded = False
    last = await _read_latest(redis, user_id)
    if should_persist(last, prediction.posture, now):
        try:
            await store.add_posture_summary(
                user_id,
                {
                    "posture_class": prediction.posture.value,
                    "confidence": prediction.confidence,
                    "deviation_deg": deviation,
                    "risk_level": risk.risk_level,
                    "brli": risk.brli,
                    "duration_minutes": round(request.posture_duration_minutes, 2),
                    "source": prediction.source,
                    "model_name": prediction.model,
                },
            )
            recorded = True
        except Exception as exc:  # 落库失败不阻断实时推理
            logger.warning("posture summary not persisted: %s", type(exc).__name__)

    await _write_latest(
        redis,
        user_id,
        {
            "posture": prediction.posture.value,
            "confidence": prediction.confidence,
            "risk_level": risk.risk_level,
            "brli": risk.brli,
            "source": prediction.source,
            "at": now,
        },
    )

    message, overlay = GUIDANCE[prediction.posture]
    return PostureInferResponse(
        posture=prediction.posture,
        confidence=prediction.confidence,
        deviation_deg=deviation,
        source=prediction.source,
        model=prediction.model,
        latency_ms=prediction.latency_ms,
        recorded=recorded,
        guidance=PostureGuidance(
            message=message,
            overlay=overlay,
            disclaimer=DISCLAIMER,
        ),
        features=features,
        risk=risk,
    )
