<p align="center">
  <img width="100" height="100" alt="Rise Loop" src="./apps/desktop-tauri/src-tauri/icons/appIcon.png" />
</p>

<h1 align="center">Rise Loop</h1>

<p align="center">
  <strong>基于华为云的智能久坐健康管理系统</strong><br />
  状态机驱动的久坐行为干预：感知久坐 → 推送最短有效动作 → 采集反馈 → 自动迁移状态
</p>

<p align="center">
  第十一届华为 ICT 大赛 · 中国创新赛 · 赛题 1<br />
  上海体育大学 · 起而行之队
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python" />
  <img src="https://img.shields.io/badge/Tauri-2-orange" alt="Tauri" />
  <img src="https://img.shields.io/badge/Vue-3-42b883" alt="Vue" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License" />
</p>

久坐是学习与办公场景中的高频健康风险，但现有提醒工具大多只是固定间隔弹窗：不判断用户当前状态，不决定“做什么、做多久”，也没有反馈后的下一次。

Rise Loop 面向久坐肩颈不适人群，只解决“坐太久、不知道怎么动”这一件事。系统用有限状态机管理干预：感知久坐后，按当前状态匹配一个最短有效动作；用户完成后提交感受、完成度与阻碍，状态机自动决定升级、回退、降级或安全短路。

> 本产品是健康行为指导工具，不提供医疗诊断或治疗建议。

## 界面

以下截图来自当前客户端界面与真实操作流程，不是设计稿。

| 状态评估 | 久坐计时 |
| :---: | :---: |
| <img src="docs/submission/public/assessment.png" width="100%" alt="状态评估" /> | <img src="docs/submission/public/dashboard.png" width="100%" alt="久坐计时与姿势风险" /> |
| **状态评估**<br>每日久坐、单次可用时长、不适部位与疼痛评分，作为状态机的初始输入。 | **久坐计时**<br>45 分钟阈值、到点提醒；姿势与风险并列展示当前 BRLI 与建议方案。 |

| 动作 | 完成反馈 |
| :---: | :---: |
| <img src="docs/submission/public/action.png" width="100%" alt="动作页" /> | <img src="docs/submission/public/feedback.png" width="100%" alt="完成反馈" /> |
| **动作**<br>按状态与可用时间匹配单条动作，给出步骤、计时与工位可做标记。 | **完成反馈**<br>完成度、主观感受、跳过原因与疼痛评分，全部进入下一次迁移。 |

| 状态迁移 | 近 7 天 |
| :---: | :---: |
| <img src="docs/submission/public/result.png" width="100%" alt="状态迁移" /> | <img src="docs/submission/public/weekly.png" width="100%" alt="近 7 天周报" /> |
| **状态迁移**<br>真实 S0 → S1：完成 2 次、评分 ≤3、次日无加重，展示下一动作。 | **近 7 天**<br>完成率 100%、活动 4 次、疼痛趋势“平稳”、安全中断 0。 |

## 核心机制

### 四状态闭环

| 状态 | 名称 | 进入条件 | 单条时长 | 退出条件 |
| :--- | :--- | :--- | :--- | :--- |
| S0 | 急性缓解 | 明显酸痛或主动报告不适 | ≤2 分钟 | 完成 2–3 次、评分 ≤3、次日无加重 → S1 |
| S1 | 激活 | S0 已完成 | 2–3 分钟 | 连续完成 ≥5 次 → S2 |
| S2 | 强化 | S1 稳定 | 5–8 分钟（一轮 2–3 条合计） | 连续完成 ≥10 次 → S3 |
| S3 | 维持 | S2 完成或进入稳定期 | 2–3 分钟 | 长期维持；异常时回退 |

迁移函数必须显式返回 `transition_type`：

- `upgrade`：满足当前阶段退出条件，升级到下一状态；
- `rollback`：连续 2 次症状加重，回退一级并缩短单次时长；
- `degrade`：连续 3 次跳过或“没感觉”且无加重，不降状态，换更短、更低强度的动作；
- `short_circuit`：命中红旗信号，立即回到 S0、停止运动推荐并提示就医；
- `hold`：条件不足，保持原状态。

久坐阈值默认 45 分钟，可配置为 30–60 分钟；同一用户 10 分钟内不重复推送。每次迁移记录 `from_state`、`to_state`、`reason`、`transition_type` 与时间戳。

### 相比固定间隔提醒

