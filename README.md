<center>
  <img width="100" height="100" alt="appIcon" src="https://github.com/user-attachments/assets/0e1c0e36-9ebb-4f14-ada9-4752b2f02970" />
</center>

# SitLoop

**状态机驱动的久坐行为干预系统。**

感知久坐 → 按当前状态推送最短有效动作 → 采集反馈 → 自动迁移状态。华为云智能核心 + Tauri 瘦客户端，不做功能堆砌，只解决「坐太久、不知道怎么动」这一件事。

> ### 健康指导提示
> 
> 本产品为健康行为指导工具，不提供医疗诊断或治疗建议。出现放射痛、麻木加重、眩晕、下肢无力等情况时，系统会立即停止运动推荐。
> 此时请您立即前往正规医疗机构就医。

## 特点

- **四状态闭环**：S0 急性缓解 / S1 激活 / S2 强化 / S3 维持，升级、回退、降级、安全短路四分支自动迁移，无需用户自选计划。
- **最短有效动作**：按不适部位、可用时间与当前状态匹配动作，单次 2–8 分钟。
- **状态机收口**：迁移逻辑为纯函数，无网络、无数据库；端侧与 API 层不实现迁移。
- **云端智能**：CodeArts 双 Agent + Skill + 3 个固定 MCP 工具；知识库问答带引用，无命中不编造。
- **周度复盘**：完成率、疼痛趋势、迁移次数、阻碍分布与规则化建议；云端由 API 聚合，本地模式由端侧按同一口径计算。
- **PC 瘦客户端**：调用系统原生通知提醒用户。
- **双模式运行**：本地模式由 `packages/local-engine` 纯端侧运行并持久化到 localStorage，无云资源也能完整跑通；个人菜单提供二次确认的「清除数据」。

## 使用

### 环境

Python 3.11+、Node 20+、pnpm 11、Rust 1.77+（仅桌面端）。

```bash
pnpm install
pip install -e packages/intervention-engine -e apps/cloud-api
```

### 本机启动

```bash
pnpm demo        # 云端模式开发：自动起 mock 后端并拉起客户端
pnpm tauri dev   # 仅客户端：登录页可直接进入「本地模式」，无需任何后端
```

手动分离启动：

```bash
cp apps/cloud-api/.env.example apps/cloud-api/.env

uvicorn app.main:app --app-dir apps/cloud-api --reload --port 8000

pnpm dev
```

打包桌面端：
```
pnpm tauri build
```

客户端默认端口： `http://127.0.0.1:8000`

### 全量启动

```bash
pnpm test        # 全仓：状态机 + cloud-api + MCP
pnpm test:engine
pnpm test:api
pnpm build       # 前端构建校验
cd apps/desktop-tauri/src-tauri && cargo test
```

### 结构

```text
apps/desktop-tauri   Tauri 2 + Vue 3 客户端
apps/cloud-api       FastAPI 网关（鉴权、安全中间件、迁移编排）
packages/            状态机纯函数、API 客户端
services/            MCP Server（3 工具）、Skill、CodeArts Agent
infra/               容器、云部署清单、SQL 迁移
data/                动作库与种子数据
```


## 文档

| 文档 | 内容 |
| --- | --- |
| **[PRD.md](PRD.md)** | 需求唯一来源：四状态机、迁移规则、验收标准 |
| **[docs/architecture/huawei-cloud-integration.md](docs/architecture/huawei-cloud-integration.md)** | 华为云适配层、双模式设计 |
| **[docs/api/README.md](docs/api/README.md)** | 接口契约与调用示例 |
| **[docs/demo/demo-mode.md](docs/demo/demo-mode.md)** | 本地模式说明：入口、能力边界、数据存储 |
