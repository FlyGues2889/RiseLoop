import json
from typing import Any

from common import Backend


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return list(value)


async def get_actions_by_state(
    backend: Backend,
    state: str,
    body_parts: list[str] | None = None,
    max_minutes: int | None = None,
    limit: int = 3,
) -> list[dict]:
    rows = await backend.fetch(
        """
        SELECT id, name, state, body_parts, duration_minutes, intensity, steps, caution
        FROM actions
        WHERE state = $1 AND enabled = TRUE
          AND ($2::int IS NULL OR duration_minutes <= $2)
        ORDER BY duration_minutes ASC
        LIMIT $3
        """,
        state,
        max_minutes,
        max(limit * 3, 3),
    )

    actions: list[dict] = []
    for row in rows:
        record = dict(row)
        parts = _as_list(record.get("body_parts"))
        if body_parts and not set(parts) & set(body_parts):
            continue
        record["body_parts"] = parts
        record["steps"] = _as_list(record.get("steps"))
        record["caution"] = record.get("caution") or ""
        actions.append(record)
        if len(actions) >= limit:
            break
    return actions