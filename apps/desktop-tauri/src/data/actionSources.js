export const ACTION_SOURCES = {
  "s0-neck-release": {
    title: "动作依据 · 颈肩拉伸",
    source: "颈肩拉伸随机对照试验显示，4 周规律拉伸可改善办公人群慢性颈肩痛、功能与生活质量；本动作是 1 分钟微休息版本。",
    url: "https://pubmed.ncbi.nlm.nih.gov/25780258/",
    evidenceId: "pmid-25780258",
  },
  "s0-shoulder-roll": {
    title: "动作依据 · 颈肩拉伸",
    source: "肩胛绕环与胸椎伸展属于颈肩拉伸类动作；证据来自办公人群颈肩拉伸随机对照试验。",
    url: "https://pubmed.ncbi.nlm.nih.gov/25780258/",
    evidenceId: "pmid-25780258",
  },
  "s1-stand-break": {
    title: "动作依据 · 主动休息",
    source: "主动休息或姿势变换可降低高风险办公人群 6 个月内颈痛与腰痛新发（3 臂集群随机对照试验）。",
    url: "https://pubmed.ncbi.nlm.nih.gov/33906239/",
    evidenceId: "pmid-33906239",
  },
  "s1-hip-flexor": {
    title: "动作依据 · 拉伸训练",
    source: "拉伸训练在 6 个月内改善办公人群颈肩腰疼痛，效果优于单纯工位改造（随机对照试验）。",
    url: "https://pubmed.ncbi.nlm.nih.gov/28939263/",
    evidenceId: "pmid-28939263",
  },
  "s2-core-activation": {
    title: "动作依据 · 主动休息",
    source: "12 周主动休息干预改善年轻人非特异性下背痛与功能障碍（随机对照试验）。",
    url: "https://pubmed.ncbi.nlm.nih.gov/39707287/",
    evidenceId: "pmid-39707287",
  },
  "s2-band-row": {
    title: "动作依据 · 肌力训练",
    source: "颈肩胛肌力训练可减轻办公人群慢性颈痛与失能（系统综述/Meta 分析，证据确定性低）。",
    url: "https://pubmed.ncbi.nlm.nih.gov/38219373/",
    evidenceId: "pmid-38219373",
  },
  "s3-posture-reset": {
    title: "动作依据 · 姿势行为",
    source: "办公人群久坐时间、姿势与行为均与下背痛相关，其中久坐行为证据最强（范围综述）。",
    url: "https://pubmed.ncbi.nlm.nih.gov/40111906/",
    evidenceId: "pmid-40111906",
  },
  "s3-breathe": {
    title: "动作依据 · 微休息",
    source: "打断久坐的短时微休息对健康指标有益；本动作是呼吸节律放松版本。",
    url: "https://pubmed.ncbi.nlm.nih.gov/35147898/",
    evidenceId: "pmid-35147898",
  },
};

const DEFAULT_ACTION_SOURCE = {
  title: "动作依据 · 久坐打断",
  source: "短时打断久坐与微休息对健康指标有益；具体动作强度以不引起疼痛为限。",
  url: "https://pubmed.ncbi.nlm.nih.gov/35147898/",
  evidenceId: "pmid-35147898",
};

export const PLAN_SOURCE = {
  title: "方案依据",
  source:
    "WHO 2020 指南建议减少久坐、用任何强度活动替代；CDC 建议成人每周至少 150 分钟中等强度活动，并少坐多动。45 分钟提醒间隔是产品取值，需结合个人情况调整。",
  url: "https://www.who.int/publications/i/item/9789240015128",
  evidenceId: "url-who-9789240015128 / url-cdc-adult-activity",
};

export const REVIEW_SOURCE = {
  title: "建议依据",
  source:
    "自我监测、反馈与目标设定，是数字行为干预里最常用的做法；久坐打断与微休息的证据见项目文档。",
  url: "https://pubmed.ncbi.nlm.nih.gov/38178230/",
  evidenceId: "pmid-38178230",
};

export const PLAN_SELECTOR_SOURCE = {
  title: "方案依据 · 行动规划",
  source:
    "把干预绑定到可用时间和固定触发点，属于行动规划策略，能减少“太忙/没时间”的阻碍。方案偏好只改变动作顺序，不影响安全规则。",
  url: "https://pubmed.ncbi.nlm.nih.gov/30943983/",
  evidenceId: "pmid-30943983",
};

export function sourceForAction(actionId) {
  return ACTION_SOURCES[actionId] ?? DEFAULT_ACTION_SOURCE;
}
