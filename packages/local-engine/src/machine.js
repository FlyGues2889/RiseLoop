export const STATE_NAMES = { S0: "急性缓解", S1: "激活", S2: "强化", S3: "维持" };

export const DURATION_BY_STATE = {
  S0: [0, 2],
  S1: [3, 5],
  S2: [5, 8],
  S3: [2, 5],
};

export const GENTLE_DURATION_BY_STATE = {
  S0: [0, 1],
  S1: [2, 3],
  S2: [3, 5],
  S3: [2, 3],
};

export const ROLLBACK_TARGET = { S3: "S2", S2: "S1", S1: "S0", S0: "S0" };

export const RED_FLAG_LABELS = {
  radiating_pain: "放射痛",
  numbness_worse: "麻木加重",
  dizziness: "眩晕",
  leg_weakness: "下肢无力",
  cotton_wool_gait: "踩棉花感",
  bowel_bladder: "大小便异常",
  perineal_numbness: "会阴麻木",
  post_trauma_severe_pain: "外伤后剧痛",
};

export const OBSTACLE_LABELS = {
  busy: "太忙",
  too_hard: "动作太难",
  no_space: "没地方做",
  forgot: "忘了",
};

export function emptyCounters() {
  return { completed_streak: 0, skipped_streak: 0, worse_streak: 0, s0_completed: 0 };
}

function build({
  state,
  toState,
  transitionType,
  reason,
  duration,
  intensity,
  counters,
  stopExercise = false,
  medicalAdvice = false,
}) {
  return {
    from_state: state,
    to_state: toState,
    transition_type: transitionType,
    reason,
    duration_minutes: duration,
    intensity,
    stop_exercise: stopExercise,
    medical_advice: medicalAdvice,
    counters,
  };
}

export function decide(state, feedback, counters = emptyCounters()) {
  const flags = feedback.red_flags ?? [];

  if (flags.length > 0) {
    const names = flags.map((flag) => RED_FLAG_LABELS[flag] ?? flag).join("、");
    return build({
      state,
      toState: "S0",
      transitionType: "short_circuit",
      reason: `命中安全红线：${names}，停止运动并建议就医`,
      duration: GENTLE_DURATION_BY_STATE.S0,
      intensity: "gentle",
      counters: emptyCounters(),
      stopExercise: true,
      medicalAdvice: true,
    });
  }

  if (feedback.feeling === "worse" || feedback.next_day_worse) {
    const worseStreak = counters.worse_streak + 1;
    let nextCounters = {
      completed_streak: 0,
      skipped_streak: 0,
      worse_streak: worseStreak,
      s0_completed: counters.s0_completed,
    };
    if (worseStreak >= 2) {
      const target = ROLLBACK_TARGET[state];
      if (target === "S0") {
        nextCounters = emptyCounters();
      }
      return build({
        state,
        toState: target,
        transitionType: "rollback",
        reason: `连续 ${worseStreak} 次症状加重，回退至 ${target}`,
        duration: DURATION_BY_STATE[target],
        intensity: "normal",
        counters: nextCounters,
      });
    }
    return build({
      state,
      toState: state,
      transitionType: "hold",
      reason: "症状加重 1 次，保持当前状态并观察，不升级",
      duration: DURATION_BY_STATE[state],
      intensity: "normal",
      counters: nextCounters,
    });
  }

  if (feedback.completion === "skipped") {
    const skippedStreak = counters.skipped_streak + 1;
    const nextCounters = {
      completed_streak: 0,
      skipped_streak: skippedStreak,
      worse_streak: 0,
      s0_completed: counters.s0_completed,
    };
    if (skippedStreak >= 3) {
      let reason = `连续 ${skippedStreak} 次跳过，同状态更换更短、更低强度动作`;
      if (feedback.obstacle) {
        reason = `${reason}（障碍：${OBSTACLE_LABELS[feedback.obstacle] ?? feedback.obstacle}）`;
      }
      return build({
        state,
        toState: state,
        transitionType: "degrade",
        reason,
        duration: GENTLE_DURATION_BY_STATE[state],
        intensity: "gentle",
        counters: nextCounters,
      });
    }
    return build({
      state,
      toState: state,
      transitionType: "hold",
      reason: `连续 ${skippedStreak} 次跳过，不升级`,
      duration: DURATION_BY_STATE[state],
      intensity: "normal",
      counters: nextCounters,
    });
  }

  if (feedback.completion === "partial") {
    return build({
      state,
      toState: state,
      transitionType: "hold",
      reason: "部分完成不计入连续完成，维持当前状态",
      duration: DURATION_BY_STATE[state],
      intensity: "normal",
      counters: {
        completed_streak: 0,
        skipped_streak: 0,
        worse_streak: 0,
        s0_completed: counters.s0_completed,
      },
    });
  }

  const completedStreak = counters.completed_streak + 1;

  if (state === "S0") {
    const s0Completed = counters.s0_completed + 1;
    const nextCounters = {
      completed_streak: completedStreak,
      skipped_streak: 0,
      worse_streak: 0,
      s0_completed: s0Completed,
    };
    if (s0Completed >= 2 && (feedback.pain_score ?? 0) <= 3 && !feedback.next_day_worse) {
      return build({
        state: "S0",
        toState: "S1",
        transitionType: "upgrade",
        reason: "S0 已完成 2 次、评分 ≤3 且次日无加重，升级至 S1",
        duration: DURATION_BY_STATE.S1,
        intensity: "normal",
        counters: {
          completed_streak: 0,
          skipped_streak: 0,
          worse_streak: 0,
          s0_completed: s0Completed,
        },
      });
    }
    return build({
      state: "S0",
      toState: "S0",
      transitionType: "hold",
      reason: "S0 升级条件未满足（需完成 ≥2 次、评分 ≤3、次日无加重）",
      duration: DURATION_BY_STATE.S0,
      intensity: "normal",
      counters: nextCounters,
    });
  }

  if (state === "S1" && completedStreak >= 5) {
    return build({
      state: "S1",
      toState: "S2",
      transitionType: "upgrade",
      reason: "S1 连续完成 5 次，升级至 S2",
      duration: DURATION_BY_STATE.S2,
      intensity: "normal",
      counters: {
        completed_streak: 0,
        skipped_streak: 0,
        worse_streak: 0,
        s0_completed: counters.s0_completed,
      },
    });
  }

  if (state === "S2" && completedStreak >= 10) {
    return build({
      state: "S2",
      toState: "S3",
      transitionType: "upgrade",
      reason: "S2 连续完成 10 次，升级至 S3",
      duration: DURATION_BY_STATE.S3,
      intensity: "normal",
      counters: {
        completed_streak: 0,
        skipped_streak: 0,
        worse_streak: 0,
        s0_completed: counters.s0_completed,
      },
    });
  }

  return build({
    state,
    toState: state,
    transitionType: "hold",
    reason: "连续完成次数未达升级阈值，维持当前状态",
    duration: DURATION_BY_STATE[state],
    intensity: "normal",
    counters: {
      completed_streak: completedStreak,
      skipped_streak: 0,
      worse_streak: 0,
      s0_completed: counters.s0_completed,
    },
  });
}