# Wave-1 Apply 决策日志

> 全自主 apply 期间，遇到的冲突 / Open Question 及其解决记录，供 zy 最后核实。
> 每个 change 一节：遇到什么、怎么解的、影响。

## error-classification (AR5) — feat/error-classification

**前置核实结论(openai SDK 2.36.0):**
- `context_overflow` 判据：`APIStatusError` 且 `error.code == "context_length_exceeded"`（上下文超限以 400 + 该 code 呈现，仅状态码无法与普通 400 区分，故以 code 为准）。
- `auth_failed` 判据：`APIStatusError` 且 `status_code in {401,403}`（`AuthenticationError`/`PermissionDeniedError` 本就是 401/403，状态码判据自然覆盖，无需对子类单独 isinstance）。

**自行解决的冲突：**
1. tasks 提到的 `agent-runtime.md` 不存在 → 预留码标志位以 design.md D3 明确取值为准（tool_timeout/sandbox_* 全 False，mcp_disconnect 仅 should_retry）。
2. `tool_crash` 在表中但 `classify()` 永不返回（工具崩溃在 _safe_dispatch 归一化为字符串、不抛给 classify）→ 保留为词汇表项，守卫测试只断言不产出 4 个预留码。
3. `run_stream` 异常出口原 `return` 跳过了 log_run → 补 `_log_run_error` 在 return 前写 error_category，使"fallback 耗尽记分类码"对流式路径也成立。
4. ruff format 会误改 47 个无关文件 → 已还原，仅留本 change 的 6 个文件。

**影响：** 新增 error_classifier.py；agent_loop fallback 判定改读 should_switch_model（行为等价）；log_run 加 error_category 字段。416 passed，ruff/mypy 无新增（agent_loop 的 N814 _CU 为 AR1 既有遗留）。
**需 zy 核实：** 上述判据 #2（tool_crash 不产出）与 #3（流式补写 trace）是否认可。

## message-hygiene (AR6) — feat/message-hygiene

**实现：** 新增 message_hygiene.py（`sanitize(messages)->(clean,report)` 纯函数、`RepairKind`/`HygieneReport`/`MessageContractError`、三类修复按 D2 顺序、幂等）；run/run_stream 在 maybe_compress 后 LLM 前接入；log_run 加 hygiene_repairs 字段；不可修复 raise 由主循环按错误处理。

**MessageContractError 对齐 AR5：** 它是普通 Exception，经 AR5 `classify()` 落到 `unknown`（正是 design Open Question 预期），复用 `_log_run_error` 在循环出口写 `error_category="unknown"`。

**⚠️ 编排者验证抓到的关键 bug + 修复（重点核实）：** AR6 agent 最初把 run() 改为操作 sanitize 的副本（rebind `messages = sanitize(...)`），但 `im_gateway/normalizer.py:105-112` 的 IM 路径**依赖 run(history) 就地改 history** 再 `save(session_id, history)` 持久化（其注释明写"run already appended in-place, do NOT append again"）。rebind 会让 history 收不到 assistant/tool 追加 → **每个 IM session 只存到 [system,user]、丢失 AI 回复**（449 测试未覆盖故未报）。
**解法：** run() 改用**就地内容赋值** `messages[:] = maybe_compress(messages)` 与 `messages[:] = clean`，保住调用方列表引用（顺带也修了 maybe_compress 压缩时同样的 detach 隐患）。新增回归测试 `test_run_mutates_caller_messages_in_place` 守卫此契约。run_stream 的 messages 为内部局部变量、无外部 save 依赖，不受影响。

**agent 自解冲突：** 同名占位可达性（重写为实际可达用例）、test mock 的 model_dump 返回真 dict、stale 行号更新。

**影响：** 450 passed。run() 现保证就地改调用方 messages（IM 持久化正常）。
**需 zy 核实：** 上述就地赋值修复（run() mutation 契约）是否认可；MessageContractError→unknown 的处理是否认可。

## multimodal-input (AR21) — feat/multimodal-input

**实现：** 新增 multimodal.py（is_multimodal_content/build_image_block(base64)/build_message_with_images/has_image_block/非图片归一化占位）；agent_loop content 放宽 str|list、user_input 取文本块、`_select_route` 按 has_image_block 选 vision/default 路由；context_mgr.estimate_tokens 图片块计固定 1000 token；eval_logger._serialize 图片块→`[图片:mime,字节]` 占位；model_router ROUTES 加 vision task_type。

**D6 视觉路由（方案A）：** 含图片但 ROUTES 无 vision → `RuntimeError`（LLM 调用前，运行时查 `model_router.ROUTES` 以便 monkeypatch）。run/run_stream 共用。

