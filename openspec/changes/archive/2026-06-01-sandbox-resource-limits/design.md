## Context

`SandboxClient.create_workspace`（sandbox_client.py 行 27-44）的 `docker run -d` 命令把 `--network none --memory 256m --cpus 0.5 --read-only --tmpfs /tmp` 写死。`SandboxClient.__init__` 只接收 `image`，无资源参数。项目已有外置 yaml 配置的成熟范式：`model_router.py` 用模块级 `ROUTES_PATH: Path = Path("config/routes.yaml")` + `yaml.safe_load(ROUTES_PATH.read_text())` 加载，路径常量可 monkeypatch（CLAUDE.md：「model-routes-externalize: load ROUTES from YAML」）。`config.Settings` 是 pydantic-settings，目前无 sandbox 字段，也无 settings.yaml 文件。

`docs/capabilities/sandbox.md` 给出 `sandbox.resources` 的字段与默认值，并强调「未配置时使用安全默认值；`network: none` 为默认且推荐」。

**既有 spec 归属说明**：现有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。本 change 引入的全部能力（含 SandboxClient 据资源配置构造创建命令）均为新增，以新 capability `sandbox-resource-limits` 下的 ADDED 表达，不对 sandbox-client 主 spec 做 MODIFIED（否则 archive sync 找不到同名既有需求）。

**共享资源引用**：`config/settings.yaml` 的 `sandbox:` 段骨架 owner = SB3（首个落地者建段）。本 change 仅向该段**追加** `resources` 子段，与 `sandbox.mode`（SB3）、`sandbox.scope`/`idle_hours`（SB2）共处同段，不另立配置文件。归档顺序建议 SB3 在本 change 之前（段骨架先就位）。

约束（CLAUDE.md）：禁止全局可变状态（yaml 路径/默认值常量可 monkeypatch）；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock Docker CLI、yaml 路径隔离到 tmp_path；不吞异常（解析错误要 log 或 re-raise）。

## Goals / Non-Goals

**Goals:**
- 定义 `SandboxResources`（`memory: int` MB / `cpus: float` / `network: NetworkPolicy` / `exec_timeout: int` 秒）。
- 从 yaml 加载 `sandbox.resources`，未配置或缺字段回退安全默认（256 / 0.5 / none / 30）。
- 资源值正确映射到 `docker run` 标志，`create_workspace` 不再硬编码。
- `network` 三态语义在 design 钉死映射。

**Non-Goals:**
- 不实现 `exec_timeout` 的强制终止（`docker kill` SIGTERM→SIGKILL 属波次 3，依赖 cancel token）——本 change 仅承载并传递该值，并对其做范围校验 clamp（见 D1/Open Questions）。
- 不实现 scope（SB2）、mode（SB3）、密钥过滤（SB5）、孤儿清理（SB8）、trace（SB9）。
- 不引入新依赖。

## Decisions

### D1：`SandboxResources` 数据类 + 独立加载函数，安全默认内建
新增 `src/fleetent/sandbox_config.py`：
- `NetworkPolicy`：`str` 枚举，`NONE="none"` / `PUBLIC_ONLY="public_only"` / `ALLOW_ALL="allow_all"`。
- `SandboxResources`（dataclass，带默认值）：`memory: int = 256` / `cpus: float = 0.5` / `network: NetworkPolicy = NetworkPolicy.NONE` / `exec_timeout: int = 30` / `read_only: bool = True`。
  - `read_only` 纳入资源档位、可配置：默认 `True` 保持 session 容器只读现状；agent scope 由 SB2 传 `False`（SB2 拥有 scope→档位映射，按次构造可写容器）。
- 模块级 `SETTINGS_PATH: Path = Path("config/settings.yaml")`（可 monkeypatch）。
- `load_sandbox_resources(path: Path | None = None) -> SandboxResources`：读 yaml 的 `sandbox.resources` 段，缺省字段逐项回退 dataclass 默认；文件不存在返回全默认。
- `exec_timeout` 在本 change 做范围校验 clamp 到 `[1, 600]`：超范围的值被钳到边界（< 1 → 1，> 600 → 600），属本 change「非法配置校验」范畴；强制终止逻辑仍属波次 3。

**为何**：数据类自带默认值即「安全默认」的单一事实来源，加载只做「有则覆盖」。独立模块避免把沙箱配置塞进 `config.Settings`（Settings 是扁平 env-first 的全局设置，嵌套 `sandbox.resources` 用 yaml 段更自然，且与 `model_router` 的 yaml 外置范式一致）。
**Alternatives**：①全部塞进 `config.Settings` 扁平字段（`sandbox_memory` 等）——被否，sandbox.md 明确是嵌套 `sandbox.resources` 结构，扁平化会丢层级语义且字段名冗长；②用 pydantic model 校验——可选增强，但 dataclass + 显式回退已满足，避免过度约束。**配置位置已定**：复用 `config/settings.yaml` 的 `sandbox:` 段（SB3 建段），本 change 读 `sandbox.resources`，不新建专用 yaml。

