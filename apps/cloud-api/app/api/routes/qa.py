from fastapi import APIRouter

from ..deps import CloudDep, SettingsDep, StoreDep, UserIdDep
from ...schemas.qa import QaRequest, QaResponse
from ...services.qa import answer_question

router = APIRouter(tags=["qa"])


@router.post("/qa/ask", response_model=QaResponse)
async def ask_question(
    payload: QaRequest,
    user_id: UserIdDep,
    store: StoreDep,
    cloud: CloudDep,
    settings: SettingsDep,
) -> QaResponse:
    return await answer_question(store, cloud, settings, user_id, payload)