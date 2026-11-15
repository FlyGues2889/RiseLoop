// 取景是"画面怎么用"的约定，不是业务事实，所以放在客户端。
// 动作库新增动作时按 body_parts 与步骤文字兜底，行为不会崩。
const JOINT = {
  nose: 0,
  left_eye: 2,
  right_eye: 5,
  left_ear: 7,
  right_ear: 8,
  left_shoulder: 11,
  right_shoulder: 12,
  left_elbow: 13,
  right_elbow: 14,
  left_wrist: 15,
  right_wrist: 16,
  left_hip: 23,
  right_hip: 24,
  left_knee: 25,
  right_knee: 26,
  left_ankle: 27,
  right_ankle: 28,
};

const UPPER = [JOINT.nose, JOINT.left_ear, JOINT.right_ear, JOINT.left_shoulder, JOINT.right_shoulder];
const ARMS = [JOINT.left_shoulder, JOINT.right_shoulder, JOINT.left_elbow, JOINT.right_elbow];
const STANDING = [JOINT.left_shoulder, JOINT.right_shoulder, JOINT.left_hip, JOINT.right_hip, JOINT.left_knee, JOINT.right_knee];

const TABLE = {
  "s0-neck-release": { framing: "upper", scene: "seated", focus: UPPER, hint: "坐直，让头和双肩在画面里" },
  "s0-shoulder-roll": { framing: "upper", scene: "seated", focus: ARMS, hint: "让两侧肩膀和肘部都在画面里" },
  "s1-seated-knee": { framing: "none", scene: "seated", focus: [], hint: "腿在桌下，边做边看，不要求对齐" },
  "s1-stand-break": { framing: "full", scene: "standing", focus: STANDING, hint: "起身后往后退半步，让膝盖进画面" },
  "s1-hip-flexor": { framing: "full", scene: "standing", focus: STANDING, hint: "往后退一点，让髋和膝盖都在画面里" },
  "s2-core-activation": { framing: "none", scene: "seated", focus: [], hint: "边做边看，不要求对齐" },
  "s2-band-row": { framing: "upper", scene: "seated", focus: ARMS, hint: "让肩膀到手腕都在画面里" },
  "s3-posture-reset": { framing: "full", scene: "standing", focus: [JOINT.left_ear, JOINT.right_ear, ...STANDING], hint: "靠墙站好后，让头和髋都在画面里" },
  "s3-breathe": { framing: "none", scene: "seated", focus: [], hint: "边做边看，不要求对齐" },
  "s0-chin-tuck": { framing: "upper", scene: "seated", focus: UPPER, hint: "坐直，侧面对着镜头，让头和双肩在画面里" },
  "s0-thoracic-rotation": { framing: "upper", scene: "seated", focus: ARMS, hint: "让两侧肩膀和肘部都在画面里" },
  "s1-wall-pushup": { framing: "upper", scene: "standing", focus: ARMS, hint: "侧身站，让肩膀到手腕都在画面里" },
  "s1-calf-pump": { framing: "none", scene: "seated", focus: [], hint: "腿在桌下，边做边看，不要求对齐" },
  "s2-wall-sit": { framing: "full", scene: "standing", focus: STANDING, hint: "靠墙时往后退，让髋和膝盖进画面" },
  "s3-seated-hip-circle": { framing: "none", scene: "seated", focus: [], hint: "边做边看，不要求对齐" },
};

const STANDING_HINT = /起身|站立|弓步|抬膝|深蹲|靠墙/;

export function resolveFraming(action) {
  if (!action) return { framing: "upper", scene: "seated", focus: UPPER, hint: "坐直，让头和双肩在画面里" };
  const preset = TABLE[action.id];
  if (preset) return preset;
  const steps = (action.steps ?? []).join(" ");
  const standing = STANDING_HINT.test(steps);
  const parts = action.body_parts ?? [];
  if (parts.includes("core")) {
    return { framing: "none", scene: "seated", focus: [], hint: "边做边看，不要求对齐" };
  }
  if (standing) {
    return { framing: "full", scene: "standing", focus: STANDING, hint: "往后退半步，让膝盖进画面" };
  }
  return { framing: "upper", scene: "seated", focus: UPPER, hint: "坐直，让头和双肩在画面里" };
}