| 维度 | 固定间隔提醒 | Rise Loop |
| :--- | :--- | :--- |
| 触发逻辑 | 计时器到点即弹通知 | 久坐感知 + 当前状态共同决策 |
| 动作匹配 | 无，或随机推荐 | 按不适部位、可用时间、当前状态匹配最短有效动作 |
| 反馈闭环 | 无 | 完成度、感受、疼痛与阻碍进入下一次迁移 |
| 风险控制 | 无 | 8 类红旗先于推荐被拦截，停止运动并引导就医 |
| 计划维护 | 依赖用户自选 | 状态机自动迁移，不要求用户维护计划 |

## 项目特点

**状态机即产品逻辑。** 迁移规则是纯函数，不访问数据库、网络与文件；同一输入必得同一输出。迁移只在云端 `intervention-engine` 执行，端侧不实现迁移。四状态、四分支与 `hold` 均有表驱动单测，Python 与 JS 两套实现做 25 个场景的全字段对拍。

**头肩机位就够用。** 端侧 MediaPipe 只提取 33 个归一化关键点，云端重算 9 个公开 2D 特征：肩线倾角、肩宽、肩可见度、上体可见度、颈长比、头偏移，以及相对个人中立位的 3 个偏差；模型内部再使用 7 个头部几何 delta（耳宽/肩宽等），共 16 维输入。只要求头部与双肩入画，适配笔记本摄像头，不要求全身；原始画面不出本机。

**风险可解释。** BRLI 将姿态、连续久坐、恢复行为与症状负荷按权重融合为 0–1 的负荷分数，每个因子都能回溯到证据台账（39 条，PubMed 36 / WHO 1 / CDC 1 / NIOSH 1）。BRLI 只做行为风险提示，不替代红旗筛查。

**安全先于推荐。** `safety-check` 是 `cloud-api` 的强制中间件，位于 Agent、状态机与动作库之前。命中放射痛、麻木加重、眩晕、下肢无力、踩棉花感、大小便异常、会阴麻木、外伤后剧痛等红旗时，返回 403 语义、停止运动推荐并给出就医提示，任何推荐链路都无法绕过。

## 系统架构

```text
Tauri 2 + Vue 3 / Rust
  计时 · 托盘 · 原生通知 · Keychain
            │ HTTPS + JWT
cloud-api  FastAPI
  鉴权 · 限流 · safety-check · 路由编排
            │
intervention-engine
  纯函数状态迁移 · 无 IO · 四分支 + hold
            │
华为云  RDS 事实数据 · DCS 实时状态 · ModelArts 姿态推理
```

| 层 | 组件 | 职责 | 状态 |
| :--- | :--- | :--- | :--- |
| 桌面端 | Tauri 2 + Vue 3 + Rust | 界面、久坐计时、托盘、系统通知、Keychain；不保存状态机，不执行迁移 | ✅ 已实现 |
| 接入层 | `apps/cloud-api` | JWT、限流、安全中间件、评估/久坐时间/反馈/姿态/周报/问答路由 | ✅ 已实现 |
| 决策层 | `packages/intervention-engine` | 四状态迁移纯函数，唯一状态迁移入口 | ✅ 已实现 |
| 事实数据 | RDS for PostgreSQL | 用户、评估、迁移历史、执行记录、动作库、问答日志、安全事件 | ✅ 已接入（2026-11-28） |
| 实时状态 | DCS for Redis | 会话、久坐计时、待响应干预、安全短缓存 | ✅ 已接入（2026-11-28） |
| 姿态推理 | ModelArts 在线服务 | 33 点 → 2D 特征 + 个人基线 → 四分类；2.5 秒超时降级 | ✅ v3 head A 版已部署（2026-11-28），实测 `source=huawei`；精度仅内部评估 |
| 工具与技能 | MCP Server + Skills | 3 个固定工具、4 个平台无关 Skill，不直连数据库 | ✅ 已实现 |
| 部署 | 华为云 ECS + Docker Compose | 公网 API、镜像与编排清单 | ✅ 已部署（2026-11-28，HTTP 测试期） |
| 加密与分发 | KMS + OBS | 健康字段加密、安装包与演示材料分发 | 🟡 OBS 已用于模型包；KMS 未接线 |
| 研发工具 | 华为云 CodeArts | 需求拆解、代码生成、构建与问题修复 | ✅ 研发期使用，不进运行时 |

