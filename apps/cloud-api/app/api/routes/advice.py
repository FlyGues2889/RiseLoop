from fastapi import APIRouter

from ..deps import CloudDep, SettingsDep, UserIdDep
from ...schemas.advice import AdviceRequest, AdviceResponse
from ...services.advice import build_advice

router = APIRouter(tags=["advice"])


@router.post("/advice", response_model=AdviceResponse)
async def advice(
    payload: AdviceRequest,
    user_id: UserIdDep,
    cloud: CloudDep,
    settings: SettingsDep,
) -> AdviceResponse:
    return await build_advice(cloud, settings, user_id, payload)
