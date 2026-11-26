# 端云姿态感知链路（11.10 路线决策，11.23 模型 v1 / 特征契约 v2，11.26 契约 v3）

> 2026-11-23：姿态模型 v1（特征契约 v2）训练包与离线报告已完成；真实 ModelArts endpoint 尚未开通，当前线上仍是 mock 几何规则。
> 2026-11-26：第一批真实采集完成（14 人、去重后 3,974 帧）；特征契约 v3（2D 几何 + 个人中立位基线）已落地，真实与合成数据都已按 v3 重生成。v3 模型尚未训练，报告仍是 v1/v2 合成数据结果。

## 1. 目标与边界

| 项 | 内容 |
|---|---|
| 目标 | 11.13 跑通“摄像头 → 本地关键点 → 云端推理 → 客户端提示”的最小链路；姿态模型 v1（特征契约 v2）已完成训练与离线评估（11.23），特征契约 v3 已落地（11.26），v3 模型待训练，真实 endpoint 待开通 |
| 输入 | 摄像头画面仅在本地处理；上传归一化骨骼关键点，不上传原始图像/视频；只要求头部与双肩清晰入画，不要求全身 |
| 云端 | ModelArts 在线推理（mock / huawei 两种云端配置）：v1 模型用 A 版 5 个派生特征 MLP；v3 改为 9 个 2D 特征 + 个人基线偏差，四分类 + 置信度 <0.5 判 `undetermined` |
| 客户端 | Tauri 2 + Vue 3；叠加姿态引导框、风险解释与回退提示 |
| 边界 | 姿态识别只用于行为指导，不做医疗诊断；安全红线仍由 `safety-check` 中间件前置 |

### 11.20 MVP 范围与优先级

| 模块 | 验收口径 | 优先级 |
|---|---|---|
| 端侧姿态提取 | 摄像头采集、关键点显示、开关控制、无原始视频上传 | P0 |
| ModelArts 在线推理 | 真实华为云服务返回姿态分类与置信度 | P0 |
| 风险融合 | 久坐时长、姿态异常持续性、用户反馈形成可解释风险指数 | P0 |
| S0–S3 状态机集成 | 云端结果能触发既有干预流程 | P0 |
| 干预反馈闭环 | 从姿态识别到动作推荐、完成反馈、记录保存全程跑通 | P0 |
| 云端业务部署 | ECS + FastAPI 或等效部署方式，具备稳定 API | P0 |
| RDS / DCS | 关键历史记录持久化；实时状态按需缓存 | P0 |
| 循证知识库 | 先人工审核 10–20 条 JSON 规则并展示来源 | P0 |
| 个人坐姿引导 | 基准线、局部调整提示，不追求复杂视觉特效 | P0 |
| 喝水提醒、隐形训练等 | 不阻塞核心，暂缓或保留已有能力 | P1 / 暂缓 |

### 工作流分工与当前状态

| 工作流 | 范围 | 当前状态 | 关键依赖 |
|---|---|---|---|
| 端侧与前端 | Tauri、摄像头、关键点提取、隐私开关、姿态引导 UI | spike 已完成；真人关键点/演示机性能待验证 | 演示机摄像头 |
| 云端与模型 | ModelArts、ECS/FastAPI、APIG、模型部署、性能测试 | v1 训练包与离线报告已完成（5 特征 MLP，合成数据 test macro-F1 0.9670）；v3 契约与真实数据已落地，v3 模型待训练；`/posture/infer` + 适配层就绪；真实 endpoint 待开通 | ModelArts endpoint（需付费开通）、v3 训练 |
| 算法与运动健康 | 数据集、姿态分类评价、风险规则、循证 JSON、动作适配 | 证据台账已完成；规则草稿/姿态评价待做 | 运康专业审核 |
| 集成与交付 | S0–S3 集成、DCS/RDS/ModelArts、自动化测试、文档与演示 | 状态机/动作库已有；真实 DCS/RDS/ModelArts 与端到端集成未开始 | 云端环境与演示机 |

**范围冻结口径：**

- 个人坐姿引导只做“基准线 + 局部调整提示”，不做 3D 骨骼、复杂动效或游戏化。
- 循证规则必须由运康专业人员审核后才能标“已审核”；agent 只能起草，不能对外宣称已获专业认可。
- 云端部署验收以 ECS + FastAPI 真实 API 为准；`mock` 只能用于本地联调，不能作为“已上云”的证据。
- RDS/DCS 必须真实接线；当前 mock 内存存储不能替代持久化验收。
- 喝水提醒、隐形训练等不阻塞 11.20 MVP，避免分散核心链路工时。

## 2. 路线决策