### D2：资源值到 `docker run` 标志的映射
- `memory` → `--memory {memory}m`（MB→Docker 内存单位）。
- `cpus` → `--cpus {cpus}`。
- `exec_timeout` → 不进 `docker run`（它是单次 `docker exec` 的超时，本 change 不实现终止，仅随配置传递供波次 3 消费）。
- `network`：
  - `none` → `--network none`（默认推荐）。
  - `public_only` → `--network` 指向一个仅放行公网出站、隔离内网的**预置 Docker 网络**（具体网络的创建/命名为运维侧部署前提，见 Open Questions）。**落地标注**：该网络若未预置，本 change 不自动创建，按「非法/不可用配置」处理——记录警告后回退安全默认 `none`（或在严格模式下抛明确错误），绝不静默以 bridge 放行；spec 的 `public_only` scenario 已标明此回退取向。
  - `allow_all` → 不加 `--network none`（使用 Docker 默认 bridge，放行全部出站）。
- `read_only`：`True` → 加 `--read-only`；`False` → 不加 `--read-only`（agent 可写场景）。`--tmpfs /tmp` 始终保留（提供可写临时目录，不随 `read_only` 变化）。

**为何**：`memory`/`cpus` 是 Docker 原生标志，直接映射；`network` 三态对应不同隔离级别，`none` 为默认满足数据主权与安全默认要求。`read_only` 纳入资源档位后，session（只读）与 agent（可写）两种容器可由 SB2 按次传不同档位区分。`exec_timeout` 不属 `docker run` 范畴，强制终止明确划到波次 3，但其范围校验 clamp [1,600] 属本 change。
**Trade-off**：`public_only` 需要预置 Docker 网络，落地依赖运维准备——本 change 定义语义与映射，网络的实际创建作为部署前提（Open Question）；默认 `none` 不依赖任何预置网络，开箱安全。

### D3：`create_workspace` 按次接收 `SandboxResources`（不在 `__init__` 固定）
`SandboxClient.create_workspace(name, resources: SandboxResources | None = None, image=..., env=...)`：`resources` 为 None 时构造默认 `SandboxResources()`（等价现状）；据传入的 `resources` 构造 `docker run` 参数。**不再**在 `SandboxClient.__init__` 固定一套资源策略。
**为何**：SB2 的 `SandboxManager` 持单个 `SandboxClient`，需同时创建 session（只读）与 agent（可写）两种容器。若把 resources 锁在 `__init__`，单个 client 无法 per-scope 区分两种档位；下沉到 `create_workspace` 按次传入，使同一 client 可按 scope→档位映射构造不同容器。缺省回退默认仍满足「未配置用安全默认」。
**Alternatives**：把 resources 放 `__init__`（「一个 client 对应一套资源策略」）——被否，与 SB2 单 client 造两种容器的实际用法冲突；改为 `create_workspace` 按次传入。

## Risks / Trade-offs

- [配置值非法（如 memory=0 / cpus 负数 / network 非枚举值）] → 加载时校验：非法值 log 后回退默认或抛 `ValueError`（不静默吞）；spec 用 scenario 覆盖「非法配置安全回退或明确报错」。
- [`public_only` 的网络后端未落地导致配置了却不生效] → 本 change 定义语义并映射到 `--network <预置网络>`，网络创建为部署前提（Open Question 标注）；默认 `none` 不受影响，开箱即安全。
- [`create_workspace` 新增 `resources` 入参破坏既有调用] → `resources` 可选、缺省回退默认值（含 `read_only=True`）与现状等价；扩充既有 client 测试断言默认命令不变。
- [`exec_timeout` 被误以为本 change 已实现终止] → proposal/design/spec 均明确「仅承载传递，强制终止属波次 3」；加 scenario 断言该值被读入但不触发 `docker kill`。

## Open Questions

- ~~复用 `config/settings.yaml` 还是新建专用 yaml？~~ **已定**：复用 `config/settings.yaml` 的 `sandbox:` 段（SB3 owner 建段），`sandbox.mode`（SB3）+ `sandbox.resources`（本 change）+ `sandbox.scope`/`idle_hours`（SB2）同段。
- `public_only` 的 Docker 网络如何落地：平台启动时自动创建一个出站受限网络，还是要求运维预置并在配置中引用网络名？
- ~~`exec_timeout` 的默认 30s 与 sandbox.md「最长 600s」上限是否在本 change 校验？~~ **已定**：本 change clamp `exec_timeout` 到 `[1, 600]`（属「非法配置校验」范畴）；超时强制终止仍属波次 3。
- 是否需要 admin CLI / `/health` 暴露当前生效的资源配置便于运维核对？
