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

**重复 kwarg 守卫(双层):** 模块级 `_RESERVED_PARAM_KEYS={max_tokens,model,messages,tools}`,`_apply_override` 合并后**校验**这些键;单测固化内置 ROUTES 各 entry params 不含保留键。

**自解冲突:**
1. mock_client 的 cfg 是 MagicMock → `**MagicMock().params` 安全展开为空,既有测试零影响;新增透传测试用真实 RouteConfig。

**影响:** 576 passed;mypy 67=基线(MR3 的 provider_health 贡献 1),无新增模式。解锁 model-routes-externalize。

**✅ zy review 决定(2026-05-31,改原"运行时剔除"为"报错"):** 保留键(max_tokens/model/messages/tools)出现在 params 里 → `_apply_override` **raise ValueError**(含具体键名),不再静默剔除——让用户知道配置错了、该键不生效,而非被悄悄忽略。校验对合并后的 params 生效(同时覆盖 override.params 与 routes.yaml 的 cfg.params)。测试 `test_apply_override_reserved_key_in_params_raises` 替换原 strip 测试。732 passed,ruff/mypy 干净。

## model-routes-externalize — feat/model-routes-externalize

**实现:** 现硬编码 ROUTES 提为内置 `DEFAULT_ROUTES`(含 default/memory_extraction/**vision**);`ROUTES_PATH`(默认 config/routes.yaml,可 monkeypatch);`_load_routes()` 用 yaml.safe_load 读盘、`_build_route()` 校验字段(必填 base_url/model/api_key_env/max_tokens、类型校验、拒绝内联 api_key)并覆盖/合并内置默认;get_(async_)client_and_config 改用 _load_routes() 取表,对外签名/回落/缺 key 语义不变。密钥仍走 env(YAML 只写 api_key_env)。

**文件缺失/损坏:** 缺失/空 → 用内置默认(开箱即用,不报错);YAML 解析失败/顶层非 mapping/缺必填/类型非法/内联 api_key → `raise ValueError`(fail loud,含路径+route 名),不静默回落。

**自解冲突:** 既有测试用 `monkeypatch.setitem(ROUTES,...)` → 保留 ROUTES 为 in-memory 有效表作 _load_routes() 合并基,无文件时返回 dict(ROUTES),setitem 仍被尊重,既满足"来源改 _load_routes()"又零回归。

**影响:** 596 passed;mypy model_router 0 错。

**✅ zy review 决定(2026-05-31):**
1. **加缓存(原"每次读盘"已修)**:拆出 `_load_file_routes()`,**只缓存昂贵的文件解析**(磁盘读 + YAML parse + 校验),按 `(path, mtime, size)` 键控;`_load_routes()` 仍每次 `dict(ROUTES)` 合并 in-memory 表(便宜、且让 `setitem`/运行时改 ROUTES 仍可见)。稳态热路径(文件未变)跳过磁盘+parse;改路径/改文件内容(mtime 或 size 变)→ 自动重解析。`monkeypatch ROUTES_PATH`(各测试独立 tmp 路径)天然命 miss 重解析,可测试性不受损。新增测试 `test_load_routes_caches_file_parse_until_mtime_changes`(缓存命中)+ `test_load_routes_in_memory_routes_edits_stay_visible_through_cache`(合并仍每次做)。734 passed,ruff/mypy 干净。
2. **fail-loud 边界认可**:文件不存在=回落内置默认;文件存在但坏(YAML 错/顶层非 mapping/缺必填/类型非法/内联 api_key)=raise。

## skill-yaml-frontmatter (SK2) — feat/skill-yaml-frontmatter

**实现(skill 轨地基):** `_parse_frontmatter` 改 `yaml.safe_load`(支持标量/列表/布尔/数字);四种失败→返回 None(无 `---`/无闭合/YAMLError/顶层非 mapping);`scan()` 收 None 记 structlog warning(path+reason)并跳过(纠正静默吞);`_index` 值由 tuple 改 `@dataclass SkillEntry`(description/path/tags/platforms/version/enabled_by_default),**match/load/list_skills 对外契约不变**;类型归一(tags/platforms 标量→单元素 list、缺失→[]、enabled_by_default 缺省 True、version 归一字符串);enabled_by_default 仅解析存储不接线过滤(留 builtin-skills)。

**自解冲突:**
1. 既有 test_scan_builds_index 解包内部 tuple → 改为属性访问 entry.description/path(断言内部结构、对外契约未变)。
2. structlog 断言用 `structlog.testing.capture_logs()`(仓库无 log capture 先例)。
3. env 变量名 MINI_AGENT_SKILLS_DIR 未改(属 SK9 范畴,不越界)。

**影响:** 610 passed;skill_registry mypy 0 错。解锁 SK7/SK8/SK9/builtin-skills/agent-skill-binding。

**✅ zy review 决定(2026-05-31):**
1. **①SkillEntry dataclass、②用户 skill 解析失败→跳过+告警:均认可保持**(理由见对话:tuple 6 字段已撑不住、dataclass 对齐仓库风格;跳过+告警是故障隔离唯一正解,静默吞=不可调试、整体崩=爆炸半径灾难)。warning 现额外带 `source`(builtin/user)字段,内置 skill 失败也可见(内置不 fail-loud、统一跳过)。
2. **增强已实现:加载失败汇总**。新增模块级 `_load_errors` + 公开 `load_errors()->[{path,reason,source}]`(供 admin/health 查询,始终可查、不经日志);scan 结束**仅在有失败时**打一条 `skill_scan_complete`{loaded,failed} 汇总(warning 级)。新增测试:`test_load_errors_records_each_failed_skill`/`test_load_errors_reset_on_each_scan`/`test_scan_emits_summary_with_loaded_and_failed_counts`/`test_scan_clean_emits_no_summary_log`。738 passed。

**⚠️⚠️ review 中发现的真 bug(标记给 zy,共享日志基建,疑似常乐 observability 域):** `config.configure_logging`(config.py:38)把 `structlog.stdlib.add_logger_name`(读 `logger.name`)与 `PrintLoggerFactory()`(产出的 PrintLogger **无** `.name`)配在一起——**任何一条日志走这套配置都会 `AttributeError: 'PrintLogger' object has no attribute 'name'`**。旧代码因 scan() 仅在失败时才 log、服务正常启动从不 log,坑一直隐藏;一度因我加无条件汇总日志引爆 53 个 server 测试(已改"仅失败时 log"规避,零新增风险——剩余风险与既有 logger.warning 相同)。**建议后续修 configure_logging:add_logger_name 需配 stdlib LoggerFactory,或换 PrintLogger 兼容的处理器。** 非本次 SK2 范围,未擅自动。
**✅ 已在 S1(16/20)修复(2026-05-31):** configure_logging 删除 add_logger_name(它与 PrintLoggerFactory 不兼容),根因消除——生产任何日志不再崩。详见 S1 节第 4 点。

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

## builtin-skills — feat/builtin-skills

**实现:** `BUILTIN_SKILLS_DIR=Path(__file__).parent/"builtin_skills"`(可 monkeypatch);scan 经 `_scan_dir(base,*,builtin)` 扫内置+用户两目录,SkillEntry 加 `builtin: bool`;新建 src/fleetent/builtin_skills/getting-started/SKILL.md 示例;config 加 `disabled_skills: list[str]=[]`;match() 加可选 disabled_skills 参数(参数>Settings>默认),跳过 (name in disabled_skills) 或 (enabled_by_default false[本次接线 SK2 解析的字段]),记 `skill_disabled_skipped`{name,reason,builtin};load() 不受禁用约束。

**与 SK8 协调(方案一):** scan 只发现+打 builtin 标记,**不引入覆盖/来源优先**;同名冲突全交 SK8 路径排序+告警;替换内置走禁用开关。守卫 test_scan_no_source_priority_override_logic。

**自解冲突:**
1. 示例内置 skill 泄漏进所有测试 → autouse reset_registry 默认 monkeypatch BUILTIN_SKILLS_DIR 到不存在的 tmp,保持既有行为;builtin 测试 opt-in。
2. match 新 logger.info 在 configure_logging 后崩 → 禁用路径测试包 capture_logs(既有约定)。
3. 测试数据 skill 名 `on` 被 YAML 强转 True → 改名 enabled。

**影响:** 636 passed;mypy 68=67+1,+1 是 _resolve_disabled_skills 的 Settings() call-arg(同 context_mgr D4 既有模式,非新模式)。实现了 roadmap SK6 的全局禁用层。
**需 zy 核实:** 默认 disabled_skills 空、enabled_by_default 缺省 True 下行为不变(守卫已验);内置示例 skill 内容。

## agent-skill-binding — feat/agent-skill-binding  ⚠️⚠️ 跨张亮 governance 域,务必复核

**实现:** `agent_policy.check_skill_access(skill, allowed, blocked)` 纯函数(复用 check_tool_access fnmatch,opt-in:allowed None→False);agent_loop 加 `_matched_skill_content()`(match→过滤→load 单点),run_sync/run_stream/run 加 allowed_skills/blocked_skills 参数(run 仅透传);normalizer 从 agent 读绑定过滤注入。

**⚠️⚠️ 动了张亮的 agent_store(待张亮复核):**
- `Agent` dataclass 加 `allowed_skills: list[str]|None=None`、`blocked_skills: list[str]|None=None`(可选、向后兼容)。
- `agents` 表加两列 `allowed_skills TEXT`/`blocked_skills TEXT`(nullable;NULL=未声明 opt-in,[]=显式空白名单);_init_db CREATE 含新列 + `_ensure_skill_columns()` ALTER 兜底旧表。
- create_agent/get_by_name/get_agent_for_user/get_agent_for_channel 读写新列。
- **新增 alembic 迁移 `migrations/versions/002_add_agent_skill_columns.py`**(up 加列/down 回滚)。
- 字段命名 allowed_skills/blocked_skills + 缺省语义(None=opt-in 不注入、[]=显式空)按 design D1/D3 默认落定——**需张亮确认是否符合 governance 域约定**。

**opt-in 行为变更:** CLI run_sync 无绑定→不注入任何 skill(相对此前全局注入)。既有测试不依赖全局注入(mock_client 把 match_skill mock 成 None),故无回归;新增守卫锁 opt-in。默认 agent 配置白名单的缓解(D5)本次不实现。

**自解冲突:** get_agent_for_channel 别名 a/ca 冲突→改 ca_a;旧表无新列→_ensure_skill_columns ADD COLUMN 兜底;ruff SIM103 内联。

**影响:** 658 passed,迁移测试 5 passed,mypy 68=基线。

**✅✅ zy review 重大决定(2026-05-31)——整个 agent-skill-binding 推翻重做为 openclaw 式 read-on-demand,删除全部跨张亮 DB 改动:**

关键认知(扭转设计):**skill 不是授权边界,tool 才是。** skill 只是指令文档,模型读了也越不过 `allowed_tools` + 审批那道真正的墙。给 skill 做"DB 表 + 硬 allowlist"是把低风险指令当高风险能力治理,过度设计。

新设计(参考 /opt/gopath/src/github.com/openclaw/openclaw):
- **注入模型**:框架把已启用 skill 渲染成 `<available_skills>` 清单(name/description/location)+ `## Skills` mandatory 指令,注入 system prompt 的**稳定前缀区**(对 prompt-cache 友好);模型按需调新增 `read_skill(name)` 工具读全文。**放弃关键词自动匹配 + 全文自动注入。**
- **绑定**:用哪些 skill 由 admin 在 agent 的 `system_prompt` 里 prose 圈定;首版目录=全部已启用 skill(减 `disabled_skills`);结构化逐 agent 收窄留后续(取决于张亮 agent 定义 DB-vs-配置)。

落地(在 fix/wave1-review-corrections,TDD):新增 `skill_registry.available_skills_prompt()`(+3 测试)、`tools.read_skill`(+2 测试);`agent_loop._assemble_prompt` 改注入目录(稳定前缀),删 `_matched_skill_content`/match/load/allowed_skills/blocked_skills,prompt-cache stream/sync 测试重写;删 `agent_policy.check_skill_access`;`normalizer` 删关键词注入改注入目录,**顺带修了 12/20 prompt-cache 标记的"normalizer memory/skill 在 system 最前 缓存杀手"**(现按 base+catalog 稳定→memory 变量排序);**回退张亮 agent_store**(删字段/`_dump_opt`/`_load_opt`/create_agent 参数/`_ensure_skill_columns`/CREATE 列)、**删迁移 002**、改 test_agent_store/test_migrations、删 test_skill_policy.py + test_agent_loop_skill_binding.py。

净效果:**跨张亮 governance 纠葛归零、代码更少、与 tool/prompt-cache 架构对齐**。721 passed,ruff 净(仅既有 baseline),mypy 71=71 零新增。
**需 zy 核实:** 首版目录=全部已启用 skill(逐 agent 结构化收窄留后续);read_skill 不 gate 禁用(与已批准"load() 不受禁用约束"一致,目录只列启用项)。
**已无需张亮:** DB 表/迁移改动全部回退,不再触碰 governance 域。

## session-ttl-cleanup (S1) — feat/session-ttl-cleanup

**实现:** `is_expired(mtime,now,ttl)` 纯函数;`cleanup_expired(ttl_seconds=None,*,_now=None)`:rglob("*.json") 递归(带 `/` 的 session_id 经 `path.relative_to(SESSIONS_DIR).with_suffix("").as_posix()` 还原)、跳过 .json.tmp、过期删除返回 session_id 列表、单文件失败容错 log.warning 继续、汇总 log;最后活跃用文件 mtime;config 加 session_ttl_days=30 + _default_config;参数>Settings>默认。**纯清理原语,触发器(cron,跨张亮 scheduling)留后续**。

**自解冲突:**
1. 加 `_now` keyword-only 测试钩子(伪造 mtime 还需可控"现在"做确定性断言,不 sleep)。
2. **发现 save() 既有局限:save() 只 mkdir(SESSIONS_DIR),不为含 `/` 的 session_id 建子目录 → `save("u123/dm:...")` 会 FileNotFoundError**。本 change 不碰 save(测试直接建子目录文件);**此为 save 既有 bug,标记供 zy 后续处理**。
3. test structlog 全局污染(test_config 的 configure_logging 残留)→ test_session_mgr autouse `structlog.reset_defaults()` 隔离。

**影响:** 670 passed;mypy 69=68+S1 的 _default_config Settings()(既有模式非新)。
**⚠️ 需 zy 核实:** save() 对带 `/` session_id 不建子目录的既有 bug(本次未修,建议后续修);TTL 触发器后续接张亮 cron。

**✅ zy review 决定(2026-05-31,在 fix/wave1-review-corrections,TDD):**
1. **修了 save() 的 `/` bug**:`save()` 改为 `path.parent.mkdir(parents=True)`(不再只 mkdir SESSIONS_DIR),含 `/` 的 session_id 正常落子目录。新增 `test_save_and_load_roundtrip_slash_session_id`。
2. **TTL 默认 30 天:认可。**
3. **触发器改"从内置操作"、不依赖张亮 cron**:新增 `maybe_run_cleanup(*, _now=None)`——save() 末尾**故障隔离**调用它,**时间门控**(config 加 `session_cleanup_interval_seconds=3600`,经 `_default_config`),每 interval 最多跑一次全量 rglob,清理作为"写 session"的副作用发生。不动 server lifespan(避免 test_server 未隔离 SESSIONS_DIR 删真实数据)。新增 3 个门控测试 + save 故障隔离测试;test_session_mgr autouse 默认把门 GATE 关闭(避免触发器误删测试的人工老化 fixture),触发器测试自行开门。
4. **⚠️⚠️ 顺带修了 SK2(10/20)标记的 configure_logging 真 bug**:`config.configure_logging` 删掉 `structlog.stdlib.add_logger_name`(它读 `logger.name`,而 PrintLoggerFactory 的 PrintLogger 无 `.name`→**每条日志 emit 时 AttributeError**)。这是真实生产 bug(configure_logging 后任何日志都崩),之前因 happy path 不 log 而潜伏;本次 save()→cleanup 的 `logger.info` 引爆了它(19 个 integration/server 测试),已从根上修复。新增 `test_configure_logging_then_log_does_not_raise`。**需常乐(observability)知会**:已删 add_logger_name,日志输出不再带 logger-name 字段(要的话需配 stdlib LoggerFactory)。
影响:727 passed,ruff/mypy 71=71 零新增。

## session-metadata-index (S2) — feat/session-metadata-index

**实现:** 新建 session_index.py(sessions 表:session_id PK/user_id/created_at/updated_at/message_count/agent_name;record_activity 用 ON CONFLICT upsert 首次 created_at 固定/冲突刷 updated_at;get/list_by_user[updated_at DESC]/count/total_message_count);save() 加可选 user_id/agent_name,原子写成功后调 record_activity,**try/except 故障隔离**(索引失败 log.warning 吞掉、不回滚消息)。

**⚠️ 重要偏离(需 zy 核实):change 设计与 CLAUDE.md 说"用 aiosqlite",但 aiosqlite 实际未安装(ModuleNotFoundError),且全仓 store(user_store/agent_store/schedule_store)都用同步 `sqlite3`。** 为守"无新依赖"硬约束 + 与现有 store 一致,session_index 也用同步 sqlite3(非 aiosqlite)。→ **CLAUDE.md 的 aiosqlite 说法与现实不符**;zy 定:保持 sqlite3(匹配现状,推荐)还是真引入 aiosqlite(加依赖、store 改 async)。

**自解冲突:**
1. aiosqlite 未装 → 用 sqlite3 复刻 sibling store 模式(见上)。
2. save 写索引 DB 会污染 data/ → test 的 index_db fixture 设 autouse 隔离到 tmp_path。

**向后兼容/故障隔离:** save 两参调用不破(新参默认 None→元数据 NULL);record_activity 异常不破坏消息写入(守卫测试验证)。

**影响:** 680 passed;session_index mypy 0 错。
**⚠️ 需 zy 核实:** **sqlite3 vs aiosqlite 偏离**(CLAUDE.md 不符现实);元数据要完整需 agent_loop/normalizer 透传 user_id/agent_name(逐步补)。

**✅ zy review 决定(2026-05-31):**
1. **保持 sqlite3**(匹配全仓现状,不引入 aiosqlite 依赖)。**已修正 CLAUDE.md**:原"用 aiosqlite 直接写 SQL"→"用标准库 sqlite3 直接写 SQL(同步;全仓一致);SQLAlchemy 仅供 alembic 迁移,不作 ORM;aiosqlite 未引入"。后续开发/AI 不再被错误指引误导。
2. **元数据渐进补齐认可**:user_id/agent_name 由 agent_loop/normalizer 逐步透传。

## session-disk-management (S4) — feat/session-disk-management

**实现:** `enforce_capacity(max_total_bytes=None,max_count=None)`:rglob 扫描收集 (session_id,size,mtime)、跳过 .json.tmp、带 `/` 还原;两维度**或触发、且停止**(is_over_capacity 任一超→True,while 循环淘汰至两者皆不超);按 mtime 升序最旧优先删;维度 ≤0 关闭(不触发不停止),两维都关→返回空;删除容错(失败 log.warning 跳过、扣减累计防级联超删);触发原因+淘汰数汇总日志。config 加 session_max_total_mb=1024/session_max_count=10000;扩展 S1 的 _default_config(保留 ttl_seconds + 加 max_total_bytes/max_count)。纯原语,触发器留后续。

**自解冲突:**
1. S1 的 _default_config stub 测试因新字段失效 → 补两字段进 stub。
2. 容错按"每次淘汰尝试"扣减累计(非仅成功时),防卡住文件级联超删健康 session。

**影响:** 701 passed;mypy 69 无新模式。Session 轨(S1/S2/S4)全完。
**需 zy 核实:** 1024MB/10000 默认;容错的扣减语义。触发器(同 S1)待后续接张亮 cron。

**✅ zy review 决定(2026-05-31):** ①1024MB/10000 默认认可;②容错扣减语义认可;③**触发器挂进 S1 的内置触发器,不依赖张亮 cron**——S1 的 `maybe_run_cleanup` 更名 `maybe_run_maintenance`,现一次门控内**先 TTL 清理(cleanup_expired)再容量管理(enforce_capacity)**,save() 触发。enforce_capacity 不再是死原语。新增 `test_maybe_run_maintenance_also_enforces_capacity`。728 passed,ruff/mypy 71=71 零新增。Session 轨全部"活起来",无需 cron。

## prompt-cache-optimization — feat/prompt-cache-optimization

**实现:** `_assemble_prompt()` 重排——base system 作 messages[0] 稳定可缓存前缀,可变 memory_ctx+skill 合并为 messages[1] 独立 system 消息(无则省略);run_sync/run_stream 两处改走它,功能等价。`_extract_cache_tokens(usage)` 尽力取 Anthropic(cache_read/creation)+OpenAI(prompt_tokens_details.cached_tokens),缺失 None;log_run 加 cache_tokens 字段。不注入 cache_control(后端无关、自动前缀缓存)。AR12 的 _compress 已统一保留所有 system 头部,base system 在内(守卫测试锁)。

**自解冲突:**
1. skill-binding 测试断言 messages[0] 含 skill → skill 现在 messages[1],改为 join 所有 system 消息断言(符合 spec"skill 在 base system 之后")。
2. 流式合成 CompletionUsage 无缓存字段 → 从带 usage 的原始 chunk 提取。
3. AR12 协调:_compress 保留全部 system 头部,无需改 context_mgr,加守卫。

**⚠️ normalizer 待办(张亮域):** `im_gateway/normalizer.py` 有同样"memory/skill 在 system 最前"缓存杀手,本 change 未改(属张亮 im_gateway 域)——**待张亮协调重排,否则 IM 路径仍命不中前缀缓存**。
**✅ 已在 agent-skill-binding 重做(15/20)中顺带修复(2026-05-31):** normalizer 重写时把单条 system 消息改为 base+catalog(稳定)→memory(变量)排序,前缀字节稳定可命中缓存。无需再等张亮。

**影响:** 712 passed,mypy 无新增。
**需 zy 核实:** memory/skill 后置为独立 system 消息(messages[1])的形态;normalizer 同样重排需张亮做。

**✅ zy review 确认(2026-05-31):** 核实点已被 15/20 重构消化——`_assemble_prompt` 演进为 base+catalog(稳定前缀)→memory(messages[1]),skill 改 read_skill 工具不再走 messages 注入;**normalizer 缓存杀手已在 15/20 顺带修复,无需张亮**。`_extract_cache_tokens` + log_run cache_tokens 字段保留不变。无遗留。

## image-generation-tool — feat/image-generation-tool

**实现:** 新建 image_gen_client.py `generate(prompt,*,size,settings)->bytes`(AsyncOpenAI(base_url=image_gen_url) 调 images.generate response_format=b64_json,b64 优先、回 url 则内网 httpx fetch,`ImageGenError`);tools.py 加 `GENERATED_DIR`(默认 data/generated,可注入)+ `_save_image`(uuid4.png)+ `generate_image` `@tool(risk_level="low")`(async,经 _safe_dispatch await):调 client→存盘→**返回短引用"image generated: <path>"、绝不返回 base64**,端点失败/未配置→明确失败结果文本(不静默成功、不中断循环);config 加 image_gen_url=""/image_gen_model="default"。自托管 OpenAI 兼容 images 端点。

**自解冲突:**
1. dispatch 不 await,_safe_dispatch 处理 async(同 run_code),无需改 registry。
2. SDK size 用 Omit/omit sentinel + 显式 kwargs(避免 call-overload/type:ignore)。
3. 自托管端点常忽略 auth → 传占位 api_key="image-gen"。
4. ruff format 误改 schedule_task 等 → 还原,仅留本 change 加性 diff(tools.py 3 个 lint 错为既有 baseline)。

**影响:** 732 passed;mypy 无新模式。守卫:test_generate_image_result_has_no_base64 / test_tool_result_message_in_trace_has_no_base64。
**需 zy 核实:** image_gen_url 默认空(部署须配自托管端点);引用形态 "image generated: <path>"。

**✅ zy review 确认(2026-05-31):** ①image_gen_url 默认空、未配时返回明确失败文本(不崩不中断 loop):认可;②返回短引用 "image generated: <path>"、绝不回 base64:认可。无改动。

---

## review 收尾(2026-05-31)

20/20 决策日志全部与 zy 逐条过完。review 期间产生的修正全部在 `fix/wave1-review-corrections` 分支(基于 feature/zhangyang),计 8 个提交:
1. model-param 保留键改报错(原静默剔除)
2. model-routes 文件解析按 (path,mtime,size) 缓存
3. skill SK2 加载失败汇总(load_errors + 仅失败时 summary 日志)
4. **agent-skill-binding 推翻重做为 openclaw read-on-demand**(删 DB 表/迁移/check_skill_access,加 available_skills_prompt + read_skill 工具;顺带修 normalizer 缓存杀手)
5. session-ttl-cleanup:修 save() `/` bug + 内置 maybe_run_maintenance 触发器(不依赖 cron)+ **修 configure_logging 的 PrintLogger 崩溃真 bug**
6. CLAUDE.md 修正 aiosqlite→sqlite3
7. session-disk-management:enforce_capacity 并入内置触发器
(注:部分提交合并了多项)

仍需 zy/他人后续关注:S2 sqlite3(已确认保持,CLAUDE.md 已改);configure_logging 删 add_logger_name 需知会常乐 observability;逐 agent skill 结构化收窄 + vision-as-tool 待 propose(见 deferred 备查)。
