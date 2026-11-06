import json
import uuid
from datetime import UTC, datetime

from common import Backend, RealtimeState, dump, pending_key, session_key, sitting_key


async def read_realtime_state(backend: Backend, user_id: str) -> dict:
    raw = await backend.redis_get(session_key(user_id))
    session = json.loads(raw) if raw else {}
    sitting_raw = await backend.redis_get(sitting_key(user_id))
    pending_raw = await backend.redis_get(pending_key(user_id))

    state = RealtimeState(
        user_id=user_id,
        state=session.get("state", "S1"),
        counters=session.get("counters", {}),
        sitting_minutes=session.get("sitting_minutes", int(sitting_raw or 0)),
        last_push_at=session.get("last_push_at"),
        pending_intervention=json.loads(pending_raw) if pending_raw else None,
    )
    return state.model_dump()


async def write_intervention_result(
    backend: Backend,
    user_id: str,
    action_id: str,
    state: str,
    completion: str,
    feeling: str,
    pain_score: int,
    obstacle: str | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    reason: str | None = None,
    transition_type: str | None = None,
) -> dict:
    log_id = str(uuid.uuid4())
    await backend.fetch(
        """
        INSERT INTO intervention_logs
            (id, user_id, action_id, state, completion, feeling, pain_score, obstacle)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        log_id,
        user_id,
        action_id,
        state,
        completion,
        feeling,
        pain_score,
        obstacle,
    )

    if transition_type and to_state:
        await backend.fetch(
            """
            INSERT INTO state_transitions
                (id, user_id, from_state, to_state, reason, transition_type)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            str(uuid.uuid4()),
            user_id,
            from_state or state,
            to_state,
            reason or "",
            transition_type,
        )

    if to_state:
        raw = await backend.redis_get(session_key(user_id))
        session = json.loads(raw) if raw else {}
        session["state"] = to_state
        session["updated_at"] = datetime.now(UTC).isoformat()
        await backend.redis_set(session_key(user_id), dump(session), ttl_seconds=86400)

    await backend.redis_delete(pending_key(user_id))
    await backend.redis_set(sitting_key(user_id), "0", ttl_seconds=86400)

    return {
        "log_id": log_id,
        "user_id": user_id,
        "action_id": action_id,
        "state": to_state or state,
        "transition_type": transition_type,
        "written": True,
    }