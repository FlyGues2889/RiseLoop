<p align="center">
  <img width="100" height="100" alt="appIcon" src="https://github.com/user-attachments/assets/0e1c0e36-9ebb-4f14-ada9-4752b2f02970" />
</p>

<h1 align="center">Rise Loop</h1>

<p align="center">
  <strong>状态机驱动的久坐行为干预系统</strong><br />
  感知久坐 → 按当前状态推送最短有效动作 → 采集反馈 → 自动迁移状态
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python" />
  <img src="https://img.shields.io/badge/Tauri-2-orange" alt="Tauri" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License" />
</p>


<p align="center">
  <img src="docs/assets/demo.gif" alt="Rise Loop 演示" width="640" />
</p>



久坐是现代办公人群的普遍健康风险因素，但现有的提醒工具大多采用固定间隔（如每 45 分钟弹一次通知），忽略了用户的身体状态差异和实际可用性。

用有限状态机收口干预逻辑——感知久坐后，根据当前状态（急性缓解 / 激活 / 强化 / 维持）自动匹配最短有效动作，采集反馈后迁移状态，形成闭环。不做功能堆砌，只解决「坐太久、不知道怎么动」这一件事。

---

## ✨ 核心功能与创新点

### 四状态闭环

```
S0 急性缓解 → S1 激活 → S2 强化 → S3 维持
         ↑           ↑          │
         └───────────┴──────────┘
              回退 / 降级
```

- **升级**：用户完成当前阶段动作且反馈良好，自动进入下一阶段；
- **回退**：反馈疼痛或不适，退回上一状态；
- **降级**：长时间未完成动作，状态回落；
- **安全短路**：出现放射痛、麻木加重、眩晕、下肢无力等红旗信号，立即跳转 S0 并停止运动推荐。

### 相比固定间隔提醒的改善

| 维度 | 固定间隔提醒 | Rise Loop |
| :--- | :--- | :--- |
| 触发逻辑 | 计时器到期即弹通知 | 状态机根据久坐感知 + 当前状态决策 |
| 动作匹配 | 无或随机推荐 | 按不适部位、可用时间、当前状态匹配最短有效动作（2-8 分钟） |
| 反馈闭环 | 无 | 采集用户反馈后自动迁移状态 |
| 风险控制 | 无 | 红旗信号触发安全短路，停止推荐并引导就医 |
| 用户自选计划 | 需要 | 无需，状态机自动迁移 |

### 其他核心能力

- **状态机收口**：迁移逻辑为纯函数，无网络、无数据库；端侧与 API 层均不实现迁移，保证可测试性与可审计性。
- **云端智能**：华为云 CodeArts 双 Agent + Skill + 3 个 MCP 工具；知识库问答带引用，无命中不编造。
- **周度复盘**：完成率、疼痛趋势、迁移次数、阻碍分布与规则化建议；云端由 API 聚合，本地模式由端侧按同一口径计算。
- **双模式运行**：本地模式由 `packages/local-engine` 纯端侧运行并持久化到 localStorage，无云资源也能完整跑通。
- **PC 瘦客户端**：Tauri 2 + Vue 3，调用系统原生通知提醒用户。
- **系统亮暗色**：跟随操作系统亮/暗色，首屏预应用主题，避免暗色系统下的白闪。

---

## 🏗️ 系统架构

<!-- TODO: 替换为实际架构图路径；建议用 Mermaid 或 draw.io 绘制 -->
<p align="center">
  <img src="docs/assets/architecture.png" alt="系统架构图" width="720" />
</p>

### 华为云技术栈

| 组件 | 华为云服务 | 实现状态 |
| :--- | :--- | :--- |
| 智能体编排 | CodeArts Agent（双 Agent） | ✅ 已实现 |
| 技能层 | CodeArts Skill | ✅ 已实现 |
| 工具调用 | MCP Server（3 个固定工具） | ✅ 已实现 |
| 知识库 | CodeArts 知识库 | ✅ 已实现 |
| 后端网关 | FastAPI（鉴权、安全中间件、迁移编排） | ✅ 已实现 |
| 桌面客户端 | Tauri 2 + Vue 3 | ✅ 已实现 |
| 容器部署 | 容器镜像 + 云部署清单 | ✅ 已实现 |
| 数据库 | SQL 迁移脚本 | ✅ 已实现 |

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Node 20+
- pnpm 11
- Rust 1.77+（仅桌面端需要）

### 安装依赖

```bash
pnpm install

pip install -e packages/intervention-engine -e apps/cloud-api
```

### 本地开发

```bash
# 云端模式：自动起 mock 后端并拉起客户端
pnpm demo

# 仅客户端（本地模式）：登录页可直接进入「本地模式」，无需任何后端
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

客户端默认端口：`http://127.0.0.1:8000`

### 打包桌面端

```bash
pnpm tauri build
```

---

## 🧪 测试与部署复现

### 全量测试

全仓测试：状态机 + cloud-api + MCP
```bash
pnpm test
```

单独跑各模块
```bash
pnpm test:engine    # 状态机
pnpm test:api       # Cloud API
```
前端构建校验
```bash
pnpm build
```
Rust 端测试
```bash
cd apps/desktop-tauri/src-tauri && cargo test
```

### 部署复现

构建容器镜像

```bash
docker build -t riseloop-api -f infra/docker/Dockerfile .
```
部署
```bash
kubectl apply -f infra/k8s/
```

---

## 📁 目录结构

```
RiseLoop/
├── apps/
│   ├── cloud-api/          # FastAPI 网关（鉴权、安全中间件、迁移编排）
│   └── desktop-tauri/      # Tauri 2 + Vue 3 客户端
├── packages/
│   ├── intervention-engine/ # 状态机纯函数（迁移逻辑核心）
│   └── local-engine/        # 本地模式引擎（端侧运行 + localStorage）
├── services/
│   ├── mcp-servers/         # 两个 MCP Server（合计 3 个工具）
│   ├── skills/              # CodeArts Skill
│   └── agent-orchestrator/  # CodeArts 双 Agent 与工作流
├── infra/                   # 容器镜像、云部署清单、SQL 迁移
├── data/                    # 动作库、知识库与证据台账
├── docs/                    # 技术文档（含证据映射）
├── PRD.md                   # 需求唯一来源
└── README.md
```

---

## 📚 技术文档

| 文档 | 内容 |
| :--- | :--- |
| [PRD.md](PRD.md) | 需求唯一来源：四状态机、迁移规则、验收标准 |
| [docs/architecture/huawei-cloud-integration.md](docs/architecture/huawei-cloud-integration.md) | 华为云适配层、双模式设计 |
| [docs/architecture/evidence-map.md](docs/architecture/evidence-map.md) | 参数/BCT 与文献证据的映射，含支撑强度与边界 |
| [docs/architecture/posture-pipeline.md](docs/architecture/posture-pipeline.md) | 11.10 路线决策：端云姿态感知、数据契约、隐私与降级 |
| [docs/architecture/cumulative-load.md](docs/architecture/cumulative-load.md) | 久坐累积负荷 BRLI：公式、权重、风险分级与实现状态 |
| [docs/api/README.md](docs/api/README.md) | 接口契约与调用示例 |
| [docs/demo/demo-mode.md](docs/demo/demo-mode.md) | 本地模式说明：入口、能力边界、数据存储 |

---

## 🔒 安全声明

本产品为 **健康行为指导工具** ，不提供医疗诊断或治疗建议。

出现放射痛、麻木加重、眩晕、下肢无力等情况时，系统会立即停止运动推荐。**此时请立即前往正规医疗机构就医。**

---

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。