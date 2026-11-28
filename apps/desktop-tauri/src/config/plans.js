export const PLAN_OPTIONS = [
  { id: "quick", label: "快速", name: "快速缓解", icon: "bolt", hint: "一个动作，2–3 分钟做完，先不耽误工作" },
  { id: "standard", label: "标准", name: "标准干预", icon: "balance", hint: "按不适部位挑动作，更对症一点" },
  { id: "intense", label: "强化", name: "强化训练", icon: "fitness_center", hint: "强化阶段连做 2–3 条，合计 5–8 分钟" },
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
