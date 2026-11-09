"""ModelArts 在线推理适配层（mock / huawei 双模式）。

职责边界：
- 只接收 MediaPipe 33 点归一化关键点与派生特征，不接收像素、图像或视频；
- 业务层不得直连 ModelArts endpoint，一律经本适配层；
- mock 模式用确定性几何启发式，仅用于本地联调与录屏，不代表真实模型指标；
- 调用失败一律抛 `ModelArtsError`，由调用方显式降级，禁止伪造云端结果。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from ..core.config import Settings
from ..schemas.posture import PostureFeatures
from .base import ServiceStatus
from intervention_engine import PostureClass

PredictionSource = Literal["mock", "huawei"]

TILT_THRESHOLD_DEG = 8.0
HEAD_FORWARD_THRESHOLD = 0.25


class ModelArtsError(RuntimeError):
    """模型服务不可用；调用方必须显式降级。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PosturePrediction(BaseModel):
    posture: PostureClass
    confidence: float
    model: str
    source: PredictionSource
    latency_ms: float


def mock_predict(features: PostureFeatures) -> tuple[PostureClass, float]:
    """mock 模式的几何启发式：只保证链路可跑，不保证分类质量。"""
    if features.shoulder_visibility < 0.5 or features.shoulder_width <= 0:
        confidence = max(0.0, min(1.0, features.shoulder_visibility))
        return PostureClass.UNDETERMINED, round(confidence, 3)

    if abs(features.shoulder_tilt_deg) >= TILT_THRESHOLD_DEG:
        confidence = min(0.95, 0.6 + abs(features.shoulder_tilt_deg) / 45)
        return PostureClass.LATERAL_TILT, round(confidence, 3)

    if features.head_forward_ratio >= HEAD_FORWARD_THRESHOLD:
        confidence = min(0.95, 0.6 + features.head_forward_ratio)
        return PostureClass.FORWARD_HEAD, round(confidence, 3)

    headroom = max(0.0, HEAD_FORWARD_THRESHOLD - features.head_forward_ratio)
    return PostureClass.BASELINE, round(min(0.97, 0.6 + headroom), 3)


def parse_prediction(payload: Any) -> tuple[PostureClass, float]:
    """兼容三种常见返回：posture 标签、label 标签、probabilities 概率表。"""
    if not isinstance(payload, dict):
        raise ModelArtsError("invalid_response")

    label = payload.get("posture") or payload.get("label") or payload.get("prediction")
    probabilities = payload.get("probabilities")

    if label is None and isinstance(probabilities, dict) and probabilities:
        label = max(probabilities, key=probabilities.get)
        confidence = probabilities[label]
    else:
        confidence = payload.get("confidence", 0.0)

    if label is None:
        raise ModelArtsError("missing_posture_label")

    try:
        posture = PostureClass(str(label))
    except ValueError as exc:
        raise ModelArtsError("unknown_posture_label") from exc

    try:
        score = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ModelArtsError("invalid_confidence") from exc

    return posture, round(max(0.0, min(1.0, score)), 3)


class ModelArtsService:
    name = "modelarts"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.modelarts_endpoint)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = self._settings.modelarts_api_key
        if not key:
            return headers
        header = self._settings.modelarts_auth_header
        if header == "authorization":
            headers["Authorization"] = f"Bearer {key}"
        elif header == "x-api-key":
            headers["X-Api-Key"] = key
        else:
            headers["X-Auth-Token"] = key
        return headers

    async def check(self) -> ServiceStatus:
        if self._settings.cloud_provider == "mock":
            return ServiceStatus(
                name=self.name,
                provider="mock",
                configured=True,
                reachable=True,
                detail="mock provider",
            )
        if not self.configured:
            return ServiceStatus(
                name=self.name,
                provider="huawei-modelarts",
                configured=False,
                reachable=None,
                detail="endpoint_not_configured",
            )
        return ServiceStatus(
            name=self.name,
            provider="huawei-modelarts",
            configured=True,
            reachable=None,
            detail="endpoint_configured",
        )

    async def predict(
        self,
        *,
        keypoints: list[dict[str, float]],
        features: PostureFeatures,
    ) -> PosturePrediction:
        started = perf_counter()
        if self._settings.cloud_provider == "mock":
            posture, confidence = mock_predict(features)
            return PosturePrediction(
                posture=posture,
                confidence=confidence,
                model=f"{self._settings.modelarts_model_name}-mock",
                source="mock",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

        if not self.configured:
            raise ModelArtsError("endpoint_not_configured")

        body = {
            "model": self._settings.modelarts_model_name,
            "source": "mediapipe-pose-33",
            "keypoints": keypoints,
            "features": features.model_dump(),
        }
        if self._settings.modelarts_project_id:
            body["project_id"] = self._settings.modelarts_project_id

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.modelarts_timeout_seconds
            ) as client:
                response = await client.post(
                    self._settings.modelarts_endpoint,
                    headers=self._headers(),
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise ModelArtsError("timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise ModelArtsError(f"http_{exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ModelArtsError(type(exc).__name__) from exc
        except ValueError as exc:
            raise ModelArtsError("invalid_response") from exc

        posture, confidence = parse_prediction(payload)
        return PosturePrediction(
            posture=posture,
            confidence=confidence,
            model=self._settings.modelarts_model_name,
            source="huawei",
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    async def close(self) -> None:
        return None
