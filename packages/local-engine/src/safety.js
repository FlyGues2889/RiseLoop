export const MEDICAL_DISCLAIMER =
  "本产品为健康行为指导工具，不提供医疗诊断或治疗建议。如出现持续疼痛、放射痛、麻木加重、肢体无力或外伤后剧痛，请及时就医。";

export const RED_FLAG_MESSAGES = {
  radiating_pain: "放射痛",
  numbness_worse: "麻木加重",
  dizziness: "眩晕",
  leg_weakness: "下肢无力",
  cotton_wool_gait: "踩棉花感",
  bowel_bladder: "大小便异常",
  perineal_numbness: "会阴麻木",
  post_trauma_severe_pain: "外伤后剧痛",
};

const RED_FLAG_KEYWORDS = {
  radiating_pain: ["放射痛", "串电", "放射到", "窜痛", "radiating pain", "shooting pain"],
  numbness_worse: ["麻木加重", "越来越麻", "麻木扩散", "手麻加重", "numbness worse", "worsening numbness"],
  dizziness: ["眩晕", "头晕目眩", "天旋地转", "dizziness", "dizzy", "vertigo"],
  leg_weakness: ["下肢无力", "腿没劲", "腿发软", "站不住", "leg weakness", "weak legs"],
  cotton_wool_gait: ["踩棉花", "走路发飘", "脚下没根", "cotton wool gait", "walking on cotton"],
  bowel_bladder: ["大小便失禁", "大小便异常", "排尿困难", "尿不出来", "incontinence", "bladder dysfunction"],
  perineal_numbness: ["会阴麻", "会阴部麻木", "鞍区麻", "saddle anesthesia", "perineal numbness"],
  post_trauma_severe_pain: ["外伤后剧痛", "摔伤后剧痛", "撞击后剧痛", "severe pain after trauma", "pain after a fall"],
};

export function detectRedFlags(text) {
  const haystack = String(text).toLowerCase();
  const hits = [];
  for (const [flag, keywords] of Object.entries(RED_FLAG_KEYWORDS)) {
    if (keywords.some((keyword) => haystack.includes(keyword.toLowerCase()))) {
      hits.push(flag);
    }
  }
  return hits;
}

export function detectInPayload(payload) {
  const found = new Set();
  const stack = [payload];
  while (stack.length > 0) {
    const current = stack.pop();
    if (typeof current === "string") {
      if (RED_FLAG_MESSAGES[current]) found.add(current);
      for (const flag of detectRedFlags(current)) found.add(flag);
    } else if (Array.isArray(current)) {
      stack.push(...current);
    } else if (current && typeof current === "object") {
      stack.push(...Object.values(current));
    }
  }
  return [...found].sort();
}

export function safetyPayload(redFlags) {
  return {
    error: "safety_short_circuit",
    message: "检测到需要就医的高风险信号，已停止运动推荐。",
    red_flags: redFlags,
    red_flag_labels: redFlags.map((flag) => RED_FLAG_MESSAGES[flag] ?? flag),
    stop_exercise: true,
    to_state: "S0",
    medical_advice: true,
    disclaimer: MEDICAL_DISCLAIMER,
  };
}

export class SafetyShortCircuit extends Error {
  constructor(redFlags) {
    super("safety_short_circuit");
    this.name = "SafetyShortCircuit";
    this.payload = safetyPayload(redFlags);
  }
}