**11.10 选定：MediaPipe Tasks Vision（Pose Landmarker，JS/WASM）跑在 Tauri WebView 内。**

理由：

1. 浏览器/WebView 直接 `getUserMedia` + WASM，11.13 前最容易跑通，不需要 Rust/C++ FFI。
2. 本地只跑“关键点感知模型”，不跑姿态决策/风险决策模型，符合“本地不使用决策 AI”的边界。
3. 33 个关键点足够做基准、头前伸、明显侧倾、不可判定四类；坐姿机位只用头肩 13 点，躯干前倾等扩展项后置。
4. 跨 Windows/macOS，演示机不需要额外原生依赖。
5. MediaPipe 的 WASM 与 `pose_landmarker.task` 模型文件随客户端本地打包，不走 CDN，断网也能启动。

**备选：MindSpore Lite。**

- 优点：更贴华为技术栈，答辩叙事更强。
- 代价：Windows/Tauri 需要 C++/Rust FFI、模型转换与算子兼容验证，11.13 前风险高。
- 触发条件：如果学校/赛题明确要求“端侧必须用华为推理框架”，或 MediaPipe 在演示机性能不达标，再切 MindSpore Lite；代码上用 `PostureExtractor` 接口隔离，不把 MediaPipe 写死到业务层。

**关键澄清：**

> “本地不使用任何 AI 模型”应表述为“本地不运行姿态决策/风险决策模型”。  
> 关键点提取本身就是轻量感知模型（MediaPipe / MindSpore Lite），否则普通 RGB 摄像头无法直接输出头肩关键点。README 和答辩必须把这句话说清楚。

### 姿态模型 v1（2026-11-23，特征契约 v2；历史）

| 项 | 现状 |
|---|---|
| 训练包 | `scripts/modelarts/`：数据校验 → 训练 → 独立评估 → 部署脚本，全部可复跑 |
| 输入 | 33 点归一化关键点；模型只吃 5 个派生特征，端侧上传格式不变 |
| 特征 | `shoulder_tilt_deg`、`shoulder_width`、`shoulder_visibility`、`head_forward_ratio`、`upper_body_visibility` |
| 门控 | `shoulder_visibility ≥ 0.5` 且 `upper_body_visibility ≥ 0.5`；后者只统计头肩 13 点 |
| 模型 | A 版 5 特征 MLP（64→32，2,596 参数），四分类 `baseline` / `forward_head` / `lateral_tilt` / `undetermined` |
| 决策规则 | `argmax` 后 `confidence < 0.5` 改判 `undetermined`；训练、评估、serving 共用 `posture_runtime.decide_posture()` |
| 数据 | 1440 帧合成关键点 / 12 受试者 / seed 20261117 / 全部 `framing=upper_body`；标签 356 / 351 / 327 / 406 |
| 真实采集 | 14 名受试者 / 3,974 帧去重后带段落标签（2026-11-23–26）；四类 1,072 / 1,019 / 960 / 923；尚未进入正式训练 |
| 选型 | 同 seed 对比 5 维 A 与 137 维 B，按验证集 macro-F1 选 A（0.9831 vs 0.8867） |
| 离线指标 | 测试集 macro-F1 0.9670、accuracy 0.9667；低置信度改判 0 帧 |
| 报告 | `scripts/modelarts/reports/v1/`：`metrics.json`、`feature_spec.json`、`split.json`、`smoke_test.json`、混淆矩阵 |
| 端到端 | 本地 `serve.py` / `customize_service.Model` 冒烟通过；真实 ModelArts endpoint 未开通 |

机位口径：久坐人群面对笔记本摄像头时通常只有头部和双肩入画。v2 删除了依赖髋部的
`torso_lean_deg` 和按 33 点统计的 `visible_ratio`，不再要求全身可见；采集记录增加
`framing`（默认 `upper_body`），评估按机位分开统计。姿态能力边界仍是
“头颈前伸与肩部不对称识别”，不宣称能测其他部位。

版本关系：**当前特征契约 `v3`；v1 模型与 `reports/v1/` 仍是 `v2`**；`reports/v0/` 只作历史保留。三代指标不可直接比较，v3 尚未训练。指标只证明特征契约、训练与部署脚本可复现，**不代表真实场景准确率**；对外不得把 0.9670 写成模型准确率。权重与原始数据不入库。

### 特征契约 v3（2026-11-26）

