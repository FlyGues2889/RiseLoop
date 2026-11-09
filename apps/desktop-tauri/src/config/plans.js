export const PLAN_OPTIONS = [
  {
    id: "quick",
    label: "快速",
    name: "快速缓解",
    duration: "先做最短的那个",
    icon: "bolt",
    description: "开会、临时忙起来时选它。先做一个最短的动作，把久坐打断。",
  },
  {
    id: "standard",
    label: "标准",
    name: "标准干预",
    duration: "按状态给首选",
    icon: "balance",
    description: "默认选项。按当前状态给首选动作，效果和时间兼顾。",
  },
  {
    id: "intense",
    label: "强化",
    name: "强化训练",
    duration: "优先完整的动作",
    icon: "fitness_center",
    description: "时间充裕时选它。优先更长、更完整的动作，没有更长的会自动退回标准。",
  },
];

export const DEFAULT_PLAN_PREFERENCE = "standard";

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
