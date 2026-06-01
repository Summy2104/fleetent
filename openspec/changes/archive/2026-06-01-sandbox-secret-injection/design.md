## Context

`SandboxClient.create_workspace`（sandbox_client.py 行 27-44）的 `docker run` 命令完全不带 `-e`：容器启动在一个不继承宿主环境的干净环境里。这在「不泄漏」维度是安全的现状，但一旦后续有人用 `--env-file` 或透传 `os.environ` 实现注入，宿主机的 `ANTHROPIC_API_KEY`（`config.Settings.anthropic_api_key` 来源）等敏感变量就会泄漏进容器。

**本 change 范围 = 「干净环境 + 防泄漏」。** 注入合法凭据（如内网服务 token）**不在范围内**：本 change 用名称黑名单过滤，任何按正常约定命名的合法 token/key 都含黑名单子串而被剔除——黑名单与「注入合法密钥」互斥。故本 change **不承诺**注入合法密钥、**也不加 allowlist 例外通道**；合法凭据注入留给后续的占位符级 Secret（真实密钥在网络边界透明替换，名称不进容器环境），非 Docker 原生，作后续探索。

`docs/capabilities/sandbox.md` 把方案定为「按名称过滤」：Docker 无原生 Secret，故在容器启动时对环境变量按名称黑名单过滤——含敏感子串（大小写不敏感）一律不传入；三层来源（宿主进程环境、agent 配置注入、运行时显式传入）走同一过滤规则。

**既有 spec 归属说明**：现有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。本 change 引入的全部能力（含 SandboxClient 的 `-e` 注入）均为新增，以新 capability `sandbox-secret-injection` 下的 ADDED 表达，不对 sandbox-client 主 spec 做 MODIFIED（否则 archive sync 找不到同名既有需求）。

**共享资源引用（依赖 SB3）**：agent 配置注入变量承载于 **SB3 的 `agent_store.features.sandbox_env`**（SB3 是 features 列 owner），本 change 复用同一列不重复加列；取该值作为 `agent_env` 经 **SB3 拥有的 run_code 上下文通道**（agent_loop → tool_registry.dispatch → tools.run_code）获取，不自造通道。归档顺序建议 SB3 在本 change 之前（features 列与上下文通道先就位）。

约束（CLAUDE.md）：禁止全局可变状态（敏感子串/规则为模块级可注入常量）；纯函数易单测；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock Docker CLI、`monkeypatch.setenv` 隔离 `os.environ`；不吞异常。

## Goals / Non-Goals

**Goals:**
- `is_sensitive_name(name)` 纯函数：名称（大小写不敏感）含 `TOKEN`/`KEY`/`SECRET`/`PASSWORD`/`PASSWD`/`CREDENTIAL`/`PRIVATE`/`AUTH` 等子串即敏感（清单为可扩展的最小集、非穷尽）。
- `build_sandbox_env(...)` 三层合并 + 统一过滤管线，输出可安全注入容器的 env 映射。
- 宿主机敏感变量在任何来源、任何路径下都不进入容器。
- `create_workspace` 把过滤后的 env 经 `-e` 注入；不传 env 与现状等价。

**Non-Goals:**
- **不注入合法凭据**：黑名单会剔除任何含敏感子串的合法 token/key，本 change 不承诺注入合法密钥，也不加 allowlist 例外通道；留给后续占位符级 Secret。
- 不实现占位符级 Secret（网络边界透明替换，非 Docker 原生）。
- **仅按变量名过滤，不扫描变量值**：值内嵌密钥（如 `DATABASE_URL=postgres://user:pass@host`、各类连接串）不在检测范围。
- 不接受运行时/AI 在 `run_code` 调用时传入 env：注入来源仅限 agent `features.sandbox_env` 预声明（限制攻击面）。
- 不实现 scope（SB2）、mode（SB3）、资源配置（SB4）、孤儿清理（SB8）、trace（SB9）。
- 不默认整体透传宿主 `os.environ`（默认不透传；透传仅在显式选择且必经过滤时）。
- 不引入新依赖。

## Decisions

### D1：名称过滤为纯函数 + 可注入子串常量
新增 `src/fleetent/sandbox_secrets.py`：
- `SENSITIVE_TOKENS: tuple[str, ...] = ("TOKEN", "KEY", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "PRIVATE", "AUTH")`：模块级常量，可 monkeypatch 扩展。**这是可扩展的最小集、非穷尽**——后续可按需追加。
- `is_sensitive_name(name: str) -> bool`：`name.upper()` 后判断是否含任一子串。

**为何**：大小写不敏感的子串匹配是 sandbox.md 明文规则；做成纯函数 + 常量便于单测与未来扩展，且可注入避免硬编码全局。默认集在 sandbox.md 的 `TOKEN`/`KEY`/`SECRET` 之上补 `PASSWORD`/`PASSWD`/`CREDENTIAL`/`PRIVATE`/`AUTH`，覆盖常见凭据命名。
**Alternatives**：①精确变量名白名单——被否，sandbox.md 用的是子串黑名单，白名单维护成本高且漏配即泄漏；②正则——子串 `in` 检查已足够，正则是过度设计。
**Trade-off**：子串匹配可能误伤无害变量（如 `MONKEY`、`TURKEY` 含 `KEY`）→ 接受「宁可少注入、不可泄漏」的保守取向；spec 用 scenario 钉死该取向。

