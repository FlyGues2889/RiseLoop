"""MaaS（ModelArts Studio 预置模型服务）适配层。

职责边界：
- 只发问题与已检索到的知识条目，不发健康档案、用户标识或原始日志；
- 只接受 OpenAI 兼容的 `/chat/completions` 响应；
- 未配置、超时、非 2xx、空回复一律抛 `MaaSUnavailable`，由调用方降级到知识库原文，
  禁止把异常包装成一句"生成"的回答。
"""

from __future__ import annotations

import httpx

from ..core.config import Settings, secret_text
from .base import ServiceStatus

SYSTEM_PROMPT = (
    "你是久坐与颈肩不适相关的问答助手。"
    "只能依据用户消息里给出的资料回答；资料里没有的，直接说「资料中没有直接对应的条目」，"
    "不要补充常识、不要推测。"
    "回答不超过 120 字，先给可以马上执行的动作，再给一句原理。"
    "不做诊断，不给用药、康复周期或影像解读建议。"
    "若问题涉及放射痛、麻木加重、眩晕、下肢无力、大小便异常、外伤后剧痛，只提示尽快就医。"
)


class MaaSUnavailable(RuntimeError):
    """预置模型不可用；调用方必须降级到知识库原文。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MaaSClient:
    name = "maas"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.maas_endpoint
            and secret_text(self._settings.maas_api_key)
            and self._settings.maas_model
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret_text(self._settings.maas_api_key) or ''}",
        }

    def _url(self) -> str:
        endpoint = (self._settings.maas_endpoint or "").rstrip("/")
        if endpoint.endswith("/chat/completions"):
            return endpoint
        if endpoint.endswith("/v1"):
            return f"{endpoint}/chat/completions"
        return f"{endpoint}/v1/chat/completions"

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
                provider="huawei-maas",
                configured=False,
                reachable=None,
                detail="endpoint_or_api_key_not_configured",
            )
        return ServiceStatus(
            name=self.name,
            provider="huawei-maas",
            configured=True,
            reachable=None,
            detail="endpoint_configured",
        )

    async def answer(
        self,
        question: str,
        citations: list[dict],
        state_hint: str | None,
    ) -> str:
        if not self.configured:
            raise MaaSUnavailable("not_configured")
        if not citations:
            raise MaaSUnavailable("no_citations")

        knowledge = "\n".join(
            f"[{index + 1}] {item['title']}：{'；'.join(item.get('actions') or [])}。{item.get('summary') or ''}"
            for index, item in enumerate(citations)
        )
        body = {
            "model": self._settings.maas_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"问题：{question}\n当前阶段：{state_hint or '未知'}\n资料：\n{knowledge}",
                },
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.maas_timeout_seconds
            ) as client:
                response = await client.post(self._url(), headers=self._headers(), json=body)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise MaaSUnavailable(type(exc).__name__) from exc
        except ValueError as exc:
            raise MaaSUnavailable("invalid_response") from exc

        choices = payload.get("choices") or []
        if not choices:
            raise MaaSUnavailable("empty_choices")
        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()
        if not text:
            raise MaaSUnavailable("empty_answer")
        return text

    async def close(self) -> None:
        return None