| 项 | v3 |
|---|---|
| 派生特征 | 9 个：`shoulder_tilt_deg`、`shoulder_width`、`shoulder_visibility`、`upper_body_visibility`、`neck_ratio`、`head_offset_ratio`、`neck_ratio_delta`、`head_offset_delta`、`tilt_delta_deg` |
| 2D 几何 | `neck_ratio = (肩中点 y − 鼻 y) / 肩宽`；`head_offset_ratio = (鼻 x − 肩中点 x) / 肩宽` |
| 个人基线 | 采集时取 `label=baseline` 段落的中位数；请求可带 `baseline`，缺省回退总体中立值 `tilt=0`、`neck_ratio=0.65`、`head_offset=0` |
| 去掉 | z 轴 `head_forward_ratio`：真实数据 baseline 中位数 1.77、forward_head 1.84，p5–p95 完全重叠 |
| 同步范围 | `apps/cloud-api`、`scripts/modelarts/posture_contract.py`、`posture_runtime.py`、`label_policy.py`、`generate_synthetic_frames.py`、`collect_frames.py`、`dataset_check.py` 与测试 |
| 数据 | `data/posture/capture.jsonl` 已按 v3 重生成：3,974 帧 / 14 人 / 0 errors；合成数据也已重生成 |
| 模型 | **未训练**；v3 mock 只用 `|肩倾| ≥ 8°` 与 `−neck_ratio_delta ≥ 0.08` 验证链路，不能作为分类结果 |

**真实采集第一批（2026-11-26）：** 12 个 jsonl 共 4,934 条，`data (2).jsonl` 与
`data (3).jsonl` 字节级相同，去重后 3,975 帧；`collect_frames.py` 跳过 1 帧关键点越界，
`dataset_check` 对 3,974 帧给出 0 errors / 0 warnings。v3 重新转换后仍是 3,974 帧、0 errors。
格式可用，但标签执行与样本量还不足以训练发布模型：

- v2 的 `head_forward_ratio` 依赖 MediaPipe `z`：baseline 中位数 1.77、forward_head 1.84，
  p5–p95 完全重叠；99% 帧超过旧 mock 阈值 0.25。旧 mock 跑这 3,974 帧得到
  forward_head 3,188、lateral_tilt 784、baseline 2、undetermined 0，因此必须换特征。
- 跨受试者 LOSO 试算（HistGradientBoosting）：v2 的 5 特征 macro-F1 0.629；8 个 2D
  几何量 0.643；按个人 baseline 中位数归一后 0.755；137 维坐标 0.726。v3 采用
  2D 特征 + 基线偏差，离线试算仍不足以对外。
- 标签一致性：用 `neck_ratio`（鼻–肩中点垂直距离 / 肩宽）区分 baseline 与 forward_head，
  9 人 AUC ≥ 0.72；s02（0.658）、s19（0.688）偏弱；s03（0.032）反向；
  s01（0.518）、s20（0.491）几乎无分离。
- `undetermined` 主要是取景问题：肩宽中位数 0.147，其他类 0.52–0.54，更像质量类而非姿态类。
- 固定 70/15/15 划分在 14 人上只得到 2 人测试集，本轮正好落在 s03、s20；官方 MLP
  A 版 test macro-F1 0.429、B 版 0.589，A 版验证集 0.636。小样本应改用 LOSO 或
  重复分组，不能拿单次 2 人测试集当结论。

## 3. 端到端链路

```text
Tauri WebView
  getUserMedia → <video> → MediaPipe Pose Landmarker (WASM)
  → 归一化 33 关键点 → HTTPS POST /posture/infer
        │
        ▼
cloud-api（FastAPI）
  SafetyCheckMiddleware（文本红旗前置）
  → posture service
  → ModelArts adapter（mock | huawei）
  → 姿态分类 + 置信度 + 风险因子 + 证据 id
        │
        ▼
Tauri WebView
  姿态引导框 + 风险解释 + 免责声明
```

降级：

- 摄像头关闭/无权限 → 回退到 Rust 久坐计时，不给出姿态结论。
- 网络断开/ModelArts 超时 → 明确提示“云端不可用，已回退”，不伪造云端结果。
- 关键点置信度过低 → 返回 `undetermined`，不强行给姿态结论。

## 4. 数据契约（草稿）

> **2026-11-09 更新**：接口已实现为 `POST /posture/infer`。相对下方草稿收敛了两处：① 风险字段收进 `risk` 子对象，避免与姿态字段混层；② 新增 `source`（huawei/mock）与 `latency_ms`，用来在界面上如实标注推理来源。精确契约见文末“附录 A”。

请求：

```json
{
  "user_id": "uuid",
  "captured_at": "2026-11-13T10:00:00+08:00",
  "source": "mediapipe-pose-33",
  "frame": { "width": 1280, "height": 720 },
  "session": { "sitting_minutes": 45, "state": "S1" },
  "keypoints": [
    { "name": "nose", "x": 0.512, "y": 0.284, "z": -0.08, "visibility": 0.99 }
  ]
}
```

响应：