MCP 工具固定为 3 个：`read_realtime_state`、`get_actions_by_state`、`write_intervention_result`。Skill 为姿态评估、状态机、安全与问答四个，作为平台无关资产交付，主链路不依赖 Agent 编排。

本项目只提供云端模式；`packages/local-engine` 仅作内部测试对拍资产，不随客户端交付，也不出现在界面与评审材料中。

## 数据与模型

真实采集第一批已完成：2026-11-23 至 11-26，Tauri 采集页记录 14 名受试者、去重后 3,974 帧带段落标签的关键点（原始 4,934 帧，其中一份文件重复 959 帧；转换时 1 帧关键点越界被跳过），四类为 baseline 1,072 / forward_head 1,019 / lateral_tilt 960 / undetermined 923，全部 `origin=capture`、`label_source=human`、`framing=upper_body`，不含画面字段。这批数据已按特征契约 v3 重新生成到 `data/posture/capture.jsonl`，`dataset_check` 为 0 errors / 0 warnings。

当前离线训练包仍是 v1（特征契约 v2），使用 1,440 帧合成关键点，来自 12 名受试者、4 种设备 × 5 种场景；按受试者划分训练/验证/测试为 960 / 240 / 240 帧，四类标签为 356 / 351 / 327 / 406。

v1 模型输入 5 个派生特征，结构为 64 → 32 的 MLP，共 2,596 个参数。该合成训练包的测试集 macro-F1 0.9670、accuracy 0.9667，四类 F1 为 0.974 / 0.962 / 0.992 / 0.940，本机单帧推理 0.3–0.5 ms；置信度低于 0.5 判为 `undetermined`。这些指标只对应 v2 合成数据，不能写成 v3 或真实场景准确率。

特征契约 v3 去掉 z 轴 `head_forward_ratio`，改用 2D 颈长比、头偏移与每人中立位基线偏差；模型内部再加 7 个头部几何 delta。v3 head 内部 LOSO 已完成（14 人逐个留出）：A 版 16 维、3,300 参数，out-of-fold macro-F1 0.7759、accuracy 0.7765；每类 F1 为 baseline 0.763 / forward_head 0.714 / lateral_tilt 0.787 / undetermined 0.839。B 版 148 维为 0.7722，部署包按 A 版。只有 14 人、单一设备/场景，不能当作对外准确率；报告在 `scripts/modelarts/reports/v3-loso-head/`。v3 已部署到 ModelArts（2026-11-28），推理超时或失败时客户端不展示姿态结论，也不伪造结果。

## 工程验证

| 项目 | 结果 |
| :--- | :--- |
| 状态机 | 4 状态 × 4 分支 + `hold`；25 个 Python / JS 跨语言场景全字段对拍 |
| 自动化测试 | 167 项 Python 测试、21 项 Rust 测试、12 项 api-client 测试通过；`pnpm build` 通过 |
| 动作库 | 15 条动作覆盖四状态，单条 1–3 分钟；S2 一轮 2–3 条、合计 5–8 分钟 |
| 安全 | 8 类红旗短路；高风险在中间件层拦截，返回 403 与就医提示 |
| 接口 | 登录限流 10 次/60 秒，业务 120 次/60 秒；JWT access 1 小时、refresh 30 天，支持轮换与 jti 吊销 |
| 资产 | 3 个 MCP 工具、4 个 Skill；Skill 不直连数据库 |

## 快速开始

### 环境要求

- Python 3.11+
- Node 20+
- pnpm 11
- Rust 1.77+

### 安装依赖

```bash
pnpm install
pip install -e packages/intervention-engine -e apps/cloud-api
```

### 本地开发

```bash
# 启动本地后端并拉起客户端
pnpm demo

# 只启动客户端（先确保后端在 8000）
pnpm tauri dev
```

### 手动分离启动

```bash
cp apps/cloud-api/.env.example apps/cloud-api/.env

# 启动后端
uvicorn app.main:app --app-dir apps/cloud-api --reload --port 8000

# 启动前端
pnpm dev
```

客户端默认连接 `http://127.0.0.1:8000`；也可在构建或启动前用 `VITE_API_BASE` 指向云端。2026-11-28 已部署测试环境（`http://<ECS 公网 IP>:8000`，HTTP 测试期），实测配置见 `infra/huawei-cloud/deployed-config.md`。`mock` 模式只用于本地没有云资源时的联调，不作为上云证据。

