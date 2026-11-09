from fastapi import APIRouter, HTTPException

from ..deps import CloudDep, StoreDep, UserIdDep
from ...schemas.posture import PostureInferRequest, PostureInferResponse, PostureRiskRequest, PostureRiskResponse
from ...services.posture import handle_posture_risk
from ...services.posture_infer import InferenceUnavailable, handle_posture_infer

router = APIRouter(tags=["posture"])


@router.post("/posture/risk", response_model=PostureRiskResponse)
async def posture_risk(
    payload: PostureRiskRequest, user_id: UserIdDep, store: StoreDep
) -> PostureRiskResponse:
    return await handle_posture_risk(store, user_id, payload)


@router.post(
    "/posture/infer",
    response_model=PostureInferResponse,
    responses={503: {"description": "ModelArts 不可用，端侧需显式降级"}},
)
async def posture_infer(
    payload: PostureInferRequest,
    user_id: UserIdDep,
    store: StoreDep,
    cloud: CloudDep,
) -> PostureInferResponse:
    try:
        return await handle_posture_infer(store, user_id, payload, cloud)
    except InferenceUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "modelarts_unavailable", "reason": exc.reason},
        ) from exc