```json
{
  "posture": "baseline",
  "confidence": 0.86,
  "risk_index": 0.42,
  "risk_level": "medium",
  "factors": [
    { "code": "sitting_duration", "value": 45, "weight": 0.3, "evidence_ids": ["pmid-35147898"] },
    { "code": "lateral_tilt_duration", "value": 3, "weight": 0.2, "evidence_ids": [] }
  ],
  "guidance": {
    "message": "肩线轻微左倾，建议调整坐姿并做 2 分钟颈肩放松",
    "overlay": "baseline_guide"
  },
  "disclaimer": "本产品为健康行为指导工具，不提供医疗诊断或治疗建议。"
}
```

约束：

- 只传 33 个关键点的归一化坐标（0–1，保留 4 位小数）与可见度；不传像素、不传人脸特征。
- 只要求头部与双肩清晰入画，距离约 40–70 cm；不为拍全身而后退。采集记录带 `framing`，评估按机位分层。
- 服务端校验关键点数量、名称与顺序；缺项直接 422。
- 不在 info 日志打印关键点原始数组；只记录 `user_id`、姿态类别、置信度、耗时。
- 证据 id 必须能在 `data/knowledge/evidence.json` 中找到；没有证据的因子不写 `evidence_ids`，不编造。

## 5. 隐私与安全

- 摄像头开关默认关闭，开启时显示常驻指示；不录制、不缓存原始帧。
- 只上传关键点；HTTPS；服务端不落原始坐标，只落姿态摘要与风险结果。
- 用户可一键关闭摄像头并清除本机缓存。
- `safety-check` 仍覆盖文本类输入；姿态链路不替代红旗征筛查。
- 免责声明出现在摄像头页、姿态结果页与问答回答。

## 6. 11.13 验收清单

- [ ] Tauri 能打开摄像头，MediaPipe 在本地加载并输出 33 关键点。
- [ ] 演示机连续 60 秒 ≥15 fps，关键点不中断。
- [ ] 只上传关键点：抓包/日志检查无原始图像或视频。
- [x] ModelArts 在线推理可调用（无 endpoint 时用 mock，并在界面标注“mock”）——mock 全链路已实测；训练包 v1（特征契约 v2）与离线报告已完成，真实 endpoint 待开通。
- [ ] 客户端可显示“基准 / 头前伸 / 明显侧倾 / 不可判定”四类结果与引导框；只做基准线与局部调整提示，不做 3D/复杂动效。
- [ ] 关摄像头、断网、ModelArts 超时三种降级都能演示。
- [ ] 姿态页有免责声明与隐私开关。

## 7. 11.20 集成要点

- 时间持续性：姿态偏差持续 ≥N 秒才计入风险，避免单帧误判。
- 风险指数：久坐时长 + 姿态偏差时长 + 疼痛评分 + 红旗征，规则融合，权重可解释。
- S0–S3：姿态/风险作为输入，不替代状态机迁移；迁移仍由 `intervention-engine` 决定。
- 动作推荐、打卡、反馈闭环沿用现有 API 与 `data/actions/actions.json`；从姿态识别到动作推荐、完成反馈、记录保存全程跑通。
- 只持久化姿态摘要（类别、持续时长、风险因子），不持久化关键点原始序列；RDS/DCS 真实接线，不能用 mock 内存替代验收。
- 云端业务部署：ECS + FastAPI（或等效方式）提供稳定 API；`mock` 只用于本地联调，不作为“已上云”证据。
- 循证知识库：先人工审核 10–20 条 JSON 规则并展示来源；未审核的规则只能标“草稿/待审核”，不能对外宣称已获专业认可。
- 解释依据：风险因子 → 证据 id → `evidence.json`，前端可展开“为什么”。
- 喝水提醒、隐形训练等 P1 能力不阻塞 MVP；先保留已有能力或暂缓，不分散核心链路工时。

### 11.21–26 测试与封版

| 日期 | 内容 | 验收口径 |
|---|---|---|
| 11.21–22 | 集成测试、断网恢复、摄像头异常、API 超时、权限与隐私检查 | 断网/关摄像头/超时都能回退；抓包无原始画面；权限拒绝有提示 |
| 11.23–24 | 识别效果测试、不同用户与摄像头视角、端云延迟与传输量 | 至少 3 名用户、3 种视角；端到端延迟与单次上传字节数有记录 |
| 11.25 | 修复高优先级缺陷、更新界面与架构文档 | P0 缺陷清零；文档与实现一致 |
| 11.26 | 模拟比赛演示、录制完整运行视频、准备答辩材料 | 完整闭环可重复；视频可回放；答辩材料齐备 |
| 11.28–30 | 缓冲期、封版提交 | 代码/视频/文档冻结，不再改功能 |

