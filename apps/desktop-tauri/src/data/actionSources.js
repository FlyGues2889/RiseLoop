export const ACTION_SOURCES = {
  "s0-neck-release": {
    title: "动作依据 · 颈肩拉伸",
    source: "颈肩拉伸随机对照试验显示，4 周规律拉伸可改善办公人群慢性颈肩痛、功能与生活质量。",
    url: "https://pubmed.ncbi.nlm.nih.gov/25780258/",
    evidenceId: "pmid-25780258",
  },
  "s0-shoulder-roll": {
    title: "动作依据 · 颈肩拉伸",
    source: "根据来自办公人群颈肩拉伸随机对照试验，肩胛绕环与胸椎伸展属于颈肩拉伸类动作。",
    url: "https://pubmed.ncbi.nlm.nih.gov/25780258/",
    evidenceId: "pmid-25780258",
  },
  "s2-band-row": {
    title: "动作依据 · 肌力训练",
    source: "颈肩胛肌力训练可在一定程度上减轻办公人群慢性颈痛与失能。",
    url: "https://pubmed.ncbi.nlm.nih.gov/38219373/",
    evidenceId: "pmid-38219373",
  },
  "s3-breathe": {
    title: "动作依据 · 微休息",
    source: "微休息是呼吸节律放松的动作，打断久坐的微休息对健康指标有益。",
    url: "https://pubmed.ncbi.nlm.nih.gov/35147898/",
    evidenceId: "pmid-35147898",
  },
  "s0-chin-tuck": {
    title: "动作依据 · 颈肩拉伸",
    source: "收下巴是颈深屈肌激活的入门动作。\n办公人群颈肩拉伸随机对照试验显示，规律练习可改善慢性颈肩痛与功能。",
    url: "https://pubmed.ncbi.nlm.nih.gov/25780258/",
    evidenceId: "pmid-25780258",
  },
  "s0-thoracic-rotation": {
    title: "动作依据 · 颈肩拉伸",
    source: "办公人群颈肩拉伸随机对照试验显示，胸椎旋转属于颈肩与上背活动。",
    url: "https://pubmed.ncbi.nlm.nih.gov/25780258/",
    evidenceId: "pmid-25780258",
  },
  "s1-wall-pushup": {
    title: "动作依据 · 肌力训练",
    source: "靠墙俯卧撑是低负荷动作，颈肩胛肌力训练可在一定程度上减轻办公人群慢性颈痛与失能。",
    url: "https://pubmed.ncbi.nlm.nih.gov/38219373/",
    evidenceId: "pmid-38219373",
  },
};

const DEFAULT_ACTION_SOURCE = {
  title: "动作依据 · 久坐打断",
  source: "短时打断久坐与微休息对健康指标有益，而具体动作强度以不引起疼痛最佳。",
  url: "https://pubmed.ncbi.nlm.nih.gov/35147898/",
  evidenceId: "pmid-35147898",
};

export const PLAN_SOURCE = {
  title: "方案依据",
  source:
    "WHO 2020 指南建议减少久坐、用任何强度活动替代；CDC 建议成人每周至少 150 分钟中等强度活动，并少坐多动。此外，提醒间隔需结合个人情况调整。",
  url: "https://www.who.int/publications/i/item/9789240015128",
  evidenceId: "url-who-9789240015128 / url-cdc-adult-activity",
};

export const REVIEW_SOURCE = {
  title: "建议依据",
  source:
    "自我监测、反馈与目标设定，是数字行为干预里最常用的做法。",
  url: "https://pubmed.ncbi.nlm.nih.gov/38178230/",
  evidenceId: "pmid-38178230",
};

export const PLAN_SELECTOR_SOURCE = {
  title: "方案依据 · 行动规划",
  source:
    "把干预绑定到可用时间和固定触发点，将它放到行动规划策略里，能减少“太忙/没时间”的阻碍。\n方案偏好只改变动作顺序，不影响安全规则。",
  url: "https://pubmed.ncbi.nlm.nih.gov/30943983/",
  evidenceId: "pmid-30943983",
};

export function sourceForAction(actionId) {
  return ACTION_SOURCES[actionId] ?? DEFAULT_ACTION_SOURCE;
}
