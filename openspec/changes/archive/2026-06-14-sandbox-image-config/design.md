## Context

Docker 沙箱后端的基础镜像在 `DockerBackend.__init__(image="python:3.12-slim")` 写死,`factory.create_backend` 建 docker 后端时不传 image。`SandboxBackendConfig` 只解析 `sandbox.backend` 与 `sandbox.microsandbox.image`;`AgentFile.sandbox`(`SandboxSettings`)有 `microsandbox.image` 但无 docker 对应项。沙箱运行时禁网(`--network none`),故无法运行时 pip 装依赖——要让 run_code 能产 xlsx/docx/pdf 等,只能把库烤进镜像 + 让部署能指定该镜像。

## Goals / Non-Goals

**Goals:**
- 让部署可配置 Docker 沙箱基础镜像(`sandbox.docker.image`),平台级 + 每-agent 覆盖,与 microsandbox image 同优先级。
- 随仓库提供一个预装文件操作库的沙箱镜像构建产物(Dockerfile + requirements)。
- 未配置时完全向后兼容(仍 `python:3.12-slim`)。

**Non-Goals:**
- 不改沙箱网络策略(保持禁网;镜像预装就是为了不联网)。
- 不自动构建/拉取镜像(部署自行 `docker build` 后配置 tag)。
- 不动 `build_deps_image`(运行时构建 deps 镜像)那条独立机制。

## Decisions

### D1：`sandbox.docker.image` 配置(对称于 microsandbox.image)
- 平台:`config.SandboxBackendConfig` 加 `docker_image: str | None`;`load_sandbox_backend_config` 读 `sandbox.docker.image`(空串视为 None)。
- agent:`agent_config` 加 `SandboxDockerSettings{image: str|None}`,`SandboxSettings.docker` 字段(default factory),与 `microsandbox` 并列。
- **为何 `sandbox.docker.image` 而非 `sandbox.image`**:与既有 `sandbox.microsandbox.image` 对称、无歧义;`docker`/`microsandbox` 各自子节放各自镜像。

### D2：factory 解析优先级 = agent 覆盖 > 平台 > 内置默认
`create_backend` 解析 `docker_image`:平台 `platform_cfg.docker_image`,若 `agent.sandbox.docker.image` 非空则覆盖。docker 分支:`DockerBackend(image=docker_image) if docker_image else DockerBackend()`(None → 内置默认 `python:3.12-slim`,行为不变)。与既有 backend/microsandbox-image 的优先级规则一致。

### D3：随仓库提供 `docker/sandbox/`(Dockerfile + requirements.txt)
`FROM python:3.12-slim` + 预装 openpyxl/XlsxWriter/pandas/numpy/python-docx/pypdf/reportlab/fpdf2/Pillow/matplotlib/tabulate/markdown/python-frontmatter/PyYAML;`MPLBACKEND=Agg`;构建期 import 自检。已本地 `docker build` 验证通过,并在 `--network none` 下成功生成 xlsx。部署:`docker build -t fleetent-sandbox:<ver> -f docker/sandbox/Dockerfile docker/sandbox` 后配 `sandbox.docker.image: fleetent-sandbox:<ver>`。

## Risks / Trade-offs

- [配置了不存在的镜像 → docker run 失败] → 与配错 backend 同类风险;沙箱获取失败按既有降级/报错处理,不崩 agent。运维需先 build 再配。
- [镜像体积(预装 pandas/matplotlib ~600MB)] → 文档说明可裁剪 requirements(去 matplotlib/pandas 降到 ~150MB);默认给全集,按需删。
- [agent 覆盖镜像与平台 backend 不匹配] → docker_image 只在 docker 后端分支生效;microsandbox 后端忽略它(各取各的 image),无交叉。