## 8. 待确认

1. ModelArts endpoint：训练包、特征顺序与响应格式已定，缺账号下的在线服务与鉴权值；没有则继续 mock。
2. 姿态类别已冻结为四类：`baseline` / `forward_head` / `lateral_tilt` / `undetermined`；新增类别须先改 `PostureClass`、`feature_spec.json` 与两端测试。
3. 是否需要每人一次基线校准（不同摄像头角度/身高）。
4. 演示机性能目标：fps、端到端延迟、单次上传字节数。
5. 如果赛题强制华为端侧推理，MindSpore Lite 的 Windows/Tauri 集成是否有人力支持。
6. 首次真实 endpoint 调用要确认 ModelArts 传给 `customize_service._preprocess` 的请求体是裸 JSON 还是 `{"data": ...}` 包络；本地 `serve.py` 只验证了裸 JSON。

## 9. 实现状态（2026-11-08）

**已完成：**

- 端侧 spike：[PostureSpike.vue](../../apps/desktop-tauri/src/components/PostureSpike.vue)；由风险报告里的“检查我的姿势”按钮打开，不再使用悬浮 FAB。
- MediaPipe Pose Landmarker（lite, float16）本地加载；WASM 与模型随 `apps/desktop-tauri/public/` 打包，不走 CDN。
- 摄像头开关、33 关键点绘制、肩线倾角、基准/明显侧倾/不可判定三分类、FPS 与关键点数量显示。
- 已接 `POST /posture/risk`：每 2 秒把姿态类别/置信度/持续时长 + 久坐/疼痛/部位 + 方案偏好送到云端，返回 BRLI、风险等级、推荐方案、最多 3 个匹配动作与 `citations[]`；低风险不打断。
- 新增“风险与姿势报告”（InterventionCard 按钮下方，h2）：显示风险等级、BRLI、最近姿势/置信度、建议方案、最近风险姿势；不弹通知。
- 有风险姿势会记录到本机 `postureEvents`（high/very_high，5 分钟去重）；目前是本地记录，未接 RDS。
- 计时结束改为独立 [InterventionOverlay.vue](../../apps/desktop-tauri/src/components/InterventionOverlay.vue)：覆盖 content-pane，包含动作内容、倒计时进度条、摄像头画面、权威文字与反馈按钮。
- 系统通知点击 `tap` 通过 Tauri `on_action` 唤回主窗口；Windows 只在通知仍在屏幕时上报点击。
- `pnpm build` 通过；`dist/mediapipe/wasm` 与 `dist/models` 已包含运行资产。
- 隐私边界：默认不自动开摄像头；关闭即停止 track 并清空画布。

**未验证 / 待办（11-08 快照）：**

- 当前开发机摄像头被隐私锁遮挡，关键点识别未做真人验证；需在演示机现场用真人复核。
- `/posture/risk` 已接，但云端仍是 BRLI 规则融合，不是真实 ModelArts 推理；`/posture/infer` 已接适配层，真实模型待 endpoint。
- （11-08 时）端侧上传“分类特征”而非原始关键点序列；该契约已于 11-09 收敛为 33 点关键点，见 A.2。S0–S3 迁移尚未消费姿态风险。
- 当前环境（摄像头黑屏/后台窗口）FPS 偏低，需在演示机实测；目标 ≥15 fps。
- 11.13 剩余：ModelArts 真实推理、端云数据传输与返回结果可演示。

**2026-11-19 进展：**

- 训练包 v0 完成：6 特征 MLP、四分类、低置信度改判，报告在 `scripts/modelarts/reports/v0/`；`evaluate_posture.py` 复算 A/B/chosen 全部一致。
- `/posture/infer` 的 mock 全链路与本地 `serve.py` 冒烟均通过；144 个 Python 测试全绿。
- 仍未完成：真实 ModelArts endpoint、真实摄像头采集与人工标注、真实包络确认、线上 503/超时/断网回退实测。
- 合成数据指标只验证链路，不能作为泛化准确率或答辩效果数据。

**2026-11-23 采集链路验证：**

- `capture_webcam.py` 在 CPython 3.11 64 位 + MediaPipe 0.10.35 下跑通，
  用 FlyGues 虚拟摄像头（DirectShow 索引 1）采到 20 帧，`no_pose=0`。
- 契约修正：MediaPipe 对画面外关节会给外推坐标（坐姿腿部到 `y≈2.8`），
  `Keypoint` 边界由 `[-0.5,1.5]` 放宽到 `x/y ∈ [-2,4]`、`z ∈ [-4,4]`；
  超出按异常帧跳过，`collect_frames` 不再因单帧中断整批。
