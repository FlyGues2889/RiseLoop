from fastapi import APIRouter, Query

from ..deps import StoreDep, UserIdDep
from ...schemas.review import WeeklyReview
from ...services.weekly import build_weekly_review

router = APIRouter(tags=["review"])


@router.get("/review/weekly", response_model=WeeklyReview)
async def weekly_review(
    user_id: UserIdDep,
    store: StoreDep,
    days: int = Query(default=7, ge=1, le=30),
) -> WeeklyReview:
    return await build_weekly_review(store, user_id, days)