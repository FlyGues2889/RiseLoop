from fastapi import APIRouter

from ..deps import StoreDep, UserIdDep
from ...schemas.assessment import AssessmentRequest, AssessmentResponse
from ...services.assessment import run_assessment

router = APIRouter(tags=["assessment"])


@router.post("/assessment", response_model=AssessmentResponse)
async def create_assessment(
    payload: AssessmentRequest, user_id: UserIdDep, store: StoreDep
) -> AssessmentResponse:
    return await run_assessment(store, user_id, payload)