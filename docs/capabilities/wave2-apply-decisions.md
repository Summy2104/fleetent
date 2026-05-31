# Wave-2 Apply 决策日志

> 全自主 apply 期间,遇到的冲突 / Open Question 及其解决记录,供 zy 最后核实。
> 每个 change 一节:遇到什么、怎么解的、影响。

## vision-as-tool — feat/vision-as-tool

**前置核实结论(tasks 1.x):**
- AR21 复用点确认:`multimodal.has_image_block` 按 `block.get("type") == "image_url"` 判定;`agent_loop._select_route` 仅当 `has_image_block` 为真才走 `vision`,否则 `default`。因此"剥离图片块(主上下文只留盘上引用字符串)→ 路由自然回 default"成立,且**无需改 `_select_route`**。
- image-gen 复用模式确认:`tools.GENERATED_DIR` 是可注入模块级路径常量;`_save_image(data)->ref`(写 `{uuid}.png` 返回路径,绝不回 base64);`generate_image` 是 `@tool(risk_level="low")` async,经 `_safe_dispatch` await;`image_gen_client.generate` 用 `AsyncOpenAI(base_url=..., api_key="image-gen")`、`image_gen_url` 默认空、未配抛 `ImageGenError`、工具层归一化为 `error:` 文本不抛。
- normalizer 注入链确认:`route()` 在 `session_lock` 内组装 system(base+catalog→memory)后 `history.append({"role":"user","content": msg.text})`,再 `await agent_loop.run(history)`,run 就地改 history 后 `session_mgr.save`。**首次抽取的插入点**就是这条 user-append:把"取 msg.text 当 content"换成"先抽取图片再构造 content"。

**实现:**
- 新增 `src/fleetent/vision_client.py`:`analyze(image_bytes, instruction, *, settings) -> str`,对称 `image_gen_client`——`AsyncOpenAI(base_url=settings.vision_url, api_key="vision")` 占位 key,发标准 OpenAI 兼容 vision chat(text 块 + image_url base64 data URL 块),取回 `choices[0].message.content`;`VisionError`;`vision_url` 空抛 `VisionError`;端点错/空 choices/空 content 均抛。
- `config.py`:加 `vision_url=""` / `vision_model="default"`(对称 image_gen 字段,带注释)。`.env.example` 同步加 `VISION_URL=` / `VISION_MODEL=default` 注释。
- `tools.py`:加 `UPLOADS_DIR`(默认 `data/uploads`,可注入)+ `_MIME_EXT` 映射 + `_save_upload(data, mime)->ref`(写 `{uuid}.{ext}`、返回路径)/ `_read_upload(ref)->bytes`;新增 `analyze_image(ref, instruction)` `@tool(risk_level="low")` async:`_read_upload` 失败→`error:` 文本,`VisionError`→`error:` 文本,均不抛(经 `_safe_dispatch` await)。
- `im_gateway/normalizer.py`:新增 `_image_attachments`(从 `msg.attachments` 挑出 `(bytes, mime)` 图片项)+ `_build_user_content(msg)`(无图→原 `msg.text`;有图→逐图 `_save_upload` + 一次 `vision_client.analyze`(instruction=用户文本)→ 把"用户文本 + `[图片 {ref}]\n{分析}`"拼成纯字符串 content)。`route()` 的 user-append 改调它。base64 从不进 history,故 `has_image_block` 天然为假、路由回 default、run 就地改 history 契约不变(content 仍是 str)。

**自解冲突:**
1. **attachments 形态未在 spec/现实中定义**:`NormalizedMessage.attachments` 字段早已存在但所有 caller 传 `[]`,无既定结构。据 `build_message_with_images` 的既有契约(`list[tuple[bytes, mime]]`)定为同形——`_image_attachments` 只收 `(bytes, str)` 且 mime 以 `image/` 打头的项,非图片项忽略。slack/telegram 适配器抽图入 attachments 不在本 change 范围(仍传 `[]`),不动它们。
2. **"剥离图片块"的落地形态**:AR21 的 normalizer 路径其实从没把图片做成 image_url 块进 history(它只 append `msg.text` 字符串)。所以本 change 不是"先建块再剥离",而是**首次抽取直接产出纯文本 content(用户文本 + 引用 + 分析),图片 base64 根本不进主上下文**——等价于 D3 的"剥离后只留引用",且更彻底。run/run_stream 的 `images=` 参数路径(AR21 真正会建 image_url 块的入口)保持不变,其 `_select_route` 仍按 has_image_block 选 vision,AR21 用例不破。
3. **bare `@tool` 对 async 函数报 mypy `type-var`(新错误类型)**:`tool` 的 bare overload 绑定 `F: Callable[..., str]`,async 函数返回 Coroutine 违反 bound → `type-var`(既有 async 工具用的是 `@tool(risk_level=...)` 参数化 overload,只报 `arg-type`)。改用 `@tool(risk_level="low")`(analyze_image 是只读、低风险,与 generate_image 对称),把新 `type-var` 收敛回既有的 `arg-type` 模式。
4. **vision_client `messages=` 的 mypy TypedDict 报错**:dict 字面量精确类型与 OpenAI 的 ChatCompletionMessageParam Union 不洁净匹配(`misc`/`list-item`,且 `arg-type` ignore 覆盖不到)。改为先 `content: list[Any]` / `messages: list[Any]` 再传(同 agent_loop 全程用 `list[Any]` 的既有做法),去掉 inline ignore;末行 `getattr` 的 Any 用 `str(text)` 收口 `no-any-return`。
5. **ruff format 误改无关代码**:`ruff format` 把 tools.py 里 AR 既有的 `schedule_task`/`cancel_task`(本就超 100 行/import 顺序问题)一并重排。已手工还原这几行,只留本 change 新增内容。tools.py 现存的 3 个 ruff 错误(E501+I001+F401,均在 schedule_task/cancel_task)是 stash 验证确认的**改动前既有**遗留,非本 change 引入。

**影响:**
- 新增 `vision_client.py`、`tests/test_vision.py`、`tests/test_normalizer_vision.py`;改 `config.py`、`tools.py`、`im_gateway/normalizer.py`、`.env.example`。
- 全量 **746 passed**(基线 728 + 新增 18),无回归;AR21 multimodal/route 用例全绿。
- ruff:我的新建/修改文件 `ruff format` + `ruff check` 全绿;tools.py 的 3 个 ruff 错误为既有遗留(未触碰)。
- mypy:`uv run mypy src` 总数 base 71 → 本 change 73(+2,编排者实测更正子 agent 误记的"79→73"),无新增**错误模式**——新增 2 个均为既有模式实例:`vision_client.py:53` 的 `Settings()` call-arg 同 `image_gen_client.py`/`server.py`/`im_connector_config.py` 既有;`tools.py` analyze_image 的 `arg-type` 同 generate_image/run_code 既有 async-`@tool` 模式。符合"不新增错误模式"。