- 仍未完成：真实受试者采集、人工标注、真实 ModelArts endpoint。

**2026-11-23 特征契约 v2 / 模型 v1：**

- 删除 `torso_lean_deg` 与 `visible_ratio`，新增 `upper_body_visibility`（头肩 13 点）；
  门控改为 `shoulder_visibility` + `upper_body_visibility` 双阈值。
- 云 API、ModelArts 运行时副本、标注口径、训练/评估脚本同步到 v2；
  `FEATURE_SPEC_VERSION` 与 `POLICY_VERSION` 均为 `v2`，模型/报告为 `v1`。
- 合成数据改为头肩机位：髋腿放在画面外，1440 帧全部 `framing=upper_body`。
- 重训结果：A 版 5 维、2,596 参数，test macro-F1 0.9670、accuracy 0.9667；
  B 版 137 维 0.8432。报告在 `scripts/modelarts/reports/v1/`。
- 新增回归用例：只有头肩可见时仍能分类；头肩大部分不可见时判 `undetermined`。
- 仍未完成：真实 endpoint、真实采集与人工标注、线上链路复测。

**2026-11-26 真实采集第一批：**

- Tauri 采集页记录 14 名受试者、12 个 jsonl / 4,934 条；`data (2).jsonl` 与
  `data (3).jsonl` 字节级相同，去重后 3,975 帧，转换后 3,974 帧可训练。
- `dataset_check`：0 errors / 0 warnings；全部 `origin=capture`、`label_source=human`、
  `framing=upper_body`，四类 1,072 / 1,019 / 960 / 923。
- 官方训练脚本按 70/15/15 划分：10 人训练、2 人验证、2 人测试（s03、s20）；
  A 版 test macro-F1 0.429、B 版 0.589，A 版验证集 0.636。
- 试算结论：v2 的 `head_forward_ratio` 在真实画面无区分度；LOSO 约 0.63，按个人基线
  归一约 0.75。数据格式可用，但不能发布为模型准确率。
- 2026-11-26 特征契约 v3 落地：去掉 z 轴量，改为 2D 颈长比/头偏移 + 个人基线偏差；
  `data/posture/capture.jsonl` 已按 v3 重生成，`dataset_check` 0 errors。
- 仍未完成：v3 模型训练与 LOSO 复评、s01 / s03 / s20 重采、受试者扩到 ≥20、真实 endpoint。

## 10. 摄像头姿态：记录与报告（不弹通知）

### 记录规则

- 摄像头已开启，姿态类别为 `baseline` / `forward_head` / `lateral_tilt`，且置信度 ≥ 0.6；
- 同一异常姿态**连续 ≥30 秒**（可配 30–60 秒），单帧不记录；
- 结合 BRLI，只有 `high` / `very_high` 才写入“风险姿势记录”；
- 同一姿态/同一等级 5 分钟去重；姿态回到 `baseline` 持续 10 秒可解除；
- `undetermined` 不记录，只提示调整摄像头。

### 不记录 / 回退

- 摄像头关闭、权限拒绝、模型加载失败、断网 → 不记录，回退到计时提醒；
- 红旗征 → `safety-check` 403 + 就医提示，不走姿态记录；
- 用户正在执行动作/提交反馈 → 不打断，也不写记录；
- 记录只用于报告和后续评估，**不弹通知、不强制切屏**。

### 报告与查看

- InterventionCard 的“立即开始活动”按钮下方显示“风险与姿势报告”（h2）；
- 报告显示风险等级、BRLI、最近姿势与置信度、建议方案、最近 3 次风险姿势；
- “检查我的姿势”按钮手动打开摄像头面板；已取消悬浮 FAB；
- 风险报告与计时结束遮罩会展示 `data/knowledge/evidence.json` 解析出的权威来源。

### 隐私与合规

- 默认关闭摄像头；首次开启说明用途、数据范围、关闭方式；
- 只传归一化关键点/特征，不传原始画面；不录制、不落原始坐标；
- 日志不打印关键点数组；用户可一键关闭并清除本机缓存；
- 不用于医疗诊断，不替代红旗征筛查；未成年人场景需监护人知情。

### 体验

- 不弹通知打断，风险只在报告中呈现；
- 文案给一个可执行动作（如“肩线左倾，做 2 分钟颈肩放松”），不指责用户；
- 多人/背景干扰：只取画面中最大/最近的人；多人场景先限制为单人。

### 要观察的指标

- 误报率、风险记录后 5 分钟内动作完成率、关闭摄像头比例；
- 演示机 fps、端到端延迟、CPU 占用。

## 11. 关联文档

