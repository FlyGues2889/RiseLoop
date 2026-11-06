# SitLoop

**状态机驱动的久坐行为干预系统。**

感知久坐 → 按当前状态推送最短有效动作 → 采集反馈 → 自动迁移状态。华为云智能核心 + Tauri 瘦客户端，不做功能堆砌，只解决「坐太久、不知道怎么动」这一件事。

## 特点

- **四状态闭环**：S0 急性缓解 / S1 激活 / S2 强化 / S3 维持，升级、回退、降级、安全短路四分支自动迁移，无需用户自选计划。
- **最短有效动作**：按不适部位、可用时间与当前状态匹配动作，单次 2–8 分钟。
- **安全前置**：所有推荐强制经过 `safety-check`，命中红旗症状立即停止推荐并提示就医。
- **状态机收口**：迁移逻辑为纯函数，无网络、无数据库；端侧与 API 层不实现迁移。
- **云端智能**：CodeArts 双 Agent + Skill + 3 个固定 MCP 工具；知识库问答带引用，无命中不编造。
- **周度复盘**：完成率、疼痛趋势、迁移次数、阻碍分布，一次请求返回。
- **瘦客户端**：Tauri 2 + Vue 3（JavaScript），Rust 负责计时、托盘、原生通知、Keychain。
- **双模式运行**：华为云适配层支持 `mock` / `huawei`，无云资源也能完整跑通。

## 使用

### 环境

Python 3.11+、Node 20+、pnpm 11、Rust 1.77+（仅桌面端）。

```bash
pnpm install
pip install -e packages/intervention-engine -e apps/cloud-api
```

### 启动

```bash
pnpm demo        # 推荐：自动起 mock 后端并拉起客户端，数据只存本机内存
```

手动分离启动：

```bash
cp apps/cloud-api/.env.example apps/cloud-api/.env
uvicorn app.main:app --app-dir apps/cloud-api --reload --port 8000
pnpm dev         # 开发模式
pnpm tauri build # 打包桌面端
```

客户端默认连 `http://127.0.0.1:8000`，线上地址通过 `VITE_API_BASE` 注入。

### 测试

```bash
pnpm test        # 全仓：状态机 + cloud-api + MCP
pnpm test:engine
pnpm test:api
pnpm build       # 前端构建校验
cd apps/desktop-tauri/src-tauri && cargo test
```

## 文档

| 文档 | 内容 |
| --- | --- |
| **[PRD.md](PRD.md)** | 需求唯一来源：四状态机、迁移规则、验收标准 |
| **[AGENTS.MD](AGENTS.MD)** | 架构红线、目录约束、开发顺序 |
| **[docs/architecture/huawei-cloud-integration.md](docs/architecture/huawei-cloud-integration.md)** | 华为云适配层、双模式设计 |
| **[docs/api/README.md](docs/api/README.md)** | 接口契约与调用示例 |
| **[docs/demo/demo-mode.md](docs/demo/demo-mode.md)** | 演示模式边界与启动方式 |

## 结构

```text
apps/desktop-tauri   Tauri 2 + Vue 3 客户端
apps/cloud-api       FastAPI 网关（鉴权、安全中间件、迁移编排）
packages/            状态机纯函数、API 客户端
services/            MCP Server（3 工具）、Skill、CodeArts Agent
infra/               容器、云部署清单、SQL 迁移
data/                动作库与种子数据
```

## 边界

本产品为健康行为指导工具，不提供医疗诊断或治疗建议。出现放射痛、麻木加重、眩晕、下肢无力、踩棉花感、大小便异常、会阴麻木或外伤后剧痛时，系统立即停止运动推荐并提示就医。