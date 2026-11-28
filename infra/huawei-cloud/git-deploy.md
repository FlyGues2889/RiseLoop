# Git 拉取部署

目标：云端代码由 git 管理，更新只做 `git pull` + 重建，不再手工传 tar 包。

适用：Flexus L（或任意 Linux 云主机）+ Docker Compose。`.env` 不进 git，迁移时单独保留。

## 1. 前置

- 代码已推到远端仓库（当前 `origin` 为 `https://github.com/FlyGues2889/RiseLoop.git`）。
- 仓库根就是构建上下文，`apps/cloud-api`、`packages/intervention-engine`、`data/actions`、`data/knowledge`、`infra/docker` 必须保持原层级。
- 私有仓库需要凭据，二选一：
  - **部署密钥（推荐，只读）**
    ```bash
    ssh-keygen -t ed25519 -C riseloop-deploy -f ~/.ssh/riseloop_deploy
    cat ~/.ssh/riseloop_deploy.pub
    ```
    把公钥加到 GitHub 仓库的 Deploy keys（不勾写权限）。
  - **Personal Access Token**：`git clone https://<token>@github.com/FlyGues2889/RiseLoop.git`，token 只放 `~/.git-credentials`（`chmod 600`），不要写进仓库或镜像。

## 2. 首次迁移（从 tar 包目录切到 git 目录）

```bash
# 备份现有 .env
cp ~/riseloop/infra/docker/.env ~/riseloop.env.bak
chmod 600 ~/riseloop.env.bak

# 停旧栈
cd ~/riseloop/infra/docker
docker compose -f docker-compose.cloud.yml down

# 克隆（私有仓库用部署密钥）
cd ~
GIT_SSH_COMMAND="ssh -i ~/.ssh/riseloop_deploy" \
  git clone git@github.com:FlyGues2889/RiseLoop.git riseloop-git

# 恢复 .env
cp ~/riseloop.env.bak ~/riseloop-git/infra/docker/.env
chmod 600 ~/riseloop-git/infra/docker/.env

# 起栈
cd ~/riseloop-git/infra/docker
docker compose -f docker-compose.cloud.yml up -d --build
docker compose -f docker-compose.cloud.yml ps
curl -s http://127.0.0.1:8000/health/ready
```

确认新目录跑通后，旧目录可以改名保留或删除：

```bash
mv ~/riseloop ~/riseloop.bak
```

## 3. 日常更新

```bash
cd ~/riseloop-git
git pull --ff-only

cd infra/docker
docker compose -f docker-compose.cloud.yml up -d --build
docker compose -f docker-compose.cloud.yml ps
curl -s http://127.0.0.1:8000/health/ready
```

只改 `.env` 时不需要 `--build`，用 `--force-recreate`：

```bash
docker compose -f docker-compose.cloud.yml up -d --force-recreate api
```

## 4. 回滚

```bash
cd ~/riseloop-git
git log --oneline -5
git checkout <commit-or-tag>
cd infra/docker
docker compose -f docker-compose.cloud.yml up -d --build
```

回滚后如需回到主线：

```bash
git checkout main
git pull --ff-only
```

## 5. 约束

- `.env` 只存在于服务器，权限 `600`；不要提交、不要打进镜像。
- `git pull` 用 `--ff-only`，服务器上不要产生本地提交。
- 构建上下文是仓库根；不要在服务器上单独改 `apps/` 下的文件后不提交，下一次 `git pull` 会覆盖。
- 数据卷：`postgres` / `redis` 容器在场景 B 才用；切到托管 RDS/DCS 后可以 `stop` 它们，卷保留。

## 6. ModelArts 实测配置（2026-11-28）

在线服务 `service-af70`（PyTorch 2.1.0 / 8C32G / 公共池）实测可用配置：

```dotenv
RISELOOP_MODELARTS_ENDPOINT=https://120.46.74.129/v2/infer/<service-id>/
RISELOOP_MODELARTS_API_KEY=<API Key>
RISELOOP_MODELARTS_AUTH_HEADER=authorization
RISELOOP_MODELARTS_TLS_VERIFY=false
```

要点：

- URL **末尾必须带 `/`**，否则网关 307，httpx 默认不跟随。
- API KEY 认证用 `Authorization: Bearer <API Key>`，不是 `X-Apig-AppCode`。
- 公网地址是 IP + 自签证书，`RISELOOP_MODELARTS_TLS_VERIFY=false` 才能连；正式环境应换域名或把 CA 装进镜像。
- 模型挂载路径填 `/home/ma-user/infer/model/1`，不是 `/home/mind/model`。
- 预置 PyTorch 镜像的 nginx（8443）可能因私钥加密启动失败；可用 HTTP 8080 + 启动命令绕过：
  ```bash
  bash -lc 'source /home/ma-user/anaconda3/etc/profile.d/conda.sh && conda activate PyTorch-2.1.0 && cd /home/ma-user/infer && export TF_MODEL_ARGS="--model_path=/home/ma-user/infer/model/1 --model_name=serve --service_file=/home/ma-user/infer/model/1/customize_service.py" && export MODEL_SERVER_ARGS="$TF_MODEL_ARGS" && exec modelarts_server -w 1 --threads 5 -t 120 -b 0.0.0.0:8080 app:app'
  ```
  容器协议 HTTP、端口 8080。
- 验证：`curl -k -X POST <endpoint> -H "Authorization: Bearer <key>" -H "Content-Type: application/json" -d '{}'` 返回 400 `MR.0101` 即通；`/posture/infer` 返回 `source=huawei` 才算接上。
