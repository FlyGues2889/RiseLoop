export const BODY_PART_LABELS = {
  neck: "颈部",
  shoulder: "肩部",
  upper_back: "上背",
  low_back: "腰背",
  hip: "髋部",
  core: "核心",
};

const LOWER_STATE = { S0: null, S1: "S0", S2: "S1", S3: "S2" };

export function toPayload(action, matchReason = "") {
  return {
    id: action.id,
    name: action.name,
    duration_minutes: action.duration_minutes,
    intensity: action.intensity,
    body_parts: [...(action.body_parts ?? [])],
    steps: [...action.steps],
    caution: action.caution ?? "",
    match_reason: matchReason,
  };
}

export function selectActions(library, { state, bodyParts, maxMinutes } = {}) {
  return library
    .filter((action) => !state || action.state === state)
    .filter((action) => {
      if (!bodyParts || bodyParts.length === 0) return true;
      return action.body_parts.some((part) => bodyParts.includes(part));
    })
    .filter((action) => !maxMinutes || action.duration_minutes <= maxMinutes);
}

function overlapCount(action, bodyParts) {
  if (!bodyParts || bodyParts.length === 0) return 0;
  return action.body_parts.filter((part) => bodyParts.includes(part)).length;
}

function matchReason(action, sourceState, state, bodyParts) {
  const labels = action.body_parts
    .filter((part) => bodyParts?.includes(part) && BODY_PART_LABELS[part])
    .map((part) => BODY_PART_LABELS[part]);
  if (sourceState !== state) {
    return labels.length
      ? `更温和备选（${sourceState}）；匹配${labels.join("/")}`
      : `更温和备选（${sourceState}）`;
  }
  return labels.length
    ? `匹配${labels.join("/")}；当前状态 ${state}`
    : `当前状态 ${state} 的备选动作`;
}

/**
 * 自动匹配多个动作：当前状态优先，同状态内按部位重合度排序；
 * 当前状态匹配不足 2 个时，补一个更温和的下一级动作作为备选。
 */
export function rankActions(library, { state, bodyParts, maxMinutes, limit = 3 } = {}) {
  const current = selectActions(library, { state, maxMinutes });
  const items = current.map((action) => ({
    action,
    sourceState: state,
    overlap: overlapCount(action, bodyParts),
  }));

  if (bodyParts?.length) {
    const matched = items.filter((item) => item.overlap > 0);
    if (matched.length < 2) {
      const lower = LOWER_STATE[state];
      if (lower) {
        for (const action of selectActions(library, { state: lower, maxMinutes })) {
          const overlap = overlapCount(action, bodyParts);
          if (overlap > 0) items.push({ action, sourceState: lower, overlap });
        }
      }
    }
  }

  items.sort((a, b) => {
    const aSame = a.sourceState === state ? 1 : 0;
    const bSame = b.sourceState === state ? 1 : 0;
    return (
      bSame - aSame ||
      b.overlap - a.overlap ||
      a.action.duration_minutes - b.action.duration_minutes ||
      a.action.id.localeCompare(b.action.id)
    );
  });

  const seen = new Set();
  return items
    .filter((item) => {
      if (seen.has(item.action.id)) return false;
      seen.add(item.action.id);
      return true;
    })
    .slice(0, limit)
    .map((item) => ({
      ...item,
      matchReason: matchReason(item.action, item.sourceState, state, bodyParts),
    }));
}

export function pickAction(library, options = {}) {
  return rankActions(library, { ...options, limit: 1 })[0]?.action ?? null;
}