**自解冲突：**
1. get_async_client_and_config 对未知 task_type 静默回落 default → 无法检测"无 vision 路由"。解：在 `_select_route` 显式 `"vision" not in model_router.ROUTES` 检查（引模块属性、非 bound import，便于测试 monkeypatch）。
2. run_stream 是 user_input:str 无 messages → 加可选 `images: list[tuple[bytes,str]]` 参数，经 build_message_with_images 构造;server.py 接入属后续(Non-Goal)。
3. 每图占位 token = 1000（保守常量；Anthropic 按像素约 ≤1600，避免 100KB base64 误加 ~25k token）。

**AR6 协调：** sanitize 只看 role/tool_call 配对、不索引 content，list content 原样通过；加守卫 `test_image_message_passes_sanitize`。run() 的 messages[:] 就地改未破坏。

**影响：** 477 passed，ruff/mypy 无新增。
**需 zy 核实：** 每图 1000 token 占位是否合理;vision task_type 默认指向(本次用 Sonnet vision,部署可改);run_stream 的 images 参数形态。

## compression-dual-threshold (AR12) — feat/compression-dual-threshold

**实现：** context_mgr 双阈值——`tmax_ratio`(触发,默认0.8)/`tretained_ratio`(目标,默认0.6);`maybe_compress(..., force=False)` 触发改读 tmax、force 实现手动 /compact;新增 `compress_for_context_overflow()` 错误触发入口;`_select_tail` 按目标线动态收缩尾部、tool-pair 完整性优先(可略超目标线、不截断 tool 对);system 头部继续单独保留(prompt-cache 依赖不破坏)。复用 AR21 改过的 estimate_tokens。

**D5 移除 context_compress_threshold：** config.py 删字段 + 新增 context_tmax_ratio/context_tretained_ratio;_default_config 改返回新键;.env.example 迁移(CONTEXT_COMPRESS_THRESHOLD→CONTEXT_TMAX_RATIO + 新增 CONTEXT_TRETAINED_RATIO);测试键更新 + 加 `test_context_compress_threshold_removed` 守卫。src 零残留。

**自解冲突：**
1. 非法配置(tretained≥tmax)选 **raise ValueError** 而非 clamp(spec 二选一,raise 更明确可断言)。
2. 摘要占位 token 用 `_SUMMARY_OVERHEAD_TOKENS=512`(对齐 _summarize 的 max_tokens=512)投影尾部,避免压后超目标。
3. 手动触发用 `force` 参数(最小侵入)、错误触发用独立函数 `compress_for_context_overflow`(语义清晰,design D4 留作实现决策)。

**影响：** 489 passed,ruff/mypy 无新增。解锁 prompt-cache(其依赖 AR12 的 system 头部保留)。
**需 zy 核实：** 非法配置 raise(非 clamp);_SUMMARY_OVERHEAD_TOKENS=512 估算;force 参数 vs 独立函数的入口形态。

## mcp-http-streamable (MCP1) — feat/mcp-http-streamable

**实现(方案A:替换非标 http 为标准 Streamable HTTP,transport 值仍 "http"):** 重写 `_register_http_server`(initialize 握手 → 存 Mcp-Session-Id → tools/list)与 `_call_http_tool`(tools/call + session id + 递增 id + Content-Type 分流);纯函数 `_extract_jsonrpc_from_sse(body,request_id)`(忽略注释、拼多行 data、按 id 过滤);session_id 与 _request_id 按 McpServerConfig 实例持有(field repr/compare=False,无全局可变态);Accept 协商;复用 transport=="http" 分支/命名空间/register_all 降级/Bearer 认证。

**自解冲突:**
1. protocolVersion 取规范最新 `2025-06-18`(design Open Question)。
2. initialize 后补发 best-effort `notifications/initialized`(失败仅 debug log 不阻断),兼容要/不要该通知的服务。
3. JSON 单响应不强制 id 匹配(无多事件干扰);SSE 严格按 id 过滤。

**影响:** 509 passed;mcp_client 的 2 个 no-any-return 为既有同模式,无新增。stdio 路径无回归。
**需 zy 核实:** protocolVersion=2025-06-18、是否所有目标 MCP server 都接受/需要 notifications/initialized。

## request-routing-override (MR1) — feat/request-routing-override

**实现:** `RouteOverride` frozen dataclass(5 字段全可选);`_apply_override(cfg,override)` 纯函数(非 None 替换;设 model 且未给 fallbacks→清空;override=None 返回同对象);get_(async_)client_and_config 加 override 参数、共用 _apply_override;run/run_stream 加 force_model→RouteOverride(model=force_model),override 生效时 models_to_try=[cfg.model];trace 复用 model_used。

