from fastapi import APIRouter, HTTPException, status

from ..deps import StoreDep, UserIdDep
from ...schemas.intervention import FeedbackRequest, FeedbackResponse
from ...schemas.sitting import ActionPayload
from ...services.feedback import handle_feedback

router = APIRouter(tags=["intervention"])


@router.post("/intervention/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    payload: FeedbackRequest, user_id: UserIdDep, store: StoreDep
) -> FeedbackResponse:
    return await handle_feedback(store, user_id, payload)


@router.get("/intervention/current", response_model=ActionPayload)
async def current_intervention(user_id: UserIdDep, store: StoreDep) -> ActionPayload:
    session = await store.get_session(user_id)
    if session is None or not session.pending_action_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_pending_intervention")
    actions = await store.list_actions(session.state.value)
    for action in actions:
        if action.id == session.pending_action_id:
            return ActionPayload(
                id=action.id,
                name=action.name,
                duration_minutes=action.duration_minutes,
                intensity=action.intensity,
                steps=list(action.steps),
                caution=action.caution,
            )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action_not_found")