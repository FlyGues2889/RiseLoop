// 步骤时长只从文字推算，误差在所难免；动作库的 duration_minutes 才是标签口径，
// 所以推算结果最后统一拟合到标签时长，两边不会各说各的。

const REP_SECONDS = 3;
const DEFAULT_STEP_SECONDS = 20;
const MIN_STEP_SECONDS = 10;
const MAX_STEP_SECONDS = 75;
// 读提示、挪椅子、换一口气都要时间，卡着秒数做会一直追倒计时
const STEP_SLACK_RATIO = 0.2;
const MIN_STEP_SLACK = 3;

export function parseStepSeconds(text) {
  const source = String(text || "");
  // 「每轮 12 秒，共做 6 轮」这种写法直接乘起来，避免退化成按单轮计时
  const perRound = /每(?:轮|组)\s*(\d+)\s*秒/.exec(source);
  const repeat = /(\d+)\s*[轮组]/.exec(source);
  if (perRound && repeat) return Number(perRound[1]) * Number(repeat[1]);
  const secs = [...source.matchAll(/(\d+)\s*秒/g)].map((match) => Number(match[1]));
  const reps = [...source.matchAll(/(\d+)\s*次/g)].map((match) => Number(match[1]));
  const rounds = /重复\s*(\d+)\s*[轮次]/.exec(source);
  const groups = /共\s*(\d+)\s*组/.exec(source);
  const sides = /左右各|各侧|两侧/.test(source) ? 2 : 1;
  const sum = (list) => list.reduce((acc, item) => acc + item, 0);
  if (secs.length && reps.length) return sum(secs) * sum(reps);
  if (secs.length) return sum(secs) * sides * (rounds ? Number(rounds[1]) : 1);
  if (reps.length) {
    return sum(reps) * sides * (groups ? Number(groups[1]) : 1) * REP_SECONDS
      * (rounds && !groups ? Number(rounds[1]) : 1);
  }
  if (rounds) return DEFAULT_STEP_SECONDS * Number(rounds[1]);
  return null;
}

function slackSeconds(value) {
  return Math.max(MIN_STEP_SLACK, Math.round(value * STEP_SLACK_RATIO));
}

function clampEstimate(value) {
  return Math.min(MAX_STEP_SECONDS, Math.max(MIN_STEP_SECONDS, value));
}

// 每一步先按文字估一个值，再整体拟合到动作标签时长：估短了等比放大，估长了等比缩回。
// 弹性也算在预算里，否则放大后总和会稳定超出 20%。
export function planStepSeconds(list, total) {
  const guessed = list.map((text) => parseStepSeconds(text));
  const raw = guessed.map((value) => clampEstimate(value ?? DEFAULT_STEP_SECONDS));
  // 「换侧，各做 2 组」这类步骤本身没有数字，按上一步的时长乘以组数
  for (let index = 1; index < list.length; index += 1) {
    if (guessed[index] !== null || !/换(侧|边)|另一(侧|边)|各做/.test(String(list[index] || ""))) continue;
    const groups = /(\d+)\s*(组|轮|次)/.exec(String(list[index]));
    raw[index] = clampEstimate(raw[index - 1] * (groups ? Number(groups[1]) : 1));
  }

  const base = raw.reduce((acc, item) => acc + item, 0);
  if (!total || base <= 0) {
    return raw.map((value) => value + slackSeconds(value));
  }

  // 弹性随步长变，缩放系数就跟着变；迭代两轮后误差已在 1 秒内
  let scale = total / base;
  for (let pass = 0; pass < 2; pass += 1) {
    const slackBudget = raw.reduce((acc, item) => acc + slackSeconds(item * scale), 0);
    scale = Math.max(0.1, (total - slackBudget) / base);
  }
  return raw.map((value) => {
    const seconds = Math.max(MIN_STEP_SECONDS, Math.round(value * scale));
    return seconds + slackSeconds(seconds);
  });
}

// 标签时长缺失时的兜底步长，主窗和通知窗共用同一个值
export { DEFAULT_STEP_SECONDS };
