## Why

沙箱(Docker 后端)的基础镜像被**写死**为 `python:3.12-slim`,无任何配置口子(只有 microsandbox 有 `image`)。该镜像不含 openpyxl/pandas 等文件操作库,而沙箱**禁网**(`--network none`)又装不了 → agent 无法在 run_code 里生成 xlsx/docx/pdf 等并经 send_file 发出(实测:"生成 Excel 发给我"因此失败,模型被逼走 Google-Sheets→/tmp 的脆弱路径并最终编借口)。需要一个口子,让部署能指定一个**预装好文件操作库的沙箱镜像**(保持禁网)。

## What Changes

- **新增可配置的 Docker 沙箱镜像**:`sandbox.docker.image`(platform.yaml 平台级 + agent.yaml 每-agent 覆盖,镜像与 `sandbox.microsandbox.image` 对称)。未配置时仍用 `python:3.12-slim`(行为不变)。`factory.create_backend` 按"agent 覆盖 > 平台默认 > 内置默认"解析后传给 `DockerBackend(image=...)`。
- **随仓库提供专用沙箱镜像构建产物**:`docker/sandbox/Dockerfile` + `docker/sandbox/requirements.txt`(`FROM python:3.12-slim`,预装 openpyxl/XlsxWriter/pandas/python-docx/pypdf/reportlab/fpdf2/Pillow/matplotlib/tabulate/markdown 等文件操作与图表库,设 `MPLBACKEND=Agg`)。构建后部署可把 `sandbox.docker.image` 指向它,沙箱**保持禁网**也能产文件。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `sandbox-backend-abstraction`: 后端选择新增 Docker 基础镜像可配(`sandbox.docker.image`,平台 + 每-agent 覆盖),与 microsandbox image 同优先级规则。

## Impact

- **owning package**：`integrations/sandbox`（`config.py` 的 `SandboxBackendConfig` + loader、`factory.py`）、`agent_config`（`SandboxSettings` 加 `docker` 子节）。
- **public API surface**：`SandboxBackendConfig` 新增 `docker_image: str | None`；`AgentFile.sandbox` 新增 `docker.image`；`factory.create_backend` 签名不变,内部多解析一个 image。
- **owned tables**：无。
- **config namespace**：新增 `sandbox.docker.image`(platform.yaml + agent.yaml)。
- **cross-module dependencies**：无新增;不碰 agent⊥platform。
- **migration / shim plan**：无 schema 迁移;未配置 `sandbox.docker.image` 时 `DockerBackend()` 仍默认 `python:3.12-slim`,完全向后兼容。新增 `docker/sandbox/` 构建文件(不影响运行时,除非部署显式 build 并配置)。
