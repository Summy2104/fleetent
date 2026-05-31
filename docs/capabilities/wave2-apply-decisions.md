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