- `docs/architecture/cumulative-load.md`：BRLI 累积负荷公式、权重与风险分级。
- `docs/architecture/evidence-map.md`：风险因子与干预规则的证据边界。
- `data/knowledge/evidence.json`：39 条文献台账。
- `data/actions/actions.json`：动作库。
- `packages/intervention-engine`：S0–S3 状态机。

## 附录 A｜实现状态与 11.10 验证步骤（2026-11-09）

### A.1 已落地（本机实测）

| 项 | 状态 | 证据 |
|---|---|---|
| `POST /posture/infer` | 已实现 | 请求 33 点关键点 + 上下文；响应含姿态、置信度、来源、耗时、引导文案与 `risk` |
| ModelArts 适配层 | 已实现，mock/huawei 两种云端配置 | `apps/cloud-api/app/cloud/modelarts.py`；注册进 `CloudRegistry`，`/health/deps` 可见 |
| 关键点契约校验 | 已实现 | 数量或顺序不符直接 422；端云两份清单有跨语言一致性测试 |
| 云端不可用 | 显式降级 | ModelArts 失败返回 503 `modelarts_unavailable`，端侧切“端侧兜底”并提示，不伪造云端结论 |
| 姿态摘要落库（RDS） | 已实现 | `posture_summaries` 表：只存类别/置信度/偏差/风险/BRLI/时长/来源，**不存关键点**；同类默认 60 秒一条，类别变化立即写 |
| 实时缓存（DCS） | 已实现 | `posture:latest:{user_id}`，TTL 600s；同时作为写入节流的跨实例依据；DCS 不可用时退回进程内缓存 |
| 周报消费 | 已实现 | `/review/weekly` 新增 `posture` 块（样本数、主姿态、高风险占比）；高风险占比 ≥30% 时追加一条提示 |
| 本地资源 | 已打包，不走 CDN | `public/models/pose_landmarker_lite.task`（5.5 MB）、`public/mediapipe/wasm/*`（14.6 MB + 334 KB），本地 200 可访问 |
| 测试 | 155 passed | `python -m pytest -q`；前端 `pnpm build` 通过 |

真实 ModelArts endpoint 尚未开通（**需付费**），因此当前所有推理结果都带 `source: "mock"`，界面显示「演示模型」，不得对外表述为「已接入华为云推理」。

### A.2 请求/响应（实现后的精确契约）

请求：

```json
{
  "keypoints": [{ "name": "nose", "x": 0.5, "y": 0.30, "z": 0.0, "visibility": 0.99 }, "... 共 33 条"],
  "baseline": { "shoulder_tilt_deg": 0.0, "neck_ratio": 0.67, "head_offset_ratio": 0.0 },
  "source": "mediapipe-pose-33",
  "captured_at": "2026-11-09T12:30:00+08:00",
  "posture_duration_minutes": 2.5,
  "sitting_minutes": 50,
  "daily_sitting_minutes": 300,
  "minutes_since_last_break": 50,
  "pain_score": 3,
  "body_parts": ["neck"],
  "plan": "standard"
}
```

响应（200）：

```json
{
  "posture": "forward_head",
  "confidence": 0.95,
  "deviation_deg": 27.0,
  "source": "mock",
  "model": "riseloop-posture-v1-mock",
  "latency_ms": 0.01,
  "guidance": { "message": "检测到头前伸，收下巴并把屏幕上沿抬到视线高度。", "overlay": "align_guide", "disclaimer": "..." },
  "features": {
    "shoulder_tilt_deg": 0.0, "shoulder_width": 0.2, "shoulder_visibility": 0.98,
    "upper_body_visibility": 1.0, "neck_ratio": 0.40, "head_offset_ratio": 0.0,
    "neck_ratio_delta": -0.27, "head_offset_delta": 0.0, "tilt_delta_deg": 0.0
  },
  "risk": { "brli": 0.4862, "risk_level": "medium", "recommended_plan": "standard", "actions": ["..."], "factors": ["..."], "citations": ["..."] }
}
```

失败（503）：`{ "detail": { "error": "modelarts_unavailable", "reason": "timeout" } }`

### A.3 接真实 ModelArts 的剩余步骤

训练包已在 `scripts/modelarts/` 完成，剩下的是部署与联通：

