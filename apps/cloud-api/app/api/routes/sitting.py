from typing import Literal

from fastapi import APIRouter, HTTPException, status
from intervention_engine import State

from ..deps import SettingsDep, StoreDep, UserIdDep
from ...schemas.sitting import ActionPayload, HeartbeatRequest, HeartbeatResponse
from ...services.heartbeat import handle_heartbeat

router = APIRouter(tags=["sitting"])


@router.post("/sitting/heartbeat", response_model=HeartbeatResponse)
async def sitting_heartbeat(
    payload: HeartbeatRequest, user_id: UserIdDep, store: StoreDep, settings: SettingsDep
) -> HeartbeatResponse:
    return await handle_heartbeat(store, settings, user_id, payload)


@router.get("/actions/{state}", response_model=list[ActionPayload])
async def list_actions(
    state: State,
    store: StoreDep,
    user_id: UserIdDep,
    body_part: Literal["neck", "shoulder", "upper_back", "low_back", "hip", "core"] | None = None,
    max_minutes: int | None = None,
) -> list[ActionPayload]:
    assessment = await store.latest_assessment(user_id)
    parts = [body_part] if body_part else (assessment["body_parts"] if assessment else None)
    actions = await store.list_actions(state.value, parts, max_minutes)
    if not actions:
        actions = await store.list_actions(state.value, None, max_minutes)
    return [
        ActionPayload(
            id=action.id,
            name=action.name,
            duration_minutes=action.duration_minutes,
            intensity=action.intensity,
            body_parts=list(action.body_parts),
            steps=list(action.steps),
            caution=action.caution,
            match_reason="匹配当前状态",
        )
        for action in actions
    ]


@router.post("/ingest/wearable", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def ingest_wearable() -> None:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="not_implemented")