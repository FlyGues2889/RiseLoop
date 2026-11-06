from collections import Counter
from datetime import UTC, datetime, timedelta

from ..core.safety import MEDICAL_DISCLAIMER
from ..repositories.store import Store
from ..schemas.review import (
    InterventionStats,
    ObstacleCount,
    PainStats,
    WeeklyReview,
)

TRANSITION_TYPES = ("upgrade", "rollback", "degrade", "hold", "short_circuit")


def _pain_trend(scores: list[int]) -> str:
    if len(scores) < 4:
        return "unknown"
    middle = len(scores) // 2
    first = sum(scores[:middle]) / middle
    second = sum(scores[middle:]) / (len(scores) - middle)
    delta = second - first
    if delta <= -0.5:
        return "improving"
    if delta >= 0.5:
        return "worsening"
    return "stable"


def _build_highlights(review: WeeklyReview) -> list[str]:
    highlights: list[str] = []
    if review.interventions.total == 0:
        highlights.append(f"过去 {review.days} 天还没有干预记录，先完成一次评估即可开始。")
    elif review.interventions.completion_rate >= 80:
        highlights.append(f"完成率 {review.interventions.completion_rate}%，节奏保持得很好。")
    if review.pain.trend == "improving":
        highlights.append("疼痛评分在下降，当前动作强度是合适的。")
    elif review.pain.trend == "worsening":
        highlights.append("疼痛评分在上升，建议缩短单次时长并观察。")
    if review.safety_events:
        highlights.append(f"出现 {review.safety_events} 次安全中断，请优先就医确认。")
    return highlights


def _build_suggestions(review: WeeklyReview) -> list[str]:
    suggestions: list[str] = []
    rate = review.interventions.completion_rate
    if review.interventions.total and rate < 50:
        suggestions.append("完成率偏低，把单次可用时间调到 3 分钟以内更容易坚持。")
    if review.top_obstacles:
        top = review.top_obstacles[0]
        mapping = {
            "busy": "主要阻碍是太忙，建议把动作绑定到接水、开会结束等固定触发点。",
            "too_hard": "主要阻碍是动作太难，可切换到更温和的动作。",
            "no_space": "主要阻碍是没地方做，优先选择坐姿或站姿动作。",
            "forgot": "主要阻碍是忘记，保持 45 分钟提醒并允许托盘常驻。",
        }
        if top.obstacle in mapping:
            suggestions.append(mapping[top.obstacle])
    if not suggestions:
        suggestions.append("保持当前节奏，每 45 分钟起身一次即可。")
    return suggestions


async def build_weekly_review(store: Store, user_id: str, days: int) -> WeeklyReview:
    since = datetime.now(UTC) - timedelta(days=days)
    logs = await store.list_intervention_logs(user_id, since)
    transitions = await store.list_transitions(user_id, since)
    safety_events = await store.count_safety_events(user_id, since)
    sitting_events = await store.count_sitting_events(user_id, since)
    session = await store.get_session(user_id)

    total = len(logs)
    completed = sum(1 for item in logs if item.get("completion") == "completed")
    scores = [int(item["pain_score"]) for item in logs if item.get("pain_score") is not None]
    obstacles = Counter(
        item["obstacle"] for item in logs if item.get("obstacle")
    )

    transition_counts = {key: 0 for key in TRANSITION_TYPES}
    for item in transitions:
        key = item.get("transition_type")
        if key in transition_counts:
            transition_counts[key] += 1

    review = WeeklyReview(
        days=days,
        generated_at=datetime.now(UTC),
        current_state=session.state.value if session else None,
        interventions=InterventionStats(
            total=total,
            completed=completed,
            completion_rate=round(completed / total * 100, 1) if total else 0.0,
        ),
        pain=PainStats(
            average=round(sum(scores) / len(scores), 1) if scores else None,
            latest=scores[-1] if scores else None,
            trend=_pain_trend(scores),
        ),
        transitions=transition_counts,
        top_obstacles=[
            ObstacleCount(obstacle=name, count=count)
            for name, count in obstacles.most_common(3)
        ],
        safety_events=safety_events,
        sitting_events=sitting_events,
        disclaimer=MEDICAL_DISCLAIMER,
    )
    review.highlights = _build_highlights(review)
    review.suggestions = _build_suggestions(review)
    return review