### D2：三层合并 + 统一过滤管线
`build_sandbox_env(host_env=None, agent_env=None, runtime_env=None, include_host=False) -> dict[str, str]`：
- 按优先级合并：host_env（仅当 `include_host=True` 才纳入，默认 False）< agent_env < runtime_env（后者覆盖前者同名键）。
- 合并后对**所有**键统一应用 `is_sensitive_name`，敏感键一律剔除。
- 返回过滤后的映射。

**为何**：sandbox.md 强调「三层均经同一过滤规则」——把过滤放在合并之后、对全集统一执行，确保没有任何来源能绕过过滤（即便 agent 配置或运行时显式写入敏感名也被剔除）。默认 `include_host=False` 保持现状「干净环境」，注入是显式 opt-in。
**Alternatives**：每层各自过滤后再合并——等价但更易遗漏新来源；统一在合并后过滤是单一过滤点，更难绕过。

### D3：`create_workspace` 接收已过滤 env，转 `-e`
沙箱轨收敛后 `create_workspace` 的签名为 `create_workspace(name, resources, image, env)`——`env: dict[str, str] | None` 与 `resources`/`image` 同属 per-create 参数。对 env 每项追加 `-e {k}={v}` 到 `docker run`；None/空时不加 `-e`（与现状等价）。**约定**：传入 `create_workspace` 的 env 必须已是 `build_sandbox_env` 的输出（已过滤）；为防御性，`create_workspace` 内可再跑一次 `is_sensitive_name` 兜底剔除（双保险，不信任调用方）。
**为何**：单一注入点；防御性二次过滤确保「即便调用方误传敏感变量，容器仍拿不到」——纵深防御，符合数据主权底线。
**Alternatives**：`--env-file` 临时文件——被否，需写盘临时文件含明文密钥、清理复杂；`-e` 直接传参更简单且不落盘。
**Trade-off**：`-e` 值出现在 `docker run` 进程参数中（宿主 `ps` 可见）→ 仅非敏感变量经此路径，敏感变量已被过滤，残余风险可接受；占位符级方案留作后续。

### D4：注入来源仅限 agent `features.sandbox_env` 预声明（已钉死）
agent 定义中沙箱注入变量**唯一**承载于 **SB3 的 `agent_store.features` JSON 列下的 `sandbox_env` 键**（`features.sandbox_env`，一个 `dict[str, str]`）。调用链经 SB3 拥有的 run_code 上下文通道取出该 agent 的 `features`，读其 `sandbox_env` 作为 `agent_env` 传入 `build_sandbox_env`。
**钉死：不接受运行时/AI 在 `run_code` 调用时传入 env。** `build_sandbox_env` 的 `runtime_env` 形参保留作管线完整性，但当前**无任何调用方**把用户/AI 提供的 env 接入该形参——注入只能由 agent 预声明驱动。
**为何**：SB3 是 `features` 列的 owner，复用同一扩展位避免再加列；命名落定为 `features.sandbox_env`，不另立独立列/字段。仅 agent 预声明可显著缩小攻击面——AI 无法在执行期临时构造环境变量名（即便有黑名单兜底，也不给 AI 任何注入入口）。
**依赖**：SB3 先落地 `features` 列与 run_code 上下文通道；本 change 在其上读取，不自造承载位与通道。

## Risks / Trade-offs

- [子串黑名单误伤含 KEY/TOKEN 子串的无害变量] → 接受保守取向（宁可不注入）；spec 钉死；未来如需精确化可加白名单例外（不在本 change）。
- [新来源绕过过滤] → 统一在合并后单点过滤 + `create_workspace` 内防御性二次过滤，纵深防御。
- [`-e` 明文出现在 docker 进程参数] → 仅非敏感变量经此路径；敏感变量已剔除；占位符级方案后续探索。
- [`include_host=True` 误用导致大面积透传] → 默认 False，透传是显式 opt-in 且必经过滤；spec 覆盖「即便透传宿主环境，敏感变量仍被剔除」。

## Open Questions

- ~~agent 配置中沙箱注入变量的字段名~~ **已定**：复用 SB3 `features` 列下的 `features.sandbox_env`（不另立字段）。
- ~~敏感子串清单是否需扩充~~ **已定**：默认集扩为 `TOKEN`/`KEY`/`SECRET`/`PASSWORD`/`PASSWD`/`CREDENTIAL`/`PRIVATE`/`AUTH`，并注明为可扩展的最小集、非穷尽（可注入常量，后续按需追加）。
- ~~运行时显式传入变量的来源~~ **已定（钉死）**：**仅** agent `features.sandbox_env` 预声明，**不接受**运行时/AI 在 `run_code` 调用时传入 env（限制攻击面，见 D4）。
