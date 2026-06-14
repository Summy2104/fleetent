## 1. 平台级 docker 镜像配置

- [x] 1.1 [test] `load_sandbox_backend_config` 读 `sandbox.docker.image`：声明则取值、未声明/空串→None。先见红。
- [x] 1.2 [impl] `config.SandboxBackendConfig` 加 `docker_image: str | None = None`；loader 读 `sandbox.docker.image`。见绿。

## 2. agent 级 docker 镜像配置

- [x] 2.1 [test] `AgentFile.sandbox` 解析 `sandbox.docker.image`（含缺省、`extra=forbid` 不破）。先见红。
- [x] 2.2 [impl] `agent_config` 加 `SandboxDockerSettings{image}`，`SandboxSettings.docker` 字段。见绿。

## 3. factory 接线 + 优先级

- [x] 3.1 [test] `factory.create_backend`：平台配 docker image → `DockerBackend(image=...)`；agent 覆盖平台；都没配 → `DockerBackend()`(内置默认)；microsandbox 后端不受影响。先见红。
- [x] 3.2 [impl] `factory.create_backend` 解析 docker_image（agent>平台），docker 分支 `DockerBackend(image=docker_image) if docker_image else DockerBackend()`。见绿。

## 4. 镜像构建产物

- [x] 4.1 [docs] `docker/sandbox/Dockerfile` + `requirements.txt`（已建、已本地 build + `--network none` 实测生成 xlsx）随本 change 提交;README/注释说明 build 与 `sandbox.docker.image` 配置。

## 5. 收尾

- [x] 5.1 [gate] `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。
- [x] 5.2 [gate] `uv run mypy src`（≤基线）+ 改动文件 `ruff check/format` 净。