1. **上传模型包**到 ModelArts 模型管理：`customize_service.py`、`posture_runtime.py`、`model.py`、`model.pt`、`feature_spec.json`；部署为在线服务（CPU、1 副本）。
2. **首次调用确认包络**：用一条真实请求确认 `customize_service._preprocess` 收到的是裸 JSON 还是 `{"data": ...}`。本地 `serve.py` 只验证了裸 JSON；若云端不同，在 `modelarts.py` 加一层包装，不改模型包。
3. **在 `apps/cloud-api/.env` 填**：`RISELOOP_CLOUD_PROVIDER=huawei`、`RISELOOP_MODELARTS_ENDPOINT`、`RISELOOP_MODELARTS_API_KEY`、`RISELOOP_MODELARTS_AUTH_HEADER`（`x-auth-token` / `authorization` / `x-api-key`）。
4. **响应解析**：模型包返回 `posture` / `confidence` / `probabilities`；`parse_prediction` 取前两者，兼容 `{"label", "confidence"}` 与概率表。
5. **验收**：`/posture/infer` 返回 `source=huawei`，`/health/deps` 显示 `modelarts.configured=true`，停服务后返回 503 且端侧显式降级。

### A.4 真人关键点验证（11.10，需人在镜头前）

前置条件本机已确认：Camera 设备 `Integrated Camera` 状态 OK；Windows 摄像头权限（用户级 + 机器级）均为 `Allow`；模型与 WASM 资源本地可访问。唯一剩下的阻塞是**物理层面**：摄像头挡板要打开，镜头前要坐人。

步骤（约 3 分钟）：

1. 打开摄像头物理挡板，正对镜头坐好，保证肩、头都在画面内。
2. 启动：项目根目录 `pnpm dev`（或 `pnpm tauri dev`）。
3. 在应用里点“检查我的姿势”，观察四个数值：
   - **关键点**应为 33（少于 33 或 0 = 未检测到人，先调光线/距离）；
   - **FPS** 目标 ≥ 15；
   - **推理来源**应为“华为云 ModelArts”或“mock 模型”；
   - **实时风险**在 2 秒内出现 BRLI 与推荐方案。
4. 做三个动作验证分类：正常坐 → “基准姿态”；肩一高一低 → “明显侧倾”；头前伸 → 云端返回“头前伸”。
5. 拔网线或停掉 cloud-api，确认提示「无法连接云服务」，且不出现任何编造的云端结论。

记录到验收表：fps、关键点数、单次上传字节数（约 33 × 5 字段 ≈ 1–2 KB）、端到端延迟。

### A.5 常驻监测与摄像头授权（2026-11-09 落地）

| 项 | 实现 |
|---|---|
| 授权入口 | 每次评估完成后弹 `m3e-dialog`（已开启监测时不打扰）；弹窗内带**实时预览**与设备名，多摄像头可直接切换并即时预览；选择结果写 `riseloop.posture.prefs.v1`，之后可从账号菜单「姿势监测设置」再打开 |
| 采样 | 常驻 `getUserMedia` 320×240，每 10 秒取一帧关键点 |
| 窗口 | 每 60 秒汇总：主导姿态、异常占比、估算偏差时长；只上报窗口代表帧的 33 点 |
| 云端节奏 | 每 60 秒一次 `/posture/infer`（此前为 2 秒一次） |
| 多摄像头 | 授权后 `enumerateDevices`；多于 1 个时弹窗内用 `m3e-select` 选择，可随时切换 |
| 摄像头独占 | 打开「姿势检查」面板时自动暂停常驻监测，面板关闭后恢复 |
| 后台节流 | 连续超过 3 个采样周期未执行采样 → 记一次缺口并丢弃当前窗口，不用残缺数据下结论 |
| 失败降级 | 权限拒绝、设备被占用、未找到设备分别给出不同提示；监测失败不影响久坐计时 |

未验证项：**真实摄像头下的端到端**（本机摄像头物理挡板仍未打开），以及多摄像头设备的实际切换。

### A.6 姿态模型 v1 部署包与验证（2026-11-23，特征契约 v2）

| 项 | 内容 |
|---|---|
| 模型包 | `customize_service.py`（torch 前向 + 日志）、`posture_runtime.py`（5 特征、`decide_posture`）、`model.py`、`model.pt`、`feature_spec.json` |
| 关键点边界 | `x/y ∈ [-2,4]`、`z ∈ [-4,4]`，与服务端 `Keypoint` 一致；坐姿腿部外推坐标不会被拒 |
| 决策规则 | `argmax`，`confidence < 0.5` 输出 `undetermined`；训练、评估、serving 共用同一函数 |
| 离线复跑 | `generate_synthetic_frames.py` → `dataset_check.py` → `train_posture.py` → `evaluate_posture.py`，命令见 `scripts/modelarts/README.md` |
| 本机冒烟 | `customize_service.Model` 对 `s01-000000` 返回 `forward_head` / `0.9862`，与样本标签一致；日志不含关键点数组 |
| 测试 | `python -m pytest -q`：155 passed（含决策规则、生成器跨 hash seed 复现、采集链路、头肩受限视野回归） |
| 未完成 | 真实 endpoint 未创建；未上传模型包；未用真实摄像头数据复评 |

