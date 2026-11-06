from time import perf_counter
from typing import Any, Literal

import httpx

from ..core.config import Settings
from .base import ServiceStatus

AgentName = Literal["planning", "executing"]


class CodeArtsService:
    name = "codearts"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.codearts_endpoint and self._settings.codearts_api_key)

    def _agent_id(self, agent: AgentName) -> str | None:
        if agent == "planning":
            return self._settings.codearts_planning_agent_id
        return self._settings.codearts_executing_agent_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.codearts_api_key}",
            "Content-Type": "application/json",
        }

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
                provider="huawei-codearts",
                configured=False,
                reachable=None,
                detail="endpoint_or_api_key_not_configured",
            )

        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    self._settings.codearts_endpoint,
                    headers=self._headers(),
                )
            reachable = response.status_code < 500
            return ServiceStatus(
                name=self.name,
                provider="huawei-codearts",
                configured=True,
                reachable=reachable,
                detail=None if reachable else f"http_{response.status_code}",
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        except httpx.HTTPError as exc:
            return ServiceStatus(
                name=self.name,
                provider="huawei-codearts",
                configured=True,
                reachable=False,
                detail=type(exc).__name__,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )

    async def invoke(self, agent: AgentName, payload: dict[str, Any]) -> dict[str, Any]:
        if self._settings.cloud_provider == "mock":
            return {
                "agent": agent,
                "status": "mock",
                "output": {"message": f"{agent} agent mock response", "actions": []},
            }
        if not self.configured:
            raise RuntimeError("CodeArts agent is not configured")

        body = {"agent_id": self._agent_id(agent), "input": payload}
        async with httpx.AsyncClient(
            timeout=self._settings.codearts_timeout_seconds
        ) as client:
            response = await client.post(
                self._settings.codearts_endpoint,
                headers=self._headers(),
                json=body,
            )
            response.raise_for_status()
            return response.json()

    async def close(self) -> None:
        return None