**需 zy 核实:**
1. `attachments` 形态定为 `list[tuple[bytes, mime]]`(自解冲突 #1):是否认可。本 change 未让 slack/telegram 适配器真正抽图入 attachments(仍 `[]`),即"入站图片自动抽取"在 IM 端尚无真实数据源——是否需要后续 change 补适配器抽图,还是本 change 应一并接上。
2. 首次抽取直接产出纯文本 content(不经 image_url 块,自解冲突 #2):是否认可这一"比剥离更彻底"的落地,即 IM 路径的图永不以 base64 块进 history。
3. uploads 生命周期/清理本 change 未实现(按 design Open Question 既定:只存盘,清理留后续)。

## skill-hot-reload — feat/skill-hot-reload

**前置核实结论(tasks 1.x):**
1. `scan()` 用 `_index.clear()` 就地清空(原行 55)后再 `_scan_dir` 逐个填充,确认运行期复用会有半空窗口 + 填充中途抛错则旧索引永久丢失 → 不能直接复用。
2. 触发时机:`scan()` 仅在 `server.py:68` lifespan 与 `agent_loop.py:466` 的 `run_sync()` 内跑;`run()` 不扫描。本 change 只新增运行期 `reload()`,不改任何既有触发时机。
3. 读取方引用方式:`match`/`load`/`list_skills`/`available_skills_prompt` 均在函数体内经模块级 `_index` 访问(非 def 时捕获);`tools.py:90` 经 `skill_registry._index` 模块属性查找;全仓**无任何** `from skill_registry import _index`。→ `global _index; _index = new` 整体重绑定对所有读取方即时可见,原子替换安全。

**实现:**
- `skill_registry.py`:抽出 `_build_index(skills_dir, errors=None) -> dict[str, SkillEntry]` 纯构建函数(覆盖 builtin + 用户两源,不触碰全局);`_scan_dir` 改签名为接收 `index`/`errors` 形参(不再 mutate 模块全局),同时服务 `scan()` 与 `_build_index()` 两路径。`scan()` 改为调 `_build_index` 再 `clear()+update()` 落到全局(启动/CLI 行为不变)。新增 `reload(skills_dir=None) -> dict`:构建成功才 `global _index, _load_errors; _index = new_index`(单次重绑定,原子);失败(build 抛异常)不替换、记 `skill_reload_failed` 结构化 warning(含 skills_dir+reason)、返回 `{"status":"failed",...}`;成功返回 `{"status":"ok","loaded":N,"failed":M}`。
- `admin.py`:新增 `reload-skills` 子命令(沿用 `add_parser`),调 `reload()` 打印成功/失败摘要,失败 `sys.exit(1)`。
- D4(in-flight)无需改实现:`_assemble_prompt` 已把 catalog 字符串快照进该请求私有 messages,原子替换不回改——仅加确认测试。

**自解冲突:**
1. **`_build_index` 签名 vs `_load_errors`**:D1 规定签名 `-> dict[str, SkillEntry]`,但 `scan()` 需继续填充 `load_errors()`。取最小改动:`_build_index` 严格返回 dict(符合 D1),通过可选 `errors` 出参收集跳过的坏 Skill;`scan()` 传入一个本地 list 再落到 `_load_errors`,`reload()` 同理用本地 list 并在成功时一并重绑定 `_load_errors`。保持 D1 签名语义且不丢失既有 SK2 错误汇总能力。
2. **"目录不可用"是否算失败**:spec D3 文字含"目录消失",但现 `_scan_dir` 对不存在目录是 early-return(正常"无用户 Skill"语义,builtin 仍扫),不抛异常。若把"用户目录缺失"当失败会破坏 builtin-only 的合法部署。据此:失败路径定义为 `_build_index` **抛异常**(真正不可恢复,如读盘 OSError);用户目录单纯缺失走正常空结果,不触发保留逻辑。失败测试用 monkeypatch 让 `_build_index` 抛 `OSError` 来覆盖真实失败语义。
3. **`reload()` 返回结构**:spec/design 未规定具体返回形态,自定 `{"status","loaded","failed"}` / `{"status","skills_dir","reason"}` dict,供 CLI 直接渲染、未来 API 复用。

**影响:** 759 passed(base 746 + 13 新)。ruff:自改 src 文件(`skill_registry.py`/`admin.py`)format+check 全绿;自加测试(`test_skill_registry.py`/`test_agent_loop.py`)check 全绿;`test_admin.py` 有 3 个**既有** lint(unused `Path` import + 一处 E402,主分支同样报)未动,非本 change 引入。mypy:base 73 errors → after 73 errors,**无新增**——`admin.py` 一度因复用 `result` 变量名(与 `seed_builtin_admin` 分支的 `tuple|None` 冲突)新增 7 个错误,已改名 `summary` 消除;`skill_registry.py` 仅余 1 个**既有** `Settings()` call-arg(主分支同样 1 个,同既有模式)。未跑仓库级 `ruff format src tests`(按铁律只动自己的文件)。

**管理 API 端点:** **未做,仅做 CLI**。理由:既有管理动作端点在 `user_admin_api.py`,用的是 `Session <token>` 认证 + admin 角色 + audit_log,且该 router 刻意不 import agent loop;`server.py` 的 Bearer 端点(`/chat`)是 user-agent 调用语义,非 admin 动作。指令要求"server.py 已有清晰 Bearer 认证端点骨架可低成本复用"才一并加——实际无此低成本 Bearer admin 骨架(admin 动作走 Session,不是 Bearer)。在 Session-auth router 里加 reload 需引入 skill_registry 依赖 + 接 audit_log,属中等 surface,且 D5 明确 API 是 Open Question(CLI 先行)。故 CLI 先行,API 留后续 change(若运维需要,接 `user_admin_api.py` Session-auth + `_require_admin` + audit_log)。

**需 zy 核实:**
1. 管理 API 端点缺席是否认可(理由见上);如需,后续接 `user_admin_api.py` 的 Session-auth 而非 Bearer。
2. 自解冲突 #2:"用户目录缺失不算 reload 失败、只有 build 抛异常才保留旧索引"——这一对 spec D3"目录消失"措辞的收敛是否认可。
3. `reload()` 返回 dict 形态(自解冲突 #3)是否认可作为后续 API 的契约基础。
4. 并发 `reload()` 沿用 design"最后写赢"语义,本 change 未加锁(与 design Risks 一致)。

## skill-injection-audit — feat/skill-injection-audit

**前置核实结论(tasks 1.x):** 两个注入面已按 read-on-demand 落地并核实:`skill_registry.available_skills_prompt`(清单面,拼 name/description/location,经 `_disabled_reason` 过滤)与 `tools.read_skill`(全文面,经 `skill_registry.load` 取正文)。`SkillEntry`(SK2)字段确认;入索引点是 `_scan_dir` 组装条目处,`scan()` 与 `reload()` 都经 `_build_index → _scan_dir`,故审计对两条路径都生效。`load()` 无禁用检查(既有口径:load 是排查出口,不受清单/禁用约束),审计沿用此口径。

**实现:**
- 新增 `src/fleetent/skill_audit.py`:模块级不可变 `_RULES: tuple[_Rule, ...]`(每条 `_Rule`=frozen dataclass:`rule_id`/`severity`/预编译正则);`audit(content, description) -> list[Hit]`(`Hit`=frozen dataclass,带 `rule_id`/`severity`/`field`("content"|"description")/`match`),正文与 description 都检,纯静态、不调 LLM、无 I/O;`has_severe(hits)` 辅助判断。
- `SkillEntry` 加 `audit_blocked: bool = False`。`_scan_dir` 组装条目前调 `_audit_skill(path, body, description)`:`_body_after_frontmatter` 切出正文,跑 `audit`,**每条命中**写结构化日志 `skill_audit_hit`(path/rule_id/severity/field/disposition),有 severe 命中则置 `audit_blocked=True`(条目仍留 `_index`)。日志均走 `logger.warning`(启动扫描即控制台告警,severe/suspicious 都可见)。
- `available_skills_prompt`:过滤条件叠加 `and not entry.audit_blocked`(与 disabled 同处)。
- `read_skill`:改为先取 `entry = _index.get(name)`,`audit_blocked` 在 `load()` **之前**短路返回拒绝文本(`error: skill 'X' was blocked by the static injection audit`),不返回正文。
- `load()` 不变,忽略 `audit_blocked`,仍按名返回原文供人工排查。

**规则表覆盖(注入类/严重度):**
- severe — `ignore_previous_instructions`(英文 ignore/disregard/forget previous instructions 族)、`ignore_previous_instructions_zh`(中文 忽略/无视/忘记 之前/上述 指令族)、`fake_system_directive`(`<system>` 标签 / `system prompt:` 伪装系统指令)、`role_reassignment`(you are now unrestricted/jailbroken/DAN/developer mode)、`pipe_to_shell`(`curl|wget ... | sh/bash`)、`remote_eval_exec`(`eval/exec(requests|urllib|os.popen|subprocess`)。
- suspicious — `no_restrictions`(no/without restrictions/limitations/guardrails)、`reveal_system_prompt`(reveal/print/repeat/show your system prompt)。
- 覆盖 docs/proposal 列举的高危类(忽略指令 / 伪装 system / shell 注入),初始集,后续可在 `_RULES` 末尾追加(design Open Question)。

**自解冲突:**
1. 正文来源:`audit` 需正文,而 `_scan_dir` 原只 `read_text` 一次喂 `_parse_frontmatter`。最小改动:把 `read_text` 结果存 `raw` 复用,新增 `_body_after_frontmatter(raw)`(切 `---` 后第三段;无 frontmatter 兜底返回全文,审计不漏内容),不重复读盘。
2. 日志级别:spec 只对 suspicious 明确"启动控制台告警",severe 只要求"审计日志"。统一用 `logger.warning` 记两者——severe 至少同等严重,且启动扫描时运维应都看到;测试只断言 event/severity/disposition/path,不锁级别。
3. `read_skill` 原用 `name not in _index` 判存在;改为取一次 `entry` 同时支撑存在性 + audit_blocked 两个分支,避免二次查 `_index`(对齐 design "拒绝在 load 前短路、复用既有索引查询")。
4. 未引入 `severity` 的字符串字面量类型别名(保持 `str`),与既有 store/registry 代码风格一致,避免过度工程;规则表是 SoT。

**影响:** 780 passed(基线 759 + 新增 21:skill_audit 11 + skill_registry 9 + tools 1)。
- ruff:我新建/改的 `skill_audit.py`/`skill_registry.py`/三个测试文件 `ruff format`+`check` 全绿;`tools.py` 仅 `read_skill` 逻辑改动(diff 已收敛为仅此函数),其 2 个 `cron_scheduler` unused-import 警告是 HEAD 既有(grandfathered,非本次引入)。
- mypy:base 73 errors → after 73 errors(checked 48→49 源文件,新增 `skill_audit.py` 零错),无新增错误模式;新模块公开函数完整注解(mypy strict)。

**需 zy 核实:**
1. severe 日志与 suspicious 同用 `logger.warning`(severe 未单独升 error)是否认可;若要分级(severe→error)可在 `_audit_skill` 按 severity 切换。
2. 规则表初始 8 条覆盖面是否够用作 v1.0 起点;中文规则仅覆盖"忽略指令"族,其余类(伪装 system/shell)未做中文变体——按需在 `_RULES` 追加。
3. `read_skill` 拒绝文本以 `error:` 前缀返回(与既有 `error: no skill named` 一致),措辞含 "blocked by the static injection audit",是否符合预期对模型/运维的提示口径。

## skill-disable-mechanism — feat/skill-disable-mechanism

**前置核实结论(tasks 1.x):** 地基为 read-on-demand（已落地 SK4 hot-reload + SK5 injection-audit）。`SkillEntry` 已含 `enabled_by_default`/`audit_blocked`，本 change 新增 `enabled: bool=True`。`_disabled_reason(name, entry, disabled)` 现状仅覆盖 `disabled_skills`（返回 `"disabled_skills_config"`）与 `enabled_by_default:false`（返回 `"enabled_by_default_false"`），**未**覆盖 `enabled` 与 `audit_blocked`——`available_skills_prompt` 当时把 `audit_blocked` 作为 `_disabled_reason(...) is None and not entry.audit_blocked` 的单独一项过滤。`eval_logger.log_run` 已是可选字段模式（`stop_reason`/`error_category`/`hygiene_repairs`/`cache_tokens`，`if x is not None: entry[...]=x`），照此加 `disabled_skills_trace`。注入链三处入口（`agent_loop.run_sync`、`agent_loop.run_stream`、`im_gateway/normalizer`）都先调 `available_skills_prompt()` 再最终 `log_run`；其中 `run_sync`/`normalizer` 的 `log_run` 在 `run()` 内部，`run_stream` 自身直接 `log_run`。

**实现:**
- D1：`SkillEntry.enabled: bool=True`，`_scan_dir` 经 `bool(frontmatter.get("enabled", True))` 填充。
- D2：`_disabled_reason` 扩展为覆盖全部 4 来源的单一资格谓词，按优先级返回首个命中标识或 None：`audit_blocked` > `frontmatter_disabled`（`enabled:false`）> `config_disabled`（`disabled_skills`）> `default_disabled`（`enabled_by_default:false`）。`available_skills_prompt` 改为**纯经** `_disabled_reason(...) is None` 过滤（去掉单独的 `and not entry.audit_blocked`，audit 已并入谓词）。
- D3：新增 `collect_disabled_trace(disabled_skills=None) -> list[{"name","reason"}]`，复用同一谓词遍历 `_index` 收集被排除项；保留 `available_skills_prompt` 签名/语义不变（既有调用方与 test_agent_loop monkeypatch 不受影响）。`eval_logger.log_run` 加可选 `disabled_skills_trace`（**仅非空才写** `if disabled_skills_trace:`，空列表也不写，向后兼容）。`agent_loop.run()` 加 `disabled_skills_trace` 参数透传 `log_run`；`run_sync` 收集后传入 `run()`；`run_stream` 本地收集传入自身 `log_run`；`normalizer` 收集后经 `run()` 传入。

**自解冲突（来源标识改名）:**
1. **来源标识改名（核心）**：现状返回串 `"disabled_skills_config"` / `"enabled_by_default_false"` 与 spec/design 的标识 `config_disabled` / `default_disabled` 不一致。统一为 spec 四标识（`audit_blocked`/`frontmatter_disabled`/`config_disabled`/`default_disabled`）。grep 全仓确认旧串仅 2 处依赖：`tests/test_skill_registry.py:527`（`disabled_skills_config`→`config_disabled`）、`:540`（`enabled_by_default_false`→`default_disabled`），均为 `match()` 的 `skill_disabled_skipped` 日志断言，一并改到新串；`src` 无其他调用方读取该串。无残留。注：任务简报里写的现状串是 `"config_disabled"`，但实际代码是 `"disabled_skills_config"`——以代码为准处理。
2. **trace 收集函数选型**：未改 `available_skills_prompt` 返回 `(prompt, trace)` 元组（会破坏 3 处既有调用方与多处 test monkeypatch），而是新增独立 `collect_disabled_trace`，两者共用 `_disabled_reason`，最小改动。
3. **空列表不写**：`log_run` 用 `if disabled_skills_trace:`（truthy）而非 `is not None`，使空 `[]` 也省略字段；入口处用 `collect_disabled_trace() or None` 双重保险。

**trace 收集接入点:** 三处注入链全部接入——`agent_loop.run_sync`（收集后传 `run(...)`）、`agent_loop.run_stream`（本地收集，传自身 `log_run`）、`im_gateway/normalizer.handle`（收集后经 `agent_loop.run(...)` 传入）。`run()` 新增 `disabled_skills_trace` 参数承接。

**影响:** 798 passed（基线 780 + 新增 18：test_skill_registry 14 含 enabled/谓词/collect + 2 处旧串断言更新；test_agent_loop 4 trace 接入）。
- ruff：我改/建的 `skill_registry.py`/`eval_logger.py`/`agent_loop.py`/`normalizer.py`/两个测试文件 `format`+`check`——format 重排了 1 个测试文件；check 仅报 `agent_loop.py:638` 的 N814（`CompletionUsage as _CU`），属 HEAD 既有（grandfathered，非本次引入）。
- mypy：base 73 → after 73 errors（checked 49 源文件），无新增错误模式。

**需 zy 核实:**
1. 来源标识从 `disabled_skills_config`/`enabled_by_default_false` 改名为 spec 的 `config_disabled`/`default_disabled`——这改变了 `match()` 的 `skill_disabled_skipped` 日志里 `reason` 字段取值（运维若有日志查询/告警依赖旧串需同步）。是否认可统一到 spec 口径。
2. `disabled_skills_trace` 写入语义为「仅非空才写」，无禁用的运行完全不写该字段（向后兼容）；trace 项形如 `{"name","reason"}`，reason 取最高优先命中来源——是否符合事后排查的字段口径。
3. `normalizer` 也接入了 trace 收集（spec 未点名 IM 路径，但为口径一致一并接入）——是否认可。

## compression-pre-cleanup — feat/compression-pre-cleanup

**前置核实结论（tasks 1.x）:**
- **1.1 接入点**：`_compress`（context_mgr.py 行 108-130）确定 `to_summarize` 中段后调 `_summarize`。`_summarize`（行 156-179）只摘 `user`/`assistant`、不摘 `tool`，经 `_content(m)` 对整条 content 做 `str(...)`（非 per-block）——含 image 块的 content list 被整体字符串化（含 base64）。确认清理接入点为「`_summarize` 之前对中段做规则替换」：插入 `cleaned = _pre_cleanup(to_summarize)`，再 `_summarize(cleaned)`。清理只作用于中段（不含头尾 system/tail），与 AR12 触发/目标线判定解耦。
- **1.2 image 判据**：`estimate_tokens`/`_estimate_message_tokens`（行 53）判据为 `isinstance(block, dict) and block.get("type")=="image_url"`，`_IMAGE_BLOCK_TOKENS=1000`。清理沿用**同一判据**（`_is_image_block`），不改估算口径。
- **1.3 工具调用消息实际结构（D3 必核）**：核 `agent_loop.py`。assistant 工具调用消息 = `{"role":"assistant","content":None,"tool_calls":[{"id":<str>,"type":"function","function":{"name":<str>,"arguments":<str>}}]}`（行 614-623）；工具结果消息 = `{"role":"tool","tool_call_id":<id>,"content":<str>}`（行 434、634）。`arguments` 是 **JSON 字符串**；result `content` 是字符串；一条 assistant 可含多个 tool_call block（`tool_calls` 是 list），各自对应一条 `role=="tool"` 消息，按 `tool_call_id` 关联。
  - **规范化判等粒度**：判等键 = `(工具名, 规范化参数, 结果内容)` 三者全等。参数规范化 = `json.loads` 后 `json.dumps(sort_keys=True, ensure_ascii=False)`——**忽略 key 顺序与空白**；非法 JSON 兜底为原字符串（不崩）。结果内容用 tool 消息的 `_content(...)` 原文严格比对。
  - **多 tool_call 消息处置**：block 粒度判等；**仅当某 assistant 消息全部 block 都在更新位置找到等价重复，才删整条 assistant + 其全部 tool_result**；否则整条保留（连同未去重 block）。删除时连带删除被删 block 的 tool_result（按 id），保证无孤立 tool_result。
- **1.4 占位块形态**：除 `image_url` 外，messages 中未见其它二进制占位形态（codebase grep 仅 image_url）。判据沿用 `type=="image_url"`。尺寸来源：块上 `width`/`height` 字段（均在才用 `{w}×{h}`），缺失兜底 `未知尺寸`。**无时间戳维度**——messages dict 由 `msg.model_dump()` 产生，无 timestamp 来源（与 design Open 一致），占位简化为 `[图片：{尺寸}]`。

**实现:** `src/fleetent/context_mgr.py`：
- 新增纯函数 `_pre_cleanup(messages)`（先逐条 `_replace_image_blocks` 替图，再 `_dedup_tool_calls` 去重）；在 `_compress` 内 `_summarize` 前调用。
- `_replace_image_blocks`：list-content 内 image 块换成 `{"type":"text","text":"[图片：{尺寸}]"}`；不改入参（命中才新建 dict/list，未命中原样返回）。
- `_dedup_tool_calls`：从后往前扫，把后出现的 block 判等键存入 `seen_keys`；某 assistant 消息全部 block 键都已 seen 即整删，连带删其 tool_result。判等键经 `_tool_call_key`+`_normalize_args`。
- 常量 `_IMAGE_SIZE_UNKNOWN="未知尺寸"`。
测试：`tests/test_context_mgr.py` 新增 15 个用例（图片替换/尺寸/兜底/不可变/合法文本块；去重保留最新/结果异/参数异/规范化等价/多block部分等价保留/多block全等价整删/无孤立result；清理 0 调 LLM；`_compress` 清理在摘要前且 base64 不进摘要输入）。

**自解冲突:**
1. **占位时间戳维度**：agent-runtime.md 列 `[图片：{尺寸}，{时间戳}]`，但 messages dict 无 timestamp 来源（1.4 核实），按 design 决议简化为 `[图片：{尺寸}]`，不补时间戳。
2. **参数规范化粒度（D3 Open）**：design 留待核实——据 1.3「arguments 是 JSON 字符串」结论，定为 `json.loads`→`json.dumps(sort_keys=True)` 忽略 key 顺序/空白；非 JSON 兜底原串。属严格全等的合理规范化（同语义参数视为相等），不做模糊判等。
3. **去重单位（D3 必核）**：按 block 粒度，仅全 block 等价才整删消息，否则保留整条——避免误删非重复 block 或留孤立 tool_result。

**影响:** 813 passed（基线 798 + 新增 15），无回归。
- ruff（仅我改/建文件 `context_mgr.py`/`test_context_mgr.py`）：format 重排 2 文件，check 全绿。
- mypy `src`：base 73 → after 73 errors，无新增错误模式（context_mgr 唯一报错为既有 line 29 `Settings()` call-arg，遗留）。

**需 zy 核实:**
1. 参数规范化忽略 key 顺序/空白（`sort_keys=True`）——同语义不同书写的重复调用会被判等去重。是否认可（vs 纯字节级全等）。
2. 结果内容用 tool 消息 `content` 原文严格比对（不做 trim/normalize）——结果有微小差异即不去重。是否符合预期。
3. 占位省略时间戳维度（messages 无 timestamp 来源）——若后续调用方会注入时间戳，再决定是否补回 `{时间戳}` 维度。


## compression-layered-retention — feat/compression-layered-retention

**前置核实结论（tasks 1.x）：**
1. `_compress` 现状（核实于 context_mgr.py）：`system_msgs = [非 system 之外]` / `conv_msgs` 二分；`tail = _select_tail(conv_msgs, keep_recent, target, system_msgs)`；`to_summarize = conv_msgs[:len-len(tail)]`；组装 `[*system_msgs, summary_msg, *tail]`。摘要消息 content 以 `[Earlier conversation summary]` 前缀。
2. `_select_tail` 的 `fixed = estimate_tokens(system_msgs) + _SUMMARY_OVERHEAD_TOKENS(512)`，从 `keep_recent` 向下收缩到投影 `<= target`，下界 `_keep_tail(conv_msgs, max(n,1))` 即 1 条；扩展为「头部完整层」后投影口径自洽（只是 `fixed` 的被估对象由 system 改为 head）。
3. `_keep_tail` 用 `m is tail[0]`（identity check）保 tool-pair 完整；头部去重（D4）同样用 `id(m)` 集合（identity），不用 `==`。
4. `config.Settings` 为 pydantic `BaseSettings`，加 `compression_initial_intent_max: int = 2`（带默认、可选，env `COMPRESSION_INITIAL_INTENT_MAX` 覆盖）；`_default_config()` 透传为 config dict 的 `initial_intent_max` 键。现有 `tests/test_context_mgr.py` 开头样例首条多为 `system`，其后接 user/assistant 交替——开头连续 user 段通常 1 条，默认上界 2 不会误纳更多。

**实现：**
- D1 三层切分：`_compress` 重构为 `head = _select_head(messages, max_intent)`、`tail = _select_tail(conv_msgs, ..., head)`、`middle = messages 中 id 既不在 head 也不在 tail 的剩余`；组装 `[*head, summary_msg, *tail]`。
- `_select_head`：真 system 提示（`role=="system"` 且 **content 不以 `[Earlier conversation summary]` 前缀**）+ `_initial_intent(conv_msgs, max_intent)`（开头连续 user 段，遇首条非 user 即停，受上界约束，返回**原对象**以保 identity 去重有效），按原顺序。
- **head 如何排除自产摘要**：新增常量 `_SUMMARY_PREFIX = "[Earlier conversation summary]"` 与 `_is_self_produced_summary(msg)`（`role=="system"` 且 `_content(msg).startswith(_SUMMARY_PREFIX)`）。`_select_head` 的 system 过滤排除该类消息，使上一次压缩产出的摘要消息**不被提升进 head**；它既不在 head 也（一般）不在 tail，于是落入 `middle` → 进 `_pre_cleanup` → `_summarize`，即仍留在摘要槽（AR13 场景下按既有方式被重新摘要；AR14 合入后由 AR14 提取其 `prev_summary` 折叠）。
- **middle 如何接 _pre_cleanup**：middle 即「既非 head 也非 tail」的剩余消息（含被排除的旧摘要消息、中段早期对话），原封交 `_pre_cleanup(middle)`（AR15 保留，纯规则、不调 LLM）再 `_summarize`。摘要消息 content 改用 `f"{_SUMMARY_PREFIX}\n{summary_text}"`（与原字面量等价，集中常量）。
- D3：`_select_tail` 第 4 参由 `system_msgs` 改名 `head`，`fixed = estimate_tokens(head) + _SUMMARY_OVERHEAD_TOKENS`；head 较大时尾部相应收缩，仍保 1 条下界与 tool-pair 完整。
- D4 退化兜底：`middle` 为空时**不生成空摘要消息**，直接返回 `[m for m in messages if id(m) in head_ids or id(m) in tail_ids]`（按 messages 原顺序遍历，天然去重 + 保序，head/tail 重叠的同一条只保留单份）。
- D2 配置：`config.py` 加字段 + `_default_config` 透传 `initial_intent_max`；`config/settings.yaml.example` 补注释示例（该文件存在）。

**自解冲突：**
- AR15 既有用例 `test_compress_runs_pre_cleanup_before_summarize`：原把含 base64 图片的**首条 user 消息**置于会话开头，AR13 下该消息成为受保护 head（初始意图）而不再进摘要，断言「base64 已从摘要输入清出」失败。**最小改动**：在该测试中于图片消息前插入「user 引子 + assistant 应答」，使 assistant 打断初始意图连续 user 段，图片消息落入被摘要的 middle，从而仍验证 AR15「pre-cleanup 先于 summarize」语义（不削弱断言）。这是规格强制的行为变更（head 不进摘要），非回归。

**影响：** pytest 830 passed（基线 813 + 新增 17，无回归，AR12/AR15 既有用例全绿）；ruff format+check：改动文件全绿（context_mgr.py / tests 经 format 各重排 1 处长行，check All passed）；mypy：base 73 errors → after 73 errors（无新增错误模式；`context_mgr.py` 内唯一 mypy 报错为既有 `Settings()` 缺 `anthropic_api_key` 调用模式，行号因新增常量上移，非新增）。

**需 zy 核实：**
1. ⚠️**(编排者更正 + AR14 硬性输入)** 旧摘要消息（`[Earlier conversation summary]` 前缀、`role==system`）在 AR13 下落入 middle,但 `_summarize` **只摘 user/assistant、跳过 system 消息**——故旧摘要内容实际**被丢弃而非"重新摘要"**。单次压缩(最常见)无旧摘要、不受影响;**重复压缩**(第二次及以后)会丢失上一次摘要覆盖的最早上下文。设计 D1 明确这是过渡态、由紧接的 **AR14(compression-incremental-summary,本轨下一个 change)MUST 提取旧摘要的 prev_summary 折叠进新累积摘要** 根治,AR14 实现时务必接住此点。确认此过渡(单压正确、重复压缩暂丢最早摘要、AR14 修复)可接受。
2. head/tail identity 去重用 `id(m)` 集合而非逐一 `is` 扫描——等价于 identity 语义，仅实现形式不同。确认认可。
3. D2 默认上界 2 已定；对「开头是 system 之外但首条 conv 非 user（如先 assistant 开场）」退化为空初始意图（仅 system 进 head），与现状等价、不劣化。

## compression-incremental-summary — feat/compression-incremental-summary

**前置核实结论（tasks 1.x）：**
1. `_summarize` 现状：拼 user/assistant 文本一次性摘、`max_tokens=512`、异常返回占位文本 `[Earlier conversation summary unavailable]`（仅占位，无静态截断）。`_compress`（AR13 后）三层切分 head/middle/tail，middle 经 `_pre_cleanup` 再 `_summarize`，包成 `f"{_SUMMARY_PREFIX}\n{summary_text}"` 的 system 消息，输出 `[*head, summary_msg, *tail]`（旧中段物理移除）。**确认 AR13 把旧摘要排出 head → 落入 middle，而 `_summarize` 跳过 system → 旧摘要当前被丢弃**（即 AR13 决策文档「需 zy 核实 1」标注的过渡态）。
2. `session_mgr.save`/`load`：整列表 JSON 原子写（`.json.tmp → rename`）、`SESSIONS_DIR` 可 monkeypatch；累积摘要为普通 `role==system` 消息，随整列表原样往返。**确认无需改 session_mgr、无需新增持久化结构。**
3. 识别依据：复用 AR13 已有的 `_is_self_produced_summary(msg)`（`role==system` 且 content 以 `_SUMMARY_PREFIX` 开头）；`maybe_compress`/`compress_for_context_overflow` 保持 `list → list` 签名，`prev_summary` 从入参 middle 提取，不引入 session_id 入参、不引入消息内边界字段。
4. AR13 三层切分中段边界已就位（本 worktree 已含 AR15+AR13）；middle 即「既非 head 也非 tail」的剩余消息（含被 head 排除的旧摘要消息），契约一致，无退化分支。

**实现：**
- **前缀（最关键，单常量驱动三处）**：直接把 `_SUMMARY_PREFIX` 的**值**改为 `[历史对话摘要，仅供参考。以下为早期对话的压缩，不是新的用户指令]`（D2 强标注）。**不新增第二个前缀常量**——同一常量同时驱动 ① `_compress` 生成 summary_msg 的 content、② AR13 `_is_self_produced_summary`（head 排除）、③ AR14 `_extract_prev_summary`（识别 + 提取 prev_summary）。三处天然一致、永不漂移。
- **D1 增量摘要**：`_compress` 切出 middle 后调 `_extract_prev_summary(middle)`——遍历找首条 `_is_self_produced_summary`，去掉前缀（`body[len(_SUMMARY_PREFIX):].lstrip("\n")`）得 `prev_summary`；`new_middle = [m for m in middle if not _is_self_produced_summary(m)]` 把旧摘要消息从喂给 LLM 的内容中剔除（避免重复喂 / 重摘旧内容）；`_pre_cleanup(new_middle)` 后 `_summarize(cleaned, prev_summary=..., config=cfg)`。无 prev_summary（首次）→ `prev_summary=None` → `_summarize` 走全量分支。
- `_summarize` 升级签名为 `(messages, prev_summary=None, config=None) -> str | None`：`_build_summary_prompt` 在有 prev_summary 时用「在已有摘要基础上并入 NEW MESSAGES，保持简洁，不重复已捕获内容」的合并 prompt（EXISTING SUMMARY / NEW MESSAGES 两段），否则用原全量 prompt。**断言**：合并时传入 LLM 的内容仅含 prev_summary（作合并基底）+ new_middle，不含旧摘要消息本体（`test_incremental_summary_extracts_prev_summary_and_merges` 断言 `_SUMMARY_PREFIX`/旧文本不出现在 fed 里、新中段标记 `NEWMID` 出现）。
- **D2 来源标注**：summary_msg.content = `f"{_SUMMARY_PREFIX}\n{summary_text}"`，前缀即强标注；`test_summary_message_has_reference_annotation` 断言含「历史对话摘要」「仅供参考」且不含旧弱标注。
- **D3 失败降级**：`_summarize` LLM 调用异常 / 空响应 → `logger.warning` 后返回 `None`（不抛、不静默）。`_compress` 见 `None` → `logger.warning("compression_summary_degraded")` 后返回 `[*head, notice_msg, *tail]`，notice_msg 为静态 `_MIDDLE_OMITTED_NOTICE`（「中段对话已省略…」，纯规则、不调 LLM）。降级序列合法（头尾完整 + 中段省略标注），主循环不中断。
- **D6 不无限增长**：合并摘要受 `summary_max_tokens` 上界（默认 `_DEFAULT_SUMMARY_MAX_TOKENS=512`，经 config dict 注入，非全局可变）约束传给 LLM 的 `max_tokens`；超长 prev_summary 仍只产出 ≤ 上界的新累积摘要，故收敛而非线性堆叠（替代「拼接」方案，避免摘要自身超 Tretained）。
- **D4 跨加载延续**：未改 session_mgr / 未改 `maybe_compress` 签名 / 未加持久化结构；累积摘要作普通 system 消息往返，`test_cumulative_summary_round_trips_and_stays_incremental` 验证 save→load→再压缩时 `_extract_prev_summary` 从往返回来的消息取到 prev_summary。
- 新增 `structlog` logger（模块顶部）承载降级日志。
- 既有测试适配：① `test_summarize_exception_returns_placeholder` → `..._returns_none`（断言 `is None`）；② 12 处 1 参 `_summarize` lambda monkeypatch + 2 处具名 stub 改为 `(msgs, prev_summary=None, config=None)`；③ 3 处硬编码 `[Earlier conversation summary]` 改引 `cm._SUMMARY_PREFIX`；④ 2 处「`"summary" in content.lower()`」断言（旧英文前缀含 summary）改为 `startswith(cm._SUMMARY_PREFIX)`。均为前缀 / 签名变更的必然适配，非行为回归。

**自解冲突：**
- 旧 `_summarize` 异常返回占位文本 vs D3 要求结构化静态降级：选「`_summarize` 返回 `None` 作失败信号、降级路径放 `_compress`」——`_summarize` 只负责「成功返回文本 / 失败返回 None」，头尾保留 + 中段截断的静态兜底由 `_compress` owns（与三层切分同处，复用既有 head/`_keep_tail`）。最小改动且职责清晰。
- `_summarize` 新增 `config` 第三参 vs 既有大量 1 参 lambda monkeypatch：选「`config` 带默认 `None`、`prev_summary` 带默认 `None`」保持可单参调用（既有 `cm._summarize([...])` 直调测试不破），但 `_compress` 内部以关键字 `prev_summary=/config=` 调用，故所有 monkeypatch lambda 必须显式带这两个形参——已统一适配。
- 降级 notice 粒度（全丢 vs 保留中段首尾）：选「全丢中段、插一条静态 system 标注」——spec 只约束「降级后序列合法且不崩溃」，全丢最简且头尾已完整保留，避免再引入对 new_middle 的截断规则。

**是否修复 AR13「旧摘要被丢弃」过渡态：是，已修复。** AR13 下重复压缩时旧摘要消息落入 middle 但被 `_summarize` 跳过而丢弃（最早上下文流失）。AR14 在 `_compress` 切出 middle 后**显式 `_extract_prev_summary` 提取旧摘要文本作 prev_summary**，与新增中段一起交 LLM **合并为新累积摘要**，不再丢弃。`test_cumulative_summary_round_trips_and_stays_incremental` 往返后第二次压缩断言 `call_log[-1] == "ACCUMULATED-V1"`（即上一次累积摘要文本被作为合并基底传入），证明重复压缩现在在 prev_summary 上增量、不再丢最早上下文。

**影响：** pytest 841 passed（基线 830 + 新增 11，无回归；AR12/AR13/AR15 既有用例全绿，含已适配的前缀 / 签名引用）；ruff format+check（仅改动文件 `context_mgr.py` / `tests/test_context_mgr.py`）：format 重排测试文件若干长行，check All passed；mypy：base 73 errors → after 73 errors（无新增错误模式；`context_mgr.py` 内唯一报错仍为既有 `Settings()` 缺 `anthropic_api_key` 调用模式，行号因新增常量从 39 → 55，非新增）。

**需 zy 核实：**
1. 降级时**中段全丢**（仅留一条 `_MIDDLE_OMITTED_NOTICE` 标注）——而非保留中段首尾极少量。spec 只约束「降级后序列合法不崩溃」，已满足；确认全丢可接受（降级为故障兜底而非常态）。
2. D6 收敛策略采「合并摘要受 `summary_max_tokens` 上界约束 LLM 输出长度」即天然收敛，**未额外实现「超界整体重摘一次」的显式二次调用**——因合并 prompt 每次都把 prev_summary 压回 ≤ 上界，累积摘要不会线性堆叠，已满足「不无限增长」。确认无需额外的显式重摘分支。
3. `summary_max_tokens` 仅经 config dict 注入，**未加进 `config.Settings` / `_default_config()`**（沿用既有 `_DEFAULT_SUMMARY_MAX_TOKENS` 常量 + config dict 覆盖模式，与 AR13 `initial_intent_max` 不同——后者进了 Settings）。若需运维侧可配，可后续补 Settings 字段；当前默认 512 与原 max_tokens 一致，行为等价。确认此差异可接受。

---

## 8. loop-detection (AR4)：主循环粗粒度循环检测 checker

**前置核实结论（tasks 1.x）：**
1. **AR1 接口（1.1）**：`termination.py` 现状已含 `StopReason.loop_detected`（保留原因码，无需新增枚举）、`LoopState`（@dataclass）、`TerminationChecker` Protocol（`check(state: LoopState) -> StopReason | None`）、`TerminationController.register`/`should_stop`（顺序评估、首个非 None 即返回）。本 change 仅新增 checker + 扩展 `LoopState`，未改 Protocol/Controller 语义。
2. **主循环工具落点（1.2）**：`run()` 工具分发后 `messages.append({"role":"tool", "tool_call_id":tc.id, "content":result})` 处可同时拿到 `tc.function.name`/`tc.function.arguments`/`result`/`failed`（`_safe_dispatch` 归一化字符串 + failed 标志）四者。三条分支（sub_agent / approval-rejected / 普通 dispatch）中只有两条 dispatch 分支设 `failed`，已在循环体引入 `failed = False` 默认（覆盖 sub_agent=成功、approval-rejected=不计 failed），保证四元组成功标志在所有分支可取。`run_stream()` 同理在 `_safe_dispatch` 后落点可取 `name/args/result/failed`。
3. **`_build_controller` 注册顺序（1.3）**：在 `MaxTurnsChecker`/`ConsecutiveFailuresChecker`/`ApprovalRejectedChecker` **之后** `register(LoopDetectionChecker(...))`。`should_stop` 首个非 None 即返回 → 既有三者优先级不变；空历史时 checker 恒返回 None，对既有用例零影响（既有 `test_build_controller_*` 适配为解包元组后断言不变）。
4. **message_hygiene / 压缩可见性（1.4）**：`_fix_consecutive_same_role` 只对相邻同角色 user/assistant 文本合并；警告用 `user` 角色且紧跟一批 `tool` 结果之后（前一条非 user），不触发同角色合并，独立可见。`maybe_compress` 的 `_keep_tail` 按尾窗保留，但销毁式压缩可能丢中段——故 D4b 落点选「压缩**之后**、sanitize/LLM 调用**之前** append 警告」，使其必在送 LLM 序列中（见实现）。
5. **config 字段（1.5）**：`config.Settings` 加 `agent_loop_repeat_threshold: int = 3`、`loop_detect_ignore_arg_keys: list[str] = []` 即经 `.env`/`settings.yaml` 覆盖（pydantic-settings env 大写自动映射，已测 `AGENT_LOOP_REPEAT_THRESHOLD` override）。

**实现：**
- **新建 `src/fleetent/loop_detector.py`**（结构 import→常量→纯函数→checker 类）：
  - `arg_fingerprint(arguments, ignore_keys=())`：JSON 解析→（非空 ignore_keys 时剔除顶层键）→`json.dumps(sort_keys=True)`→sha256；解析失败对原始串取 sha256。键序无关、易变键可选剔除。
  - `result_digest(result)`：`len ≤ 2KB` 全量、否则取首尾各 `_DIGEST_EDGE_BYTES=1024` 字符拼接，再 sha256。常数级、字节级比对。
  - `LoopDetectionChecker(repeat_threshold, ignore_arg_keys=())`：`window` 属性 = 派生常量 `max(2*threshold, 6)`（不暴露配置）；`ignore_arg_keys` 属性供主循环算指纹用。
- **`termination.py` 扩展 `LoopState`**（默认空 / False，向后兼容）：`tool_history: list[ToolCallRecord]`（四元组 `(tool_name, arg_fingerprint, result_digest, success)`）、`loop_warning_requested: bool=False`、`loop_warning_injected: bool=False`；新增 `record_tool_call(..., *, window)` 方法 append 后 FIFO 截断到 window（`del self.tool_history[:-window]`），不保留全量。新增 `ToolCallRecord` 类型别名。
- **`agent_loop.py` 接入**：`_LOOP_WARNING_TEXT` 常量（D4 文案）；`_resolve_loop_config`（call param > Settings > 默认，lazy import Settings）；`_build_controller` 改为返回 `(controller, loop_checker)` 元组并末位注册 checker；`_maybe_inject_loop_warning(messages, state)` 在 `loop_warning_requested and not loop_warning_injected` 时 append `{"role":"user","content":_LOOP_WARNING_TEXT}` 并置 `loop_warning_injected=True`（幂等）。`run()`/`run_stream()` 两路径：① 解包 `_build_controller`；② `maybe_compress` **之后** 调 `_maybe_inject_loop_warning`（D4b）；③ 每次工具调用落点后 `state.record_tool_call(name, arg_fingerprint(args, loop_checker.ignore_arg_keys), result_digest(result), not failed, window=loop_checker.window)`。
- **config.py / settings.yaml.example**：加两字段 + 注释示例。

**双信号 + 两段式落地：**
- **信号 A（精确重复）**：`_has_repeat` 在尾窗内 `Counter((tool, fp))`，任一计数 ≥ threshold 即命中。
- **信号 B（结果停滞）**：尾窗内 `Counter((tool, digest) for ... if ok)`（**仅成功**调用计入，失败被排除，避免与 consecutive_failures 双重计数），任一计数 ≥ threshold 即命中，**不论参数是否变化**。
- **两段式**：`check()` 中 `_has_repeat` 命中后——若 `loop_warning_injected` 已 True → 返回 `StopReason.loop_detected`（第二段终止）；否则置 `loop_warning_requested=True`、返回 None（第一段请求警告，不终止）。
- **警告角色/可见性（D4/D4b）**：角色定死 `user`（不会被 `_fix_consecutive_same_role` 与首位 system 合并）。D4b 落点：警告在 `maybe_compress` 之后、`sanitize`/LLM 调用之前 append——即便该轮触发销毁式压缩，警告也在压缩产物**之上**追加，必出现在送 LLM 序列中。`test_run_warning_survives_same_round_compression` 用「压缩丢弃除首条 system 外全部消息」的 mock 守卫：断言压缩后某次 LLM 调用的 messages 仍含 `user` 角色警告文本。

**checker 如何「请求注入警告」（返回值/信号设计）：** checker 不直接改 messages（保持纯判定、只读 + 写状态标志）。它通过在 `LoopState` 上置 `loop_warning_requested=True` 并返回 `None`（不终止）来「请求」；主循环在下一段 `_maybe_inject_loop_warning` 读该标志决定是否 append 警告并置 `loop_warning_injected`。即「checker 写请求标志 / 主循环执行注入」的状态驱动协议，沿用 AR1「标志位驱动循环」模式，判定逻辑全在 checker 内、主循环只记录历史 + 按请求注入。

**自解冲突：**
1. **`_build_controller` 返回值由 controller 改为 `(controller, loop_checker)` 元组** —— 主循环记录历史时需 checker 的 `window`/`ignore_arg_keys` 派生量。选返回元组而非另设全局/重复解析配置（禁止全局可变状态）。两处调用与 1 处既有测试已适配（`controller, _ = ...` / `controller, loop_checker = ...`）。
2. **多分支 `failed` 标志缺失** —— sub_agent 与 approval-rejected 分支原不设 `failed`。引入循环体级 `failed = False` 默认：sub_agent 记为成功（与其 `consecutive_failures=0` 语义一致、视作有进展）、approval-rejected 记为「非失败」（其终止由 approval_rejected 优先处理，不应喂信号 B）。最小改动，不动既有 consecutive_failures 计数语义。
3. **checker 私有 `_ignore_arg_keys` 外部访问** —— 主循环需读以算指纹。加只读 `ignore_arg_keys`/`window` property，避免下划线私有属性跨模块访问，符合风格。
4. **Settings 调用触发 mypy `[call-arg]`** —— `_resolve_loop_config` lazy `Settings()` 与既有 `termination._default_config`/`context_mgr._default_config` 同模式，属既有遗留错误模式（`Missing named argument "anthropic_api_key"`），非新模式。
5. **`record_tool_call` 的 window 注入** —— window 不存模块级常量（禁止全局可变状态），由 checker 派生属性按调用传入，per-run 隔离。

**影响：**
- pytest：base **841 passed → after 874 passed**（新增 33：test_loop_detector 20 + test_termination 6 + test_config 3 + test_agent_loop 6−2 复用... 实测净 +33；AR1 既有终止用例全绿不破，含适配后的 `test_build_controller_*`）。
- ruff（仅改动文件 `loop_detector.py`/`termination.py`/`agent_loop.py`/`config.py` + 4 个测试文件 + `settings.yaml.example`）：format 重排 3 文件；check —— 新建/改动文件 **All passed**，唯一报错为 `agent_loop.py:721` 的 `PLC0415`（`from openai.types import CompletionUsage` 函数内 import），经 `git stash` 验证为 **基线即存在**（HEAD 同位置同错），非本 change 引入。
- mypy：base **73 errors → after 74 errors**。新增 1 条为既有 `Missing named argument "anthropic_api_key" for "Settings"` 模式的又一处（13→14，源自 `_resolve_loop_config` 的 `Settings()`），**无新增错误模式（错误类型）**。

**需 zy 核实：**
1. **sub_agent / approval-rejected 分支记 `success=True`（not failed=True）**：sub_agent 视作有进展（与其重置 consecutive_failures 一致）；approval-rejected 不计失败（由 approval_rejected 原因码优先终止）。确认此归类符合「信号 B 只计成功且有进展」语义、不致 sub_agent 反复同结果被误判循环（实际 sub_agent 极少在窗口内反复同 digest，风险低）。
2. **警告文案**（`_LOOP_WARNING_TEXT`）措辞定死为「检测到你正在重复调用同一工具且似乎没有进展，请改用其它方式或直接给出当前结论。」，与 design D3 示例一致。确认无需调整。
3. **`loop_detect_ignore_arg_keys` 仅剔除顶层 key**（不递归嵌套）：design D2 表述「剔除指定键」，实现按顶层 dict 键剔除。确认顶层粒度足够（嵌套易变键场景留信号 B 兜底）。