### 打包桌面端

打包前必须先指定云端地址，否则构建直接失败——避免打出一个只能连本机的空壳安装包：

```powershell
$env:VITE_API_BASE="http://<ECS 公网 IP>:8000"; pnpm tauri build
```

产出免安装单文件 `apps/desktop-tauri/src-tauri/target/release/rise-loop.exe`。目标机需要 WebView2 运行时；Windows 11 自带，Windows 10 一般随 Edge 预装。

只做本机联调包时显式放行：`$env:ALLOW_LOCAL_API="1"`。地址也可以写在 `apps/desktop-tauri/.env.production`，构建日志会打印最终生效的地址。

## 测试与部署复现

```bash
pnpm test            # 状态机 + cloud-api + MCP
pnpm test:engine     # 状态机
pnpm test:api        # Cloud API
pnpm build           # 前端构建校验
cd apps/desktop-tauri/src-tauri && cargo test
```

构建并启动（云主机上用 Docker Compose）：

```bash
cd infra/docker
cp env.example .env          # 填 DSN / Redis URL / JWT secret
docker compose -f docker-compose.cloud.yml up -d
curl http://127.0.0.1:8000/health/deps
```

云服务接入与验证步骤见 [`infra/huawei-cloud/README.md`](infra/huawei-cloud/README.md)。

## 目录结构

```text
RiseLoop/
├── apps/
│   ├── cloud-api/           # FastAPI 网关：鉴权、限流、安全中间件、迁移编排
│   └── desktop-tauri/       # Tauri 2 + Vue 3 瘦客户端
├── packages/
│   ├── intervention-engine/ # 云端状态机纯函数
│   ├── local-engine/        # 本地演示状态机（不发起网络请求）
│   └── api-client/          # Tauri 调用云端 API
├── services/
│   ├── mcp-servers/         # 两个 MCP Server（合计 3 个工具）
│   ├── skills/              # 4 个平台无关 Skill
│   └── agent-orchestrator/  # 可选 Agent 编排资产
├── infra/                   # Docker、华为云清单、SQL 迁移
├── data/                    # 动作库、知识库与证据台账
├── docs/
│   ├── architecture/        # 架构、证据映射、姿态管线
│   ├── api/                 # 接口契约
│   ├── demo/                # 演示流程与现场兜底
│   └── submission/          # PPT、作品信息表、演示视频、README 截图
├── PRD.md
└── README.md
```

## 项目材料

| 材料 | 路径 |
| :--- | :--- |
| 作品介绍 PPT | [`docs/submission/RiseLoop-作品介绍.pptx`](docs/submission/RiseLoop-作品介绍.pptx) |
| 作品信息收集表 | [`docs/submission/作品信息收集表.docx`](docs/submission/作品信息收集表.docx) |
| 产品流程演示视频 | [`docs/submission/RiseLoop-产品流程演示视频.mp4`](docs/submission/RiseLoop-产品流程演示视频.mp4) |
| 界面截图 | [`docs/submission/public/`](docs/submission/public/) |

## 技术文档

| 文档 | 内容 |
| :--- | :--- |
| [PRD.md](PRD.md) | 需求唯一来源：四状态机、迁移规则、验收标准 |
| [docs/architecture/huawei-cloud-integration.md](docs/architecture/huawei-cloud-integration.md) | 华为云适配层与 mock/huawei 切换 |
| [docs/architecture/evidence-map.md](docs/architecture/evidence-map.md) | 参数/BCT 与文献证据的映射，含支撑强度与边界 |
| [docs/architecture/posture-pipeline.md](docs/architecture/posture-pipeline.md) | 端云姿态感知、模型指标、数据契约、隐私与降级 |
| [docs/architecture/cumulative-load.md](docs/architecture/cumulative-load.md) | 久坐累积负荷 BRLI：公式、权重、风险分级与实现状态 |
| [docs/api/README.md](docs/api/README.md) | 接口契约与调用示例 |
| [docs/demo/demo-mode.md](docs/demo/demo-mode.md) | 演示流程：云端链路、现场步骤与录屏兜底 |

## 安全声明

本产品为健康行为指导工具，不提供医疗诊断或治疗建议。

出现放射痛、麻木加重、眩晕、下肢无力、踩棉花感、大小便异常、会阴麻木或外伤后剧痛时，系统会立即停止运动推荐。**此时请立即前往正规医疗机构就医。**

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。
