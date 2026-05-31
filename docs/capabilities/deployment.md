# deployment

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

让 fleetent 能安全、可重复地部署到客户自己的服务器上，并在版本升级时不丢数据。

**负责**：容器化打包（Docker）、环境变量与配置文件加载、数据库 schema 版本管理（alembic）、on-premises 安装包与 license 校验。

**不负责**：运行时业务逻辑（→ 各模块）、IM 平台网络连接（→ im-gateway）、用户认证（→ user_store）。

**调用关系**：
- 依赖：config、alembic（DB migration）
- 被依赖：所有模块（运行时依赖配置）

## 现状

- ✅ **pydantic-settings 配置体系**：.env + config/settings.yaml 双源加载
  - 类型安全，环境变量优先级高于 yaml
  - 密钥不进 DB，不进 git，仅通过 env var 注入

- ✅ **Dockerfile**：单容器部署
  - 当前已有 Dockerfile 和 docker-compose.yml，关键配置：
    - `extra_hosts: host.docker.internal:host-gateway`（Linux 宿主机访问，sandbox_client 通过此地址调用宿主机工具进程）
    - `volumes: ./data:/app/data, ./config:/app/config`（持久化用户数据和配置）
    - `env_file: .env.production`（密钥通过 env_file 注入，不写入镜像）

- ✅ **alembic DB migration**：schema 版本管理
  - 升级时自动执行 migration，不需要手动改表

- ✅ **SQLite-first 默认存储**：无需独立数据库服务
  - 数据在 data/ 目录，挂载 volume 持久化
  - 当前不要求 PostgreSQL；数据库访问边界需避免把业务层写死到 SQLite
  - 不引入 ORM；schema lifecycle 由 alembic 统一管理

## 规划中（v1.0）

- [ ] **on-premises 安装包**：完整的一键部署方案
  - docker-compose.yml + .env.example + 安装文档
  - 包含启动前检查（端口、权限、环境变量）

- [ ] **License key 机制**：绑定目标服务器（MAC / CPU ID）
  - 启动时校验 license，不通过则拒绝启动
  - 阶段一：硬件绑定；阶段二：Nuitka 编译保护源码

- [ ] **多环境配置**：dev / staging / prod 配置文件分离
  - 通过 FLEETENT_ENV 环境变量切换

- [ ] **升级脚本**：新版本部署时自动执行 alembic upgrade head
  - 升级前自动备份 SQLite 文件

- [ ] **统一 database_url 配置**：以 SQLite 为默认后端，保留后续 PostgreSQL 接入空间
  - 默认值指向本机 `data/users.db`
  - 业务 store 通过统一 DB runtime 获取连接和事务，不直接依赖 SQLite 文件路径

## 验收标准

**场景 1：首次部署**
- Given：一台干净的 Linux 服务器，安装了 Docker
- When：按照安装文档执行部署命令
- Then：服务在 5 分钟内启动，GET /health 返回 200

**场景 2：版本升级**
- Given：运行中的 v1.0 实例，有存量用户数据
- When：执行升级脚本部署新版本
- Then：DB migration 自动执行，存量数据完整保留，服务正常启动

**场景 3：配置隔离**
- Given：.env 文件包含 ANTHROPIC_API_KEY
- When：服务运行
- Then：API key 不出现在任何日志、trace、system prompt 中

**场景 4：License 校验（v1.0）**
- Given：license key 绑定服务器 A 的 MAC 地址
- When：将服务部署到服务器 B
- Then：服务启动失败，输出 license 不匹配的错误

## 待决问题

- [ ] License key 的发放和管理方案（负责人：待认领）
- [ ] PostgreSQL 作为可选生产后端的时间节点与 OpenSpec change 范围（负责人：待认领）