**与 AR21 _select_route 整合:** 仍 `route=_select_route(messages)` 选 task_type(vision/default),override 叠加其上;`force_model=None` 走纯位置调用(不传 override kwarg,以免破坏只接单参的现有 mock 测试),非 None 才传 override=。

**自解冲突:**
1. 现状是 AR21 _select_route 而非 design 写的硬编码 "default" → override 叠加在 _select_route 结果之上。
2. force_model=None 必须不传 override kwarg(现有 mock/spy 只接单参)→ None 分支纯位置调用。
3. models_to_try 显式 [cfg.model](override 时 fallbacks 已被清空,显式写让 D3 意图存活)。

**影响:** 533 passed,mypy 66=baseline 无新增。含守卫 test_override_none_is_byte_identical_routing。解锁 model-parameter-config。
**需 zy 核实:** force_model 与 vision route 叠加语义(force_model 会强制覆盖 vision route 的模型)。

## provider-health-probe-cache (MR3) — feat/provider-health-probe

**实现:** 新增 provider_health.py(`ProviderState`/`ProviderHealthCache`,可注入 now 假时钟,三态断路器:闭合→开启→半开;构造参数>Settings>默认;`get_health_cache()` 惰性单例+可 monkeypatch);config 加 provider_failure_threshold=3/provider_cooldown_seconds=60;_call/_stream_with_fallback 用 is_available 过滤冷却 provider、成功 record_success、失败 record_failure。

**复用 AR5 classify(A 方案):** record_failure 紧跟在 AR5 的 `if not classify(exc).should_switch_model: raise` 之后——仅当 should_switch_model(429/503)才计失败;4xx/auth/unknown 先 raise、不碰缓存。单点叠加、无重复状态码逻辑。

**D4 全冷却兜底:** `_candidates()` 过滤后若全空 → 返回原全量列表(探测冷却中 provider 作最后尝试),保住"耗尽即 raise"契约(test_call_all_cooling_does_not_return_empty 验证)。

**自解冲突:**
1. 新增 `tests/conftest.py` autouse fixture 每测试重置 _cache(防跨测试 cooldown 泄漏到顺序相关的 fallback 用例)——共享测试基建文件,影响全测试但仅做隔离重置。
2. 单例惰性构造(get_health_cache),避免 import 时实例化 Settings。
3. D4 选"探测全量"而非直接 raise(对齐既有 exhaustion 测试)。

**影响:** 558 passed;provider_health 的 Settings() call-arg 是 9 个模块共享的既有模式、非新增。含守卫 test_non_health/400_never_marks_unavailable。
**需 zy 核实:** 3/60s 默认值;全冷却"探测全量"兜底策略;新增 conftest.py autouse 重置对其它测试无副作用(558 passed 佐证)。

## model-parameter-config — feat/model-parameter-config

**实现:** RouteConfig 加 `params: dict[str,Any]=field(default_factory=dict)`、RouteOverride 加 `params: dict|None=None`;`_apply_override` 对 params 深合并 `{**cfg.params, **override.params}`(override None 沿用 base);`_call/_stream_with_fallback` 的 create 追加 `**cfg.params`;max_tokens 仍一等字段。通用 dict 非枚举字段。

**重复 kwarg 守卫(双层):** 模块级 `_RESERVED_PARAM_KEYS={max_tokens,model,messages,tools}`,`_apply_override` 合并后剔除这些键(防运行时 override.params 误带保留键致 create() 重复 kwarg TypeError);单测固化内置 ROUTES 各 entry params 不含保留键。

**自解冲突:**
1. mock_client 的 cfg 是 MagicMock → `**MagicMock().params` 安全展开为空,既有测试零影响;新增透传测试用真实 RouteConfig。
2. 运行时剔除保留键(而非仅校验报错):override.params 是用户输入风险更高,剔除既挡 TypeError 又不影响合法 params。

**影响:** 576 passed;mypy 67=基线(MR3 的 provider_health 贡献 1),无新增模式。解锁 model-routes-externalize。
**需 zy 核实:** 保留键运行时剔除(而非报错)的策略。

## model-routes-externalize — feat/model-routes-externalize

