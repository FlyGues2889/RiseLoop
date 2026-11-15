export const PLAN_OPTIONS = [
  { id: "quick", label: "快速", name: "快速缓解", icon: "bolt" },
  { id: "standard", label: "标准", name: "标准干预", icon: "balance" },
  { id: "intense", label: "强化", name: "强化训练", icon: "fitness_center" },
];

export const DEFAULT_PLAN_PREFERENCE = "quick";

export function isPlanPreference(value) {
  return PLAN_OPTIONS.some((plan) => plan.id === value);
}

export function pickActionForPlan(actions, planId) {
  if (!Array.isArray(actions) || actions.length === 0) return null;
  if (planId === "quick") {
    return [...actions].sort(
      (a, b) =>
        (a.intensity === "gentle" ? 0 : 1) - (b.intensity === "gentle" ? 0 : 1) ||
        a.duration_minutes - b.duration_minutes
    )[0];
  }
  if (planId === "intense") {
    return [...actions].sort(
      (a, b) =>
        (b.intensity === "normal" ? 1 : 0) - (a.intensity === "normal" ? 1 : 0) ||
        b.duration_minutes - a.duration_minutes
    )[0];
  }
  return actions[0];
}
