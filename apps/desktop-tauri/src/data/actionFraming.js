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

const UPPER_HINT = "请坐直，使头部与双肩位于画面内";
const ARMS_HINT = "请使双肩与肘部位于画面内";
const FREE_HINT = "随做随看，不要求对齐";
const FULL_HINT = "请后退半步，使膝盖进入画面";

const TABLE = {
  "s0-neck-release": { framing: "upper", scene: "seated", focus: UPPER, hint: UPPER_HINT },
  "s0-shoulder-roll": { framing: "upper", scene: "seated", focus: ARMS, hint: ARMS_HINT },
  "s1-seated-knee": { framing: "none", scene: "seated", focus: [], hint: "腿部位于桌下，随做随看，不要求对齐" },
  "s1-stand-break": { framing: "full", scene: "standing", focus: STANDING, hint: "请起身后退半步，使膝盖进入画面" },
  "s1-hip-flexor": { framing: "full", scene: "standing", focus: STANDING, hint: "请后退少许，使髋部与膝盖位于画面内" },
  "s2-core-activation": { framing: "none", scene: "seated", focus: [], hint: FREE_HINT },
  "s2-band-row": { framing: "upper", scene: "seated", focus: ARMS, hint: "请使肩部至手腕位于画面内" },
  "s3-posture-reset": { framing: "full", scene: "standing", focus: [JOINT.left_ear, JOINT.right_ear, ...STANDING], hint: "靠墙站立后，使头部与髋部位于画面内" },
  "s3-breathe": { framing: "none", scene: "seated", focus: [], hint: FREE_HINT },
  "s0-chin-tuck": { framing: "upper", scene: "seated", focus: UPPER, hint: "请坐直并侧对镜头，使头部与双肩位于画面内" },
  "s0-thoracic-rotation": { framing: "upper", scene: "seated", focus: ARMS, hint: ARMS_HINT },
  "s1-wall-pushup": { framing: "upper", scene: "standing", focus: ARMS, hint: "请侧身站立，使肩部至手腕位于画面内" },
  "s1-calf-pump": { framing: "none", scene: "seated", focus: [], hint: "腿部位于桌下，随做随看，不要求对齐" },
  "s2-wall-sit": { framing: "full", scene: "standing", focus: STANDING, hint: "靠墙时后退，使髋部与膝盖进入画面" },
  "s3-seated-hip-circle": { framing: "none", scene: "seated", focus: [], hint: FREE_HINT },
};

const STANDING_HINT = /起身|站立|弓步|抬膝|深蹲|靠墙/;

export function resolveFraming(action) {
  if (!action) return { framing: "upper", scene: "seated", focus: UPPER, hint: UPPER_HINT };
  const preset = TABLE[action.id];
  if (preset) return preset;
  const steps = (action.steps ?? []).join(" ");
  const standing = STANDING_HINT.test(steps);
  const parts = action.body_parts ?? [];
  if (parts.includes("core")) {
    return { framing: "none", scene: "seated", focus: [], hint: FREE_HINT };
  }
  if (standing) {
    return { framing: "full", scene: "standing", focus: STANDING, hint: FULL_HINT };
  }
  return { framing: "upper", scene: "seated", focus: UPPER, hint: UPPER_HINT };
}
