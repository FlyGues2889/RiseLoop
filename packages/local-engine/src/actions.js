export function toPayload(action) {
  return {
    id: action.id,
    name: action.name,
    duration_minutes: action.duration_minutes,
    intensity: action.intensity,
    steps: [...action.steps],
    caution: action.caution ?? "",
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

export function pickAction(library, options = {}) {
  const matched = selectActions(library, options);
  if (matched.length > 0) return matched[0];
  const fallback = selectActions(library, { state: options.state, maxMinutes: options.maxMinutes });
  return fallback[0] ?? null;
}