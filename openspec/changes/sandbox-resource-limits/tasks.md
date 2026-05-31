## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `SandboxClient.create_workspace`（sandbox_client.py 行 27-44）硬编码的资源标志（`--network none --memory 256m --cpus 0.5 --read-only --tmpfs /tmp`），确定哪些参数化、哪些保留（`--read-only --tmpfs` 保留）
- [ ] 1.2 核实 yaml 加载惯例：`model_router.ROUTES_PATH` + `yaml.safe_load(path.read_text())` 模式与路径常量可 monkeypatch；`config/settings.yaml` 的 `sandbox:` 段由 SB3 建（owner），本 change 向其追加 `resources` 子段，与 `sandbox.mode`（SB3）/`scope`（SB2）共处同段
- [ ] 1.3 确认 `SandboxClient.__init__` 现仅接收 `image`，扩展 `resources` 入参（可选、缺省回退默认）不破坏既有 `test_sandbox_client.py`

## 2. 资源配置数据结构与默认值（sandbox_config.py）

- [ ] 2.1 Write failing tests：`NetworkPolicy` 枚举含 `none`/`public_only`/`allow_all`；`SandboxResources` 默认值为 `memory=256` / `cpus=0.5` / `network=none` / `exec_timeout=30`。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `NetworkPolicy`（StrEnum）与 `SandboxResources`（dataclass 带默认值），看到绿

## 3. 配置加载与回退（sandbox_config.py）

- [ ] 3.1 Write failing tests：`load_sandbox_resources` 读 yaml 的 `sandbox.resources` 段覆盖对应字段；缺字段逐项回退默认；文件不存在返回全默认。`monkeypatch SETTINGS_PATH` 到 tmp_path。看到红
- [ ] 3.2 Implement `load_sandbox_resources`（有则覆盖、缺则默认、无文件全默认），看到绿
- [ ] 3.3 Write failing tests：非法配置（memory<=0 / cpus<=0 / network 非枚举值）安全回退默认或明确抛 `ValueError`，不静默吞。看到红
- [ ] 3.4 Implement 校验逻辑（非法 log 后回退或抛错），看到绿

## 4. 资源值映射到 docker run（sandbox_client.py）

- [ ] 4.1 Write failing tests：`SandboxClient(resources=...)` 创建容器时 `memory→--memory {n}m`、`cpus→--cpus {n}`、`network=none→--network none`、`allow_all→不加 --network none`、`public_only→--network <预置网络>`；`--read-only --tmpfs /tmp` 始终保留。捕获 `asyncio.create_subprocess_exec` 参数断言。看到红
- [ ] 4.2 Implement：`__init__` 接收 `resources`（None 回退默认），`create_workspace` 据其构造 docker run 参数，看到绿
- [ ] 4.3 Write failing test：不传 `resources` 时 `create_workspace` 命令与现状等价（既有用例不回归）。看到红/绿确认兼容

## 5. exec_timeout 承载（不实现终止）

- [ ] 5.1 Write failing test：`exec_timeout` 被读入 `SandboxResources` 并可被 client 读取，但 `create_workspace` 不含任何 `docker kill` / 超时终止逻辑（明确划归波次 3）。看到红
- [ ] 5.2 Implement：`exec_timeout` 仅作字段承载传递，看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误
