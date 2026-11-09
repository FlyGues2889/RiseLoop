import assert from "node:assert/strict";
import { test } from "node:test";

import { createLocalEngine } from "../src/index.js";
import { SafetyShortCircuit } from "../src/safety.js";

const library = [
  {
    id: "a-s0",
    name: "颈部放松",
    state: "S0",
    body_parts: ["neck"],
    duration_minutes: 1,
    intensity: "gentle",
    steps: ["低头 5 秒", "回正"],
    caution: "",
  },
  {
    id: "a-s1",
    name: "起身活动",
    state: "S1",
    body_parts: ["neck", "low_back"],
    duration_minutes: 3,
    intensity: "normal",
    steps: ["起身", "抬膝"],
    caution: "",
  },
  {
    id: "a-s2",
    name: "强化训练",
    state: "S2",
    body_parts: ["upper_back"],
    duration_minutes: 6,
    intensity: "normal",
    steps: ["划船"],
    caution: "",
  },
];

function memoryStorage() {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, value),
    removeItem: (key) => map.delete(key),
  };
}

function engine(options = {}) {
  return createLocalEngine({ storage: memoryStorage(), library, now: () => Date.now(), ...options });
}

function assess(instance) {
  return instance.assessment({
    body_parts: ["neck"],
    sedentary_minutes: 300,
    available_minutes: 10,
    pain_score: 2,
    acute_discomfort: false,
  });
}

test("高疼痛评估落入 S0", async () => {
  const instance = engine();
  const result = await instance.assessment({
    body_parts: ["neck"],
    sedentary_minutes: 300,
    available_minutes: 10,
    pain_score: 8,
    acute_discomfort: true,
  });
  assert.equal(result.initial_state, "S0");
  assert.equal(result.risk_level, "high");
  assert.equal(result.intensity, "gentle");
});

test("未达阈值不触发干预", async () => {
  const instance = engine();
  await assess(instance);
  const result = await instance.heartbeat({ sitting_minutes: 20, threshold_minutes: 45 });
  assert.equal(result.triggered, false);
  assert.equal(result.reason, "below_threshold");
  assert.equal(result.next_check_minutes, 25);
});

test("达到阈值返回动作并进入冷却", async () => {
  const instance = engine();
  await assess(instance);
  const first = await instance.heartbeat({ sitting_minutes: 46, threshold_minutes: 45 });
  assert.equal(first.triggered, true);
  assert.equal(first.action.id, "a-s1");
  assert.equal(first.actions.length, 2);
  assert.equal(first.actions[0].id, "a-s1");
  assert.equal(first.actions[1].id, "a-s0");
  assert.match(first.actions[1].match_reason, /更温和备选/);

  const second = await instance.heartbeat({ sitting_minutes: 50, threshold_minutes: 45 });
  assert.equal(second.triggered, false);
  assert.equal(second.reason, "cooldown");
});

test("S1 连续完成 5 次升级到 S2", async () => {
  const instance = engine();
  await assess(instance);
  let last;
  for (let i = 0; i < 5; i += 1) {
    last = await instance.feedback({
      action_id: "a-s1",
      completion: "completed",
      feeling: "better",
      pain_score: 2,
    });
  }
  assert.equal(last.transition_type, "upgrade");
  assert.equal(last.from_state, "S1");
  assert.equal(last.to_state, "S2");
});

test("连续两次加重回退一级", async () => {
  const instance = engine();
  await assess(instance);
  await instance.feedback({ action_id: "a-s1", completion: "completed", feeling: "better", pain_score: 2 });
  const first = await instance.feedback({ action_id: "a-s1", completion: "completed", feeling: "worse", pain_score: 2 });
  assert.equal(first.transition_type, "hold");

  const second = await instance.feedback({ action_id: "a-s1", completion: "completed", feeling: "worse", pain_score: 2 });
  assert.equal(second.transition_type, "rollback");
  assert.equal(second.to_state, "S0");
});

test("连续三次跳过降级但不降状态", async () => {
  const instance = engine();
  await assess(instance);
  await instance.feedback({ action_id: "a-s1", completion: "skipped", feeling: "same", obstacle: "busy" });
  await instance.feedback({ action_id: "a-s1", completion: "skipped", feeling: "same", obstacle: "busy" });
  const third = await instance.feedback({ action_id: "a-s1", completion: "skipped", feeling: "same", obstacle: "busy" });
  assert.equal(third.transition_type, "degrade");
  assert.equal(third.to_state, "S1");
  assert.equal(third.intensity, "gentle");
  assert.match(third.reason, /太忙/);
});

test("红牌症状直接短路", async () => {
  const instance = engine();
  await assess(instance);
  await assert.rejects(
    () => instance.feedback({ action_id: "a-s1", completion: "completed", red_flags: ["radiating_pain"] }),
    (error) => {
      assert.ok(error instanceof SafetyShortCircuit);
      assert.equal(error.payload.to_state, "S0");
      assert.deepEqual(error.payload.red_flag_labels, ["放射痛"]);
      return true;
    }
  );
});

test("反馈文本中的红牌关键词也会被拦截", async () => {
  const instance = engine();
  await assess(instance);
  await assert.rejects(
    () => instance.feedback({ action_id: "a-s1", completion: "completed", note: "刚才有点眩晕" }),
    (error) => error instanceof SafetyShortCircuit
  );
});

test("数据写入本地存储并可被新实例读取", async () => {
  const storage = memoryStorage();
  const first = createLocalEngine({ storage, library });
  await assess(first);
  await first.heartbeat({ sitting_minutes: 46, threshold_minutes: 45 });

  const second = createLocalEngine({ storage, library });
  assert.equal(second.hasProfile(), true);
  const snapshot = second.snapshot();
  assert.equal(snapshot.assessment.initial_state, "S1");
  assert.equal(snapshot.session.pending_action_id, "a-s1");
});

test("reset 清空本地数据", async () => {
  const storage = memoryStorage();
  const instance = createLocalEngine({ storage, library });
  await assess(instance);
  instance.reset();
  assert.equal(instance.hasProfile(), false);
  assert.equal(storage.getItem("riseloop.local.v1"), null);
});
test("周复盘汇总干预记录", async () => {
  const instance = engine();
  await assess(instance);
  await instance.feedback({ action_id: "a-s1", completion: "completed", feeling: "better", pain_score: 2 });
  await instance.feedback({
    action_id: "a-s1",
    completion: "skipped",
    feeling: "same",
    pain_score: 4,
    obstacle: "busy",
  });

  const review = await instance.weeklyReview(7);
  assert.equal(review.interventions.total, 2);
  assert.equal(review.interventions.completed, 1);
  assert.equal(review.interventions.completion_rate, 50);
  assert.equal(review.pain.average, 3);
  assert.equal(review.pain.latest, 4);
  assert.equal(review.pain.trend, "unknown");
  assert.equal(review.top_obstacles[0].obstacle, "busy");
  assert.equal(review.current_state, "S1");
  assert.ok(review.suggestions.length > 0);
});

test("周复盘无记录时给出提示", async () => {
  const instance = engine();
  const review = await instance.weeklyReview(7);
  assert.equal(review.interventions.total, 0);
  assert.equal(review.interventions.completion_rate, 0);
  assert.match(review.highlights[0], /还没有干预记录/);
});
