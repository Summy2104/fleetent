## Why

正在运行的 agent(`fleetent agent run` / IM 路径)只在 boot 时扫描一次 skills，IM 路径不按消息重扫，也没有文件 watcher。运行期唯一会触发 `registry.reload()` 的只有 `skill_manage` 工具自身的写。结果：**外部**更新 skills 目录(运营手改 SKILL.md、`git pull`、内网 skill 同步)后，运行中的 agent 感知不到，必须重启才能生效。本变更让 agent 侧自动感知外部文件变化并热加载，无需重启。

## What Changes

- **新增 `registry.refresh_if_changed(skills_dir=None) -> bool`**：walk user skills 根 + 对每个 `SKILL.md` 做 `os.stat`，拼出轻量 manifest(`{相对路径: (st_mtime_ns, st_size)}`)，与模块级 `_manifest` 比对。一致 → 返回 `False`(空操作)；不一致 → 调用既有的原子 `reload()` 重建索引并返回 `True`。**只 stat、不读不解析**，常态开销极低。
- **`scan()` / `reload()` 重建索引时顺带刷新 `_manifest`**，使指纹与 `_index` 始终同步。
- **挂载点 = catalog 注入前、每条入站消息一次**：`im_gateway/normalizer` 与 `runtime/loop.run_stream` 在调用 `available_skills_prompt` 之前先调一次 `refresh_if_changed`(默认取 `_last_skills_dir`，即 boot 扫描所用的同一 per-agent 根)。CLI 一次性路径(`run_sync` 已每次 `scan_skills`)**不改**。**不在每次 LLM 调用做**——一条消息一个 run 复用同一 system prompt，工具循环内不重复。
- **并发**：模块级小锁保护「比对 + reload」(`reload` 本身原子，最坏退化为良性重复重建)。
- **新增配置 `AgentFile.skill_hot_reload: bool = True`(默认开)**：关闭则退回「boot 扫一次 + `skill_manage` 写时 reload」的旧行为，给超大 skill 库/极致性能场景一个不改代码的退出口。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `skill-hot-reload`: 在既有「运行期可手动重扫(admin)/原子切换/失败保留旧索引/in-flight 用旧版」之上，新增**自动感知外部文件变化并触发重扫**的能力——agent 侧每条入站消息在 catalog 注入前做一次 manifest 比对，变化则触发既有原子 `reload()`；并由 per-agent `skill_hot_reload` 配置(默认开)门控。

## Impact

- **owning package**：`skills/`(`registry.py` 新增 `refresh_if_changed` + `_manifest` 维护)、`runtime/`(`loop.run_stream` 接线)、`im_gateway/`(`normalizer` 接线)、`agent_config.py`(新增 `skill_hot_reload` 字段)。
- **public API surface**：新增 `registry.refresh_if_changed(skills_dir=None) -> bool`；`scan()`/`reload()` 行为扩展(维护 `_manifest`，对调用方透明)。
- **owned tables**：无。
- **config namespace**：`AgentFile.skill_hot_reload: bool = True`(agent.yaml)。
- **cross-module dependencies**：`runtime` / `im_gateway` → `skills` public API(既有边)；纯 agent 运行时改动，**零 `fleetent.platform.*` import**，满足「无 platform 也能 `fleetent agent run`」基线。
- **migration / shim plan**：无模块迁移、无新表、无迁移脚本；默认开启不改变现有 reload 契约(复用既有原子 `reload()`)。