**实现:** 现硬编码 ROUTES 提为内置 `DEFAULT_ROUTES`(含 default/memory_extraction/**vision**);`ROUTES_PATH`(默认 config/routes.yaml,可 monkeypatch);`_load_routes()` 用 yaml.safe_load 读盘、`_build_route()` 校验字段(必填 base_url/model/api_key_env/max_tokens、类型校验、拒绝内联 api_key)并覆盖/合并内置默认;get_(async_)client_and_config 改用 _load_routes() 取表,对外签名/回落/缺 key 语义不变。密钥仍走 env(YAML 只写 api_key_env)。

**文件缺失/损坏:** 缺失/空 → 用内置默认(开箱即用,不报错);YAML 解析失败/顶层非 mapping/缺必填/类型非法/内联 api_key → `raise ValueError`(fail loud,含路径+route 名),不静默回落。

**加载时机:** **每次调用 `get_*` 都 `_load_routes()` 读盘**——为让测试 monkeypatch ROUTES_PATH 在调用前生效。

**自解冲突:** 既有测试用 `monkeypatch.setitem(ROUTES,...)` → 保留 ROUTES 为 in-memory 有效表作 _load_routes() 合并基,无文件时返回 dict(ROUTES),setitem 仍被尊重,既满足"来源改 _load_routes()"又零回归。

**影响:** 596 passed;mypy model_router 0 错。
**⚠️ 需 zy 核实/后续优化:** **每次 LLM 调用都读盘 YAML**(为可测试性选每次加载)——生产高频下建议加可注入缓存(design Risk 已记为后续优化点)。fail-loud vs 缺失回落的边界是否认可。

## skill-yaml-frontmatter (SK2) — feat/skill-yaml-frontmatter

**实现(skill 轨地基):** `_parse_frontmatter` 改 `yaml.safe_load`(支持标量/列表/布尔/数字);四种失败→返回 None(无 `---`/无闭合/YAMLError/顶层非 mapping);`scan()` 收 None 记 structlog warning(path+reason)并跳过(纠正静默吞);`_index` 值由 tuple 改 `@dataclass SkillEntry`(description/path/tags/platforms/version/enabled_by_default),**match/load/list_skills 对外契约不变**;类型归一(tags/platforms 标量→单元素 list、缺失→[]、enabled_by_default 缺省 True、version 归一字符串);enabled_by_default 仅解析存储不接线过滤(留 builtin-skills)。

**自解冲突:**
1. 既有 test_scan_builds_index 解包内部 tuple → 改为属性访问 entry.description/path(断言内部结构、对外契约未变)。
2. structlog 断言用 `structlog.testing.capture_logs()`(仓库无 log capture 先例)。
3. env 变量名 MINI_AGENT_SKILLS_DIR 未改(属 SK9 范畴,不越界)。

**影响:** 610 passed;skill_registry mypy 0 错。解锁 SK7/SK8/SK9/builtin-skills/agent-skill-binding。
**需 zy 核实:** SkillEntry 结构(对外契约保持);失败跳过 + warning 策略。

## skill-nested-scan (SK7) — feat/skill-nested-scan

**实现:** `scan()` 的 `glob("*/SKILL.md")` → `rglob("SKILL.md")` 递归任意层级;其余(SkillEntry 索引、name 回落 parent.name、目录不存在安全返回、SK2 失败跳过)不变;同名冲突留 SK8。一行改动 + 4 个嵌套测试。
**影响:** 614 passed,无冲突无红线,skill_registry mypy 0 错。

## skill-name-conflict-warning (SK8) — feat/skill-name-conflict

**实现:** scan 写 _index 前 `_index.get(name)` 检测同名;冲突→structlog warning `skill_name_conflict`{name,kept_path,dropped_path}(由两路径 sorted 派生、与到达顺序无关);确定性选定=路径字符串排序靠前者胜(`if existing.path <= path: continue`);多重同名逐对告警;无冲突零变化不告警。来源无关(方案一),builtin-skills 统一交本 change。6 个测试(含遍历顺序无关守卫)。
**自解冲突:** 用不同父目录+显式同 name 稳定触发冲突;两个 scan 调用包进 capture_logs(structlog stdlib 处理器在 capture 外报 PrintLogger 属性,既有约定)。
**影响:** 619 passed,skill_registry mypy 0 错,无红线。

## skill-env-var-rename (SK9) — feat/skill-env-var

**实现:** scan() 行 34 `MINI_AGENT_SKILLS_DIR` → `FLEETENT_SKILLS_DIR`(默认 "skills" 不变);不留旧名兼容。一行改动 + 2 测试(新名生效、旧名不再生效)。
**自解:** "旧名不生效"测试最初误用 _write_skill(总写 skills/),chdir 后默认 "skills" 命中 → 改为把 skill 放非 "skills" 的 oldspot/ 目录,旧名指向它、默认 "skills" 不存在 → 正确验证旧名被忽略。
**影响:** 621 passed,ruff 干净,旧名 src 零残留。zy 核实:不留旧名兼容(pre-1.0 可接受)。
