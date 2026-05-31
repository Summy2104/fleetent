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

## 9. cancellation-propagation (AR19)：贯穿主循环与工具调用的单向 cancel token 通路

**前置核实（tasks 1.x，无代码改动）：**
- **1.1 AR1 接口**：`termination.py` 的 `TerminationChecker` Protocol、`TerminationController.register`/`should_stop`、`StopReason.cancelled`（行 63）均已存在；本 change 仅新增 `CancellationChecker` + 透传 token，不改 AR1 既有判定。
- **1.2 主循环检查点**：`run()`（行 290 区域）与 `run_stream()`（行 487 区域）每轮开头 `controller.should_stop(state)`，是循环体第一步——已取消 token 在「下一次 LLM 调用前」即被捕获（`run()` 检查点在 LLM 调用之前；`run_stream()` 检查点也在 `_stream_with_fallback` 之前，仅 `state.turn += 1` 在其后，不影响首轮拦截）。
- **1.3 工具调度链**：`dispatch`（行 61）唯一外部调用点是 `_safe_dispatch`（行 108）；`_safe_dispatch` 在 `run()` 有两处调用（approved 分支、非 gated 分支）、`run_stream()` 一处。token 注入位置即此三处 + `_safe_dispatch→dispatch`。
- **1.4 容器生命周期**：`run_code`（tools.py 行 123）内 `client = SandboxClient(); ws_id = await client.create_workspace(...)`——`ws_id` 局部于 `run_code`，`SandboxClient` 实例不持有；故硬中止编排归 `run_code`（它持 `ws_id`），`SandboxClient` 仅保证 `destroy_workspace` 幂等。现状 `destroy_workspace` 用 DEVNULL 且不检查 returncode，已天然幂等（`rm -f` 失败不抛），本 change 将该保证文档化为契约。
- **1.5 `_build_schema` 排除 + dispatch opt-in**：`_build_schema`（行 85）遍历 `inspect.signature` 全部形参，无默认值进 `required`；选定判据为「形参名 == `cancel_token`」识别 opt-in，`_build_schema` 跳过该形参（properties/required 均不含）、`dispatch` 仅对声明该形参的工具追加 `cancel_token=` kwarg。未声明的存量工具签名与 schema 字节级不变。

**实现：**
- **新建 `src/fleetent/cancellation.py`**（import→常量→数据类→类）：
  - `CancelToken`（dataclass）：`deadline: float | None = None`（基于 `time.monotonic()` 的绝对截止）+ `_cancelled: bool = False`。`cancel()` 幂等置 `_cancelled=True`；`is_cancelled()` = `_cancelled or (deadline is not None and monotonic() >= deadline)`，合并「显式取消」与「超 deadline」为单一查询出口。`CancelToken()` 永不取消（默认值用）、`CancelToken(deadline=...)` 带硬截止。
  - `CancellationChecker(token)`：实现 `TerminationChecker`，`check()` 在 `token.is_cancelled()` 时返 `StopReason.cancelled` 否则 None。
  - 常量 `CANCEL_TOKEN_PARAM = "cancel_token"`（对外发布的 opt-in 形参名约定）。
- **`tool_registry.py`**：常量 `_CANCEL_TOKEN_PARAM = "cancel_token"`；`_accepts_cancel_token(fn)`（`inspect.signature` 判形参名）；`dispatch` 新增 `cancel_token: Any = None`，仅当 `cancel_token is not None and _accepts_cancel_token(fn)` 时把 `kwargs["cancel_token"] = cancel_token`；`_build_schema` 遍历时 `if param_name == _CANCEL_TOKEN_PARAM: continue` 跳过。
- **`agent_loop.py`**：import `CancellationChecker, CancelToken`；`_build_controller` 新增 kwarg `cancel_token: CancelToken | None = None`，非 None 时**首位**注册 `CancellationChecker`（短路优先级最高）；`_safe_dispatch` 新增 `cancel_token` 形参透传 `dispatch`；`run()`/`run_stream()` 各新增 `cancel_token: CancelToken | None = None`，None → 构造永不取消默认 token，传入 `_build_controller` 与三处 `_safe_dispatch`。
- **`tools.py`**：常量 `_CANCEL_POLL_INTERVAL = 0.05`；新增 `_exec_or_cancel(client, ws_id, command, token)`——`exec_task = create_task(client.exec(...))`，循环：token 取消则 `exec_task.cancel()` + `gather(..., return_exceptions=True)` + `client.destroy_workspace(ws_id)` 返回 None；否则 `asyncio.wait({exec_task}, timeout=poll)`，exec 完成即返回 result。`run_code` 新增 `cancel_token: CancelToken | None = None`（None→默认 token），调 `_exec_or_cancel`，result 为 None 时返回 `"code execution cancelled"`；`finally` 仍兜底 `destroy_workspace`（幂等，已销毁则 no-op）。正常路径不销毁中途容器、行为不变。
- **`sandbox_client.py`**：`destroy_workspace` docstring 文档化幂等契约（实现已天然幂等，未改逻辑）。

**自解冲突：**
1. **opt-in 判据选「形参名 cancel_token」而非 `@tool` 注册标记** —— design D3 允许「注册标记 或 形参名约定」二选一。选形参名约定：零侵入（工具只需声明形参即可既被注入又自动从 schema 排除，单一判据 `_accepts_cancel_token` 同时服务 dispatch 与 `_build_schema`），无需扩展 `@tool` 装饰器签名 / 注册表结构。与 design「按 `@tool` 注册标记或形参名 `cancel_token` 约定识别」一致。
2. **`CancellationChecker` 注册位置选首位** —— design 未强制顺序；选首位使「已取消」短路优先于 max_turns 等，符合「取消是最高优先的外部意图」直觉，且默认永不取消 token 下该 checker 永不触发，不改无 token 路径的既有优先级（max_turns/consecutive_failures/approval_rejected/loop_detected 相对顺序不变）。
3. **`destroy_workspace` 幂等已天然成立，6.2 测试直接绿** —— TDD 下「该测试未经实现即绿」。判定：现状 DEVNULL + 不检查 returncode 即是幂等的实现，6.2 测试是对既有可观察行为的契约固化（spec MODIFY sandbox-client 要求「提供幂等强制销毁」）。未为凑红而引入多余逻辑；改为补 docstring 把幂等从「偶然」提升为「契约」。
4. **`dispatch` 的 `cancel_token` 类型注解用 `Any`** —— tool_registry 不依赖 cancellation 模块（避免循环 import：cancellation 已 import termination，tools 已 import cancellation+tool_registry）。`dispatch` 只透传不解引用 token，用 `Any` 注解保持 tool_registry 对 CancelToken 零依赖、不引入新 import 边。
5. **`run_stream` 取消后收尾** —— 取消在检查点命中即 `break`，正常落到 `yield {"type":"done",...}` 出口，不泄漏半截事件（测试 `test_run_stream_cancelled_stops_before_llm_and_finishes_clean` 守卫 `events[-1]["type"]=="done"`）。
6. **D5 trace** —— `cancelled` 经现有 `log_run(..., stop_reason=stop_reason)` 出口写，复用既有 `ts`/`elapsed_s`，未新增 trace 字段/出口（测试 `test_run_cancelled_logs_stop_reason_cancelled` 守卫）。

**CancelToken 接口最终形态（对外契约，波次 3 T2/SB7 依赖，锁定）：**
```python
@dataclass
class CancelToken:
    deadline: float | None = None   # 绝对 time.monotonic() 截止；None 无截止
    _cancelled: bool = False
    def cancel(self) -> None: ...               # 幂等置已取消
    def is_cancelled(self) -> bool: ...         # _cancelled 或 已超 deadline → True
# CancelToken() 永不取消（默认值）；CancelToken(deadline=now+timeout) 即超时语义
CANCEL_TOKEN_PARAM = "cancel_token"             # 工具 opt-in 形参名约定
class CancellationChecker:                       # TerminationChecker
    def __init__(self, token: CancelToken) -> None: ...
    def check(self, state) -> StopReason | None: ...  # cancelled / None
```
波次 3 仅以 `CancelToken(deadline=time.monotonic()+timeout)` 复用，不改接口。

**token 带外注入 + `_build_schema` 排除如何实现、存量工具是否真不变：**
- 注入：`dispatch` 仅对声明 `cancel_token` 形参的工具（`_accepts_cancel_token`）追加 `cancel_token=` kwarg；其余工具调用 `fn(**kwargs)` 字节级不变（测试 `test_dispatch_does_not_inject_token_into_non_opt_in_tool` 守卫）。
- 排除：`_build_schema` 跳过名为 `cancel_token` 的形参，故 opt-in 工具的 LLM-facing schema 的 properties/required 均不含 token（`test_schema_excludes_cancel_token_param` 守卫），不会被当 string 必填字段误导 LLM；未声明 token 的工具 schema 完全不变（`test_schema_unaffected_for_tool_without_token` 守卫）。
- **存量工具真不变**：全量 874 基线用例无回归（含所有未 opt-in 工具的 dispatch/schema 用例）。当前唯一 opt-in 工具是 `run_code`。

**run_code 硬中止编排 + destroy 幂等如何实现：**
- 编排（`_exec_or_cancel`）：`exec_task = create_task(client.exec)`；轮询（poll 0.05s）观察 `token.is_cancelled()`，取消时 `exec_task.cancel()` + `gather(return_exceptions=True)`（吞 CancelledError，不静默业务异常）+ `client.destroy_workspace(ws_id)` 强制 `docker rm -f` 中止悬挂 exec、返回 None → `run_code` 返回 `"code execution cancelled"`。正常路径：exec 先完成即返回 result，不销毁中途容器。
- destroy 幂等：`SandboxClient.destroy_workspace` 用 DEVNULL 且不检查 returncode，`rm -f` 对已删容器报错也不抛；故取消路径销毁后，`run_code` 的 `finally` 兜底二次 destroy 不重复抛（测试 `test_destroy_workspace_is_idempotent_when_container_absent`、`test_run_code_cancel_path_finally_does_not_double_raise` 守卫）。

**影响：**
- pytest：base **874 passed → after 897 passed**（新增 23：test_cancellation 8 + test_tool_registry 5 + test_tools 3 + test_sandbox_client 1 + test_agent_loop 6）。AR1/AR4 既有终止用例全绿；不传 token 的现有用例字节级不变（`test_run_default_no_token_behaves_normally` 显式守卫）。
- ruff（仅 format/check 改动文件：`cancellation.py`/`tool_registry.py`/`tools.py`/`sandbox_client.py`/`agent_loop.py` + 5 测试文件）：新建/主改文件 **All checks passed**。残留报错（`agent_loop.py:740` N814 `_CU`、`tools.py` cron_scheduler F401、`test_sandbox_client.py` ExecResult F401 + SIM117）经 `git stash` 验证为**基线即存在**（HEAD 同位置同错，7 errors），非本 change 引入；format 仅对这些既有文件做了等价长行重排（无功能改动）。
- mypy：base **74 errors → after 74 errors**，错误码分布不变（`cancellation.py` 新增 0 错误，checked 50→51 files），**无新增错误模式**。

**需 zy 核实：**
1. **opt-in 判据用形参名 `cancel_token` 约定**（非 `@tool` 注册标记）：与 design D3「注册标记 或 形参名约定」二选一，选了形参名（最小侵入、单一判据复用于 dispatch + `_build_schema`）。确认接受此约定为对外契约的一部分（波次 3 工具若要接 token，需把执行体形参命名为 `cancel_token`）。
2. **取消结果文案 `"code execution cancelled"`**：`run_code` 取消时返回此固定串。确认措辞，及是否需要更结构化的取消标记（当前 cooperative 语义下作普通 tool_result 回喂 LLM，下一检查点由 `cancelled` 截停）。
3. **poll 间隔 `_CANCEL_POLL_INTERVAL = 0.05s`**：轮询观察 token 取消。确认该粒度（取消响应延迟 ≤ 50ms，CPU 开销可忽略）符合预期；若波次 3 偏好事件驱动可后续替换为 deadline 计算超时 + 事件，本 change 留轮询实现。
4. **`CancellationChecker` 注册于 controller 首位**（取消优先级最高）：design 未强制，确认此优先级语义。

---

## 10. iteration-budget-grace-call (AR2)

**改/建文件：**
- 新建 `src/fleetent/budget.py`（`BudgetConfig`/`BudgetUsage`/`BudgetChecker`/`MODEL_PRICING`/`DEFAULT_PRICING`/`NO_LIMIT`/`grace_max_tokens`）；对外计量契约（波次 3 AR18/MR2 依赖）。
- 修改 `src/fleetent/agent_loop.py`：`_build_controller` 退役 `MaxTurnsChecker`、注册 `BudgetChecker`，返回三元组 `(controller, loop_checker, budget_checker)`；`run()`/`run_stream()` 新增 `max_tokens`/`max_cost_usd` 参数、逐轮 `usage.add(...)`、`budget_exceeded` 终止时 Grace Call 收尾（非流式 `_grace_call`，流式内联）；新增 `_resolve_budget_config`/`_budget_add`/`_grace_call` 与 `_GRACE_CALL_TEXT` 常量、`logger`。
- 修改 `src/fleetent/termination.py`：删除已退役的 `MaxTurnsChecker` 类（不再注册，仅其单测引用），保留 `StopReason.max_turns` 枚举成员（更新注释为"compat / 不再产出"）。
- 修改 `src/fleetent/config.py`：新增 `agent_max_tokens`(-1)/`agent_max_cost_usd`(-1.0)/`agent_grace_call_token_ratio`(0.05)/`agent_grace_call_min_tokens`(512)。
- 修改 `src/fleetent/eval_logger.py`：`log_run` 末位 kw `budget_dimension: str | None = None`（仅非 None 写）。
- 修改 `config/settings.yaml.example`：补四个预算/Grace Call 字段示例。
- 测试：新建 `tests/test_budget.py`（22 例）；`tests/test_agent_loop.py` 新增 10 例 + 迁移 5 例；`tests/test_termination.py` 迁移 3 例 + 1 兼容例；`tests/test_config.py` +2 例。

**契约最终形态 + BudgetUsage 如何逐轮更新：**
- `BudgetConfig(frozen)`：`max_turns:int / max_tokens:int / max_cost_usd:float`，各以 `NO_LIMIT=-1` 表"无上限"；`exhausted_dimension(usage)` 按 `turns→tokens→cost_usd` 顺序返回首个达上限的维度名或 None。
- `BudgetUsage`（可变）：`turns/tokens/cost_usd`；`add(prompt_tokens, completion_tokens, model)` 是唯一累计入口——`turns += 1`、`tokens += prompt+completion`、`cost_usd += token/1000 × 单价`（查 `MODEL_PRICING`，表外用 `DEFAULT_PRICING`）。
- `BudgetChecker(config, usage)` 实现 AR1 `TerminationChecker`；任一维度达上限返 `StopReason.budget_exceeded` 并记 `triggered_dimension`。
- **逐轮更新落点（设计决策：usage 旁挂 + 显式 add）**：`BudgetUsage` 由 `run()`/`run_stream()` 各自 new 一个 per-run 实例，**传进 `_build_controller`** 给 `BudgetChecker` 持有引用；主循环每轮 LLM 调用返回后**显式调用同一 usage 的 add**（`run()`：`_budget_add(usage, response.usage, model)` 在 `state.turn += 1` 后；`run_stream()`：逐 chunk 累计该轮 `turn_prompt/completion_tokens`，内层 stream 结束后 `usage.add(...)` 结算）。checker 与主循环共享同一 usage 对象，下一检查点即据累计值判定。未用 `LoopState` 承载 usage（design D1 备选②），保持累计逻辑/单价换算内聚在 budget.py、可独立单测。

**§6b 退役 MaxTurnsChecker + 迁移的用例：**
- 退役：`_build_controller` 不再注册 `MaxTurnsChecker`，改注册 `BudgetChecker`（位置仍在 Cancellation 之后、ConsecutiveFailures 之前，优先级语义不变）；`MaxTurnsChecker` 类已删（唯一引用是自身单测）；`StopReason.max_turns` 枚举保留。
- 迁移（test_agent_loop.py，5 例）：`test_run_stops_at_max_turns`（断言改为 3 次调用[2 主 +1 grace]、result=grace 总结）、`test_build_controller_empty_history_yields_only_active_reasons`（用新签名 + 断言含 `budget_exceeded`）、`test_run_logs_stop_reason_max_turns`→`..._budget_exceeded_on_turns`（断言 `budget_exceeded`+`budget_dimension=="turns"`）、`test_run_stream_logs_stop_reason_max_turns`→同上流式版、`test_run_stream_stops_at_max_turns`（3 次调用、done 收尾）。
- 迁移（test_termination.py，3 例）：`test_max_turns_checker_*`（at/above/below limit）→ `test_step_budget_*`（用 `BudgetChecker` + step `BudgetConfig` 断言 `budget_exceeded` + `triggered_dimension=="turns"`）；新增 `test_stop_reason_max_turns_member_retained_for_compat`；保留 `StopReason.max_turns` 存在性/str 值用例（21/34/35/198 行）与把它当任意 stub 值的 controller-ordering 用例（不涉及"循环产出"语义）。

**Grace Call 如何实现：**
- `run()`（非流式 `_grace_call`）：终止 `stop_reason==budget_exceeded` 时，取 `budget_checker.triggered_dimension`，对 messages 追加 `_GRACE_CALL_TEXT`（"请用一段话总结…不要再调用工具"），以 `grace_max_tokens(budget_config.max_tokens)` 为 `max_tokens` 发起最后一次 `create`，输出作 reply。**降级**：`except Exception` 或 summary 为空 → 返回 `partial_reply`（终止前累积的 `msg.content`），`logger.warning` 记降级，不重试不崩溃。
- `run_stream()`（流式，内联）：命中后不直接 `done`，而是追加 grace 指令、以 reserved 上限**再发起一次流式 create**，逐 chunk `yield text_delta` 流出总结，再统一 `yield done`+`log_run(budget_dimension=...)`。**两类降级**：①未 yield 任何 delta 即失败（`any_delta==False`）→ 把 `partial_reply` 补发一次 `text_delta`（若非空）后 done；②已 yield 部分 delta 后失败（`any_delta==True`）→ 保留已流出内容（无法收回）、`logger.warning` 记降级、不回滚不重试、直接 done。两路都保证收到 done、不悬挂半截循环。
- Grace Call 自身 usage **不**计入主 `BudgetUsage`（D4/D6：用预留维度，主循环不为它调 add）。

**压缩豁免如何确认（D4 默认成立）：**
- 核实 `context_mgr.maybe_compress` 内部摘要 LLM 走它自己的 `get_client_and_config("memory_extraction")` + `client.chat.completions.create`（context_mgr.py:273/280），其 token **不流经** `agent_loop` 主循环的 `response.usage` / `_budget_add` / `BudgetUsage.add`。因此无需主动识别排除——只要不把压缩 token 接进 `usage.add` 即豁免。单测 `test_run_compression_tokens_not_counted_in_budget` 守卫：`maybe_compress` 被多次调用但 `BudgetUsage.tokens` 仅等于主循环单轮 token。

**自解冲突（C·全自主，最小改动）：**
1. **`grace_max_tokens` 基于 `BudgetConfig.max_tokens`（非 `cfg.max_tokens`）**：design D3 明确预留比例针对"主任务 token 预算"，故 `_grace_call` 形参收 `budget_max_tokens` 传 `budget_config.max_tokens`，不用 route 的输出上限。
2. **`MaxTurnsChecker` 类整体删除**（非仅退役注册）：proposal/tasks 未强制删类，但删后唯一引用仅其自身单测；保留即死代码，故删类、迁移单测、保留枚举。最小改动且与"步数并入 BudgetChecker"一致。
3. **`budget_dimension` 多维同超时的报告顺序**：`exhausted_dimension` 固定 `turns→tokens→cost_usd`，多维同超报 turns（确定性，便于 trace 统计）。
4. **`DEFAULT_PRICING` 取值** = `(0.015, 0.075)`（= 表内最贵 opus 档），注释"表外回退、宁高勿漏"、绝不计 0。
5. **流式 Grace Call 直接调 `client.chat.completions.create`（不走 `_stream_with_fallback`）**：与非流式 `_grace_call` 对称、且避免对 frozen `RouteConfig` 做 `dataclasses.replace`（mock cfg 是 MagicMock）；reserved 上限通过显式 `max_tokens=reserved` 传入。
6. **`_budget_add` 容错**：`response.usage` 缺失/非 int 时按 0 token 计、但仍 +1 turn——步数维度永不因 usage 缺失而停止累计。

**影响：**
- pytest：base **897 → after 932 passed**（净 +35 = test_budget +22 + test_agent_loop 新增 10 + test_termination 新增 1[兼容例] + test_config +2；迁移 8 例[test_agent_loop 5 + test_termination 3]为原地改写、不计净增）。AR4/AR19 既有用例全绿。
- ruff（仅本 change 改/建文件）：format **All unchanged**（无无关重排）；check 仅剩 `agent_loop.py` `_CU` N814——`git stash -u` 验证为基线即存在（HEAD 同位置），非本 change 引入。
- mypy：base **74 → after 76**，净 +2 均为 `Settings` `call-arg`（budget.py `_grace_defaults` + agent_loop.py `_resolve_budget_config` 的 `Settings()` 调用，与既有 `_default_config`/`_resolve_loop_config` 同模式），**无新增错误模式**。

**需 zy 核实：**
1. **预算默认 token/cost 维度为 `NO_LIMIT`（-1）**：不传 `max_tokens`/`max_cost_usd` 且未配 Settings 时，token/成本维度不生效，行为退化为纯步数预算（`agent_max_turns=50`）。确认这是期望的"向后兼容"默认（既有部署不被新维度意外拦截）。
2. **`MODEL_PRICING` 单价取值**：sonnet (0.003/0.015)、haiku (0.001/0.005)、opus (0.015/0.075) 美元/1K tokens 为静态估算值。确认与当前供应商实际单价大致吻合（仅用于止损估算、非账单）；`DEFAULT_PRICING=(0.015,0.075)` 表外保守回退是否过高需调。
3. **删除 `MaxTurnsChecker` 类**（见自解冲突 2）：确认接受删类而非保留空壳；若波次 3 或外部代码仍 import 该类需改回保留。
4. **Grace Call 指令文案 `_GRACE_CALL_TEXT`** 与"一段话总结"的长度约束依赖 reserved token 上限（默认 floor=512）：确认措辞与默认配额。
5. **`grace_max_tokens(NO_LIMIT)` 回退到 floor**：主 token 预算无上限时 Grace Call 仍以 floor(512) 为上限。确认该兜底语义。

## 11. mcp-session-management (MCP2)

**改/建文件：**
- 修改 `src/fleetent/mcp_client.py`：新增会话生命周期辅助 `_open_session`（initialize + 写 session_id + notifications/initialized，握手抽出供注册与重建复用）、`_expire_session`（置 None）、`_is_session_expired` / `_has_session_invalid_marker`（D1 失效识别）；`_post_jsonrpc` 增 `_allow_session_retry` 入参与失效重建分支；`close()` 新增 `_close_http_sessions`（对活跃 HTTP 会话发 DELETE）。`_register_http_server` 的内联握手替换为调用 `_open_session`。
- 修改 `tests/test_mcp_client.py`：新增 14 例（生命周期 4 + 调用期重建/重试 1 + 注册期重建 1 + 至多一次×2 + 认证不重建×2 + close DELETE×4）。

**前置核实结论（tasks 1.x）：**
- 1.1 握手/回携/raise 插入点：`_register_http_server`（原行 220）发 initialize、`init_resp.raise_for_status()` 后从响应头取 `Mcp-Session-Id` 写 `server.session_id`；`_base_headers`（原行 166）有 session_id 时回携；`_post_jsonrpc`（原行 189）`resp.raise_for_status()`（原行 199）——失效检测须前移到此 raise 之前（采用 D1a 方案 a）。
- 1.2 失效响应特征：404 为主锚点；401/403 判为认证错误**不**重建（上抛）；其余 4xx 仅当响应头 `Mcp-Session-Invalid` 或响应体含 session+(expired/invalid/not found) 标识才判失效。
- 1.3 `close()`（原行 108）仅清 stdio `_active_sessions`；`_server_registry` 为模块级 dict，可 `.values()` 遍历，按 `transport=="http" and session_id is not None` 筛活跃 HTTP 会话。
- 1.4 DELETE 端点：同 POST 端点 `{url}/`，携 `Mcp-Session-Id` 头（复用 `_base_headers`），符合 Streamable HTTP 规范。

**D1a 失效检测落点（方案 a·前移）：**
- 在 `_post_jsonrpc` 中 `resp = await client.post(...)` 之后、`resp.raise_for_status()` **之前**，先 `_is_session_expired(resp)` 判定。命中且允许重试则进入重建分支（不 raise）；不命中再走原 `resp.raise_for_status()` → 解析 → JSON-RPC error 检查。不保留"先 raise 后看码"的不可达分支。

**重建至多一次守卫如何落在共享请求层：**
- 守卫即 `_post_jsonrpc` 的 `_allow_session_retry: bool = True` keyword-only 入参。命中失效且 `_allow_session_retry` 为 True：`_expire_session` → `_open_session`（写新 id + initialized）→ **递归调用自身**重发原 method/params（分配新递增 request id），但递归时传 `_allow_session_retry=False`。重试仍失效不再进重建分支，落到 `raise_for_status()` 上抛。因 `tools/call`（`_call_http_tool`）与 `tools/list`（`_register_http_server`）都经 `_post_jsonrpc`，调用期/注册期对称生效，与路径无关。

**close DELETE + 生命周期收口如何实现：**
- `close()` 在原 stdio 清理之前先 `await _close_http_sessions()`：筛 `_server_registry` 中活跃 HTTP 会话，新建一个 `httpx.AsyncClient`，对每个 server `client.delete(f"{url}/", headers=_base_headers(server))`（带 Mcp-Session-Id），`try/except Exception → logger.debug`（best-effort，不抛、不阻断），`finally` 调 `_expire_session` 置空 session_id。无活跃会话直接 return（不建 client、不发请求）；stdio server 因 `transport!="http"` 被跳过。
- 生命周期收口：open/expire 为显式函数，reuse 沿用 `_base_headers` 回携，close 经 `_close_http_sessions`；状态仍持于 `McpServerConfig.session_id`，未引入新数据类/模块级会话表/锁。重建路径复用 `_open_session` 而非复制握手。

**自解冲突（C·全自主，最小改动）：**
1. **4xx 兜底判据的具体标识**（Open Question 1，目标 server 未在手边实测）：实现为响应头 `Mcp-Session-Invalid` 或响应体（小写）含 `session` 且含 `expired`/`invalid`/`not found` 之一。保守口径，避免把普通 400 误判为会话失效;404 仍是主路径，绝大多数标准 server 走 404，兜底仅为非 404 server 留口。
2. **重试用递归而非循环**：`_post_jsonrpc` 递归一层传 `_allow_session_retry=False`，比显式 while/计数器更短且天然"至多一次"，无新增可变状态。
3. **DELETE 失败后仍 `_expire_session`**：放在 `finally`，即便 DELETE 失败（服务端不可达）也清本地 session_id——关停后实例不应再带陈旧 id；与"best-effort 释放"语义一致。
4. **不引入 per-server 锁**（design 明确接受无锁、最坏多一次重建有界）：未加锁。

**影响：**
- pytest：base **932 → after 946 passed**（净 +14，全在 `tests/test_mcp_client.py`）。MCP1 既有用例（注册/回携/SSE/降级/请求 id）全绿，会话有效路径不破。
- ruff（仅本 change 改/建文件）：format 仅 `mcp_client.py` 折叠了一处列表推导（本 change 新增的 `_close_http_sessions`，非无关行）；check `All checks passed`。
- mypy：base **76 → after 76**，无新增。`mcp_client.py` 仅余 2 个既有 `no-any-return`（`_call_stdio_tool`/`_call_http_tool` 返回，HEAD 即存在），非本 change 引入。

**需 zy 核实：**
1. **4xx 会话失效兜底标识**（自解冲突 1）：`Mcp-Session-Invalid` 头 + 响应体关键词为推测口径，未对照真实自托管 MCP server 实测。若目标 server 用特定 JSON-RPC error code（如 -32001）表达会话失效，需改 `_has_session_invalid_marker` 改读 body 的 JSON-RPC error。404 主路径不受影响。
2. **DELETE 会话端点路径**（Open Question 2）：按规范取同 POST 端点 `{url}/`。若目标 server 用独立会话端点需调整。
3. **并发无锁**（Open Question 3）：沿用 design 决定不加锁，最坏多一次 initialize。高并发实测出现交错问题再加 per-server 锁。

## 12. mcp-oauth2 (MCP5)

**改/建文件：**
- 修改 `src/fleetent/mcp_client.py`：`McpServerConfig` 新增 OAuth2 字段（`token_url` / `client_id` / `client_secret_env` / `scope`）与按 server 实例持有的 OAuth2 运行态字段（`_token_store` / `_refresh_lock` / `_auth_unavailable`，均 `repr=False, compare=False`）；新增 `_now`（可注入时钟）、`OAuthToken` 数据类、`OAuthAuthUnavailableError`、`_InMemoryTokenStore`（按 server 隔离）、`_default_token_store`、`_clear_oauth_auth_state`、`_token_is_valid`、`_is_transient_token_error`、`_is_auth_error_response`、`_fetch_client_credentials_token`、`_resolve_oauth_token`、`_bearer_for`；`_base_headers` 增 keyword-only `bearer` 入参（保持同步、纯拼装）；`_open_session` / `_post_jsonrpc` / `_post_notification` / `_close_http_sessions` 的请求构造前先 `await _bearer_for(server)` 再传入 `_base_headers(server, bearer=...)`；`_call_http_tool` 增 D8 短路；`_register_server` 对 oauth2 调 `_clear_oauth_auth_state`（恢复触发）。
- 修改 `config/mcp.yaml.example`：新增 `internal-gateway` 的 oauth2 示例，注释强调 token_url 为客户内网自托管授权服务器、secret 经环境变量、无云依赖。
- 修改 `tests/test_mcp_client.py`：新增 20 例（config 字段 2 + token 存储 3 + 取 token/Bearer 3 + 自动刷新/边界/并发锁 6 + 认证失败 sticky/瞬时/恢复/D8 短路 5 + 配置示例 1）。

**前置核实结论（tasks 1.x）：**
- 1.1 `_base_headers` 现状为**同步** `def`，`api_key` 分支仅 `os.environ.get`；调用点为 `_open_session`（initialize）、`_post_jsonrpc`、`_post_notification`、`_close_http_sessions`（DELETE）。采用 D6a 方案 a：调用点先 `await _bearer_for(server)` 再传 `_base_headers(server, bearer=...)`，`_base_headers` 保持同步。
- 1.2 OAuth2 字段命名与 `auth_type` / `api_key_env` 同风格，`str` 默认 `""`；secret 经 `client_secret_env` 环境变量引用不明文。
- 1.3 错误判据：401 一律真认证错误；400/403 仅当响应体 `error ∈ {invalid_client, invalid_grant, unauthorized_client}` 才判真认证错误；5xx / 网络 / 超时为瞬时。
- 1.4 token 存储默认内存，按 server 实例隔离（`_InMemoryTokenStore` 经 `_token_store` 字段持有）；未启用 sqlite 持久化（client_credentials 重取廉价，design D3 允许持久化为可选，本 change 取默认内存）。

**D6a token resolve 落点（方案 a）+ `_base_headers` 是否同步：**
- token resolve 在**每个调 `_base_headers` 的 async 请求构造点之前** `await _bearer_for(server)`（`_open_session` / `_post_jsonrpc` / `_post_notification` / `_close_http_sessions`）。`_bearer_for` 对 `auth_type=="oauth2"` 返回 resolve 后的 access token，否则返回 `None`。`_base_headers` **保持同步**，新增 keyword-only `bearer`：`bearer` 非空时拼 `Authorization: Bearer <bearer>`，否则回落到既有 api_key 分支。绝不在 `_base_headers` 内 `await` / `asyncio.run` / 阻塞拿 token。none/api_key/session_id 分支可观察行为不变（oauth2 时 bearer 由外部传入，api_key 分支不被触发）。

**token 存储按 server 隔离、不进全局如何实现：**
- `_InMemoryTokenStore` 实例经 `McpServerConfig._token_store = field(default_factory=_default_token_store, repr=False, compare=False)` 随每个 server 实例创建并持有，无任何模块级 token dict/缓存。每个 server 默认各自一份 store（测试 `s1._token_store is not s2._token_store` 验证）；store 内部按 `server_id` 键仅为单 store 内记账。可注入：测试可直接构造 `_InMemoryTokenStore` 或替换实例字段;`clear` 支持重置。

**D9 per-server 锁 + double-check：**
- `McpServerConfig._refresh_lock = field(default_factory=asyncio.Lock, ...)` 随 server 实例持有（不进模块级全局，`s1._refresh_lock is not s2._refresh_lock`）。`_resolve_oauth_token`：先无锁快速读缓存，命中有效直接返回；否则 `async with server._refresh_lock` 进临界区**再次** `get` + `_token_is_valid` double-check（等锁的并发请求拿锁后命中已刷新 token、直接复用），仅 double-check 仍无效时才 `_fetch_client_credentials_token`。5 路并发 + 慢 token 端点测得端点命中 == 1。不同 server 各自锁，互不阻塞。

**D5 瞬时 vs 真认证错误区分 + 恢复触发：**
- `_is_auth_error_response`：401 → 真认证错误；400/403 且响应体 `error ∈ {invalid_client, invalid_grant, unauthorized_client}` → 真认证错误。命中即 `_fetch_client_credentials_token` 抛 `OAuthAuthUnavailableError`，`_resolve_oauth_token` 捕获后置 `server._auth_unavailable = True`（sticky）并重抛，后续 resolve 直接短路抛错、不再打端点（测得端点命中 == 1）。
- 瞬时错误：5xx 经 `resp.raise_for_status()` 抛 `httpx.HTTPStatusError`、网络/超时为 `httpx.TransportError`/`TimeoutException`，**不**被 `OAuthAuthUnavailableError` 捕获分支命中，故 `_auth_unavailable` 保持 False、原样上抛（可重试）；下次 resolve 可正常再取并成功。`_is_transient_token_error` 提供瞬时判定辅助（5xx / TransportError / TimeoutException）。
- 恢复触发：`_register_server` 对 oauth2 调 `_clear_oauth_auth_state`（清 sticky 标志 + 清缓存 token），即配置重载 / 重新注册清除 sticky；不做定时退避。

**D8 认证不可用期间工具调用（自包含、不依赖 MCP3）：**
- `_call_http_tool` 入口：`server.auth_type == "oauth2" and server._auth_unavailable` 时直接 `return` 一段「authentication unavailable: re-authorize / check OAuth2 credentials」文本结果——不取 token、不发 HTTP、不抛（测得 token 端点与 MCP 端点均未命中）。独立 auth 标志，正交于 MCP3 连接健康态，无 MCP3 依赖。其他 server 不受影响。

**自解冲突（C·全自主，最小改动）：**
1. **400/403 + error body 才判真认证错误**（Open Question 1，无真实 Keycloak 实测）：401 无条件真错；400/403 须响应体 `error` 命中白名单，避免把普通 400/403 误判为凭据错误而长期 sticky。保守口径。
2. **无 expires_in 默认 TTL = 300s、安全余量 30s**（Open Question 2）：常量 `_OAUTH_DEFAULT_TTL` / `_OAUTH_EXPIRY_SAFETY_MARGIN`，过期时刻 = `_now() + ttl - margin`。保守短 TTL，确保下次调用前重取。
3. **不做 MCP server 401 兜底刷新**（Open Question 3）：本 change 主路径按过期时刻预刷新；MCP server 返回 401 触发刷新重试为可选增强，未实现（401 经既有 `raise_for_status` 上抛，不被会话失效逻辑误判，MCP2 `_is_session_expired` 已对 401/403 返回 False）。
4. **refresh_token 为防御性附注**：`OAuthToken` 存了 `refresh_token`，但刷新主路径恒为重跑 client_credentials；缺失（RFC 6749 §4.4 正常情况）不判失败。未实现 refresh_token grant 分支（目标服务器为标准 client_credentials，无 refresh_token），避免为未触发路径写死逻辑。
5. **time 源经模块级 `_now()` 函数**：非模块级可变状态（函数引用，测试 monkeypatch 替换），满足 D4「当前时间源可注入」且不硬编码 `time.time()`。

**影响：**
- pytest：base **946 → after 966 passed**（净 +20，全在 `tests/test_mcp_client.py`）。MCP1/MCP2 既有用例全绿；none/api_key 路径行为不变（新增用例验证 none/api_key 不触发 token 端点）。
- ruff（仅本 change 改/建文件 `mcp_client.py` / `test_mcp_client.py` / `mcp.yaml.example`）：format 已应用、check `All checks passed`。
- mypy：base **76 → after 76**，无新增错误模式。`mcp_client.py` 仅余 2 个既有 `no-any-return`（`_call_stdio_tool` / `_call_http_tool` 返回，HEAD 即存在，行号因新增代码从 392/412 位移至 617/645）。

**需 zy 核实：**
1. **真认证错误判据**（自解冲突 1）：401 + 400/403 error 白名单 `{invalid_client, invalid_grant, unauthorized_client}` 为推测口径，未对照真实自托管 Keycloak 实测。若目标授权服务器以其他形态（如特定 HTTP 码 / error 值）表达凭据错误，需调 `_is_auth_error_response`。
2. **默认 TTL / 安全余量取值**（自解冲突 2）：300s / 30s 为保守默认（常量可改）。若目标 server 颁发的 token 显著长寿且总返回 expires_in，则默认 TTL 几无触发。
3. **MCP server 401 兜底刷新**（自解冲突 3）：未实现，主路径按过期时刻预刷新。若目标 server 存在「客户端时钟与服务端不一致致 token 提前被拒」场景，需补一次 401 触发刷新重试。
4. **refresh_token grant 分支**（自解冲突 4）：未实现（标准 client_credentials 无 refresh_token）。若某非标准授权服务器返回 refresh_token 且期望优先用之，需补 refresh_token grant。
5. **token 持久化**：本 change 取默认内存（重启重取），未启用 sqlite 持久化。若需跨重启复用 token，按 design D3 补 stdlib sqlite3 + 可 monkeypatch `DB_PATH` 后端。

## 13. mcp-health-reconnect (MCP3)

**改/建文件：**
- 修改 `src/fleetent/mcp_client.py`：新增 `HealthState` StrEnum（`healthy`/`degraded`/`unavailable`）；模块级**只读**调参常量 `_PROBE_INTERVAL`/`_BACKOFF_BASE`/`_BACKOFF_CAP`/`_RECONNECT_MAX_ATTEMPTS`（默认值内置，非可变状态）；`_health_monitor_task`（单后台 task 句柄）；`McpServerConfig` 新增按 server 持有的健康运行态 `_health`/`_reconnect_attempts`/`_reconnect_lock`（均 `repr=False, compare=False`）；新增 `get_health`/`set_health`/`reset_health`、`_is_disconnect_error`、`_disconnect_classification`、`_unavailable_result`、`_handle_disconnect`、`_backoff_delay`、`_attempt_reconnect`、`_reconnect_with_backoff`、`_schedule_reconnect`、`reconnect`（手动入口）、`_probe_once`、`_health_monitor_loop`、`start_health_monitor`、`stop_health_monitor`；`_call_http_tool` / `_call_stdio_tool` 增 D5 降级短路 + D1 断连捕获；`close()` 首行调 `stop_health_monitor()`。
- 修改 `src/fleetent/server.py`：lifespan 在 `register_all` 之后调 `mcp_client.start_health_monitor()`（裸 asyncio task，不挂 cron）；关停经既有 `mcp_client.close()` 取消（close 内 `stop_health_monitor`）。
- 修改 `tests/test_mcp_client.py`：新增 26 例（健康三态隔离/默认/重置/不进全局 4 + D1 断连识别/拒 HTTPStatusError/直接读表/classify 守卫 4 + 断连转 degraded http+stdio 2 + D5 降级短路 http/unavailable/不影响他服务 3 + D7 404 不降级 1 + D4 退避序列 2 + 重连成功恢复/失败累计/达阈值 unavailable/手动重连 4 + D3 探活 http 不可达/http 健康/stdio 死/跳过 unavailable 4 + D6 monitor 启停取消/close 取消 2）。

**前置核实结论（tasks 1.x）：**
- 1.1 `CLASSIFICATION_TABLE[ErrorCategory.mcp_disconnect].should_retry == True`（error_classifier.py 行 91，未改）。`classify()`/`_categorize()` 仅识别 `APIStatusError`，断连异常（httpx ConnectError 等、stdio EOF）一律落 `unknown`，**绝不**产出 `mcp_disconnect`。故 D1 定为：mcp_client 侧自判 `mcp_disconnect`、直接读表，**不经 `classify()`**。
- 1.2 断连异常形态：HTTP 走 httpx `ConnectError`/`ConnectTimeout`/`ReadError`（及更广的 `TransportError`/`TimeoutException`）；stdio 子进程死/管道断表现为 `ConnectionError`/`BrokenPipeError`/`EOFError`/`OSError`（`session.call_tool` 抛出，或 `_active_sessions` 无 session）。
- 1.3/1.4 `register_all`（行 224）/ `close()`（行 187）/ server.py lifespan（行 67，注册点 87、关停点 110）为启停接入点；lifespan 既有裸 `asyncio.create_task`（Slack/Telegram adapter）先例，探活用同款裸 task 即可，无需新调度依赖、**不挂 cron_scheduler**。
- 1.5 与 MCP2 边界：`_is_session_expired`（行 438）对 404 返 True → `_post_jsonrpc`（行 525）同请求重建会话；404 是 HTTP 响应（`HTTPStatusError`/正常 4xx 响应对象），**不是连接异常**，故 `_is_disconnect_error` 对 `HTTPStatusError` 显式返 False，404 永不进 MCP3 降级路径。

**D1 断连异常如何映射 mcp_disconnect（直接读表、不经 classify）+ 守卫：**
- `_is_disconnect_error(exc)`：先 `isinstance(exc, httpx.HTTPStatusError) → return False`（带响应的状态错误是会话/认证层，非连接层，D7 关键），再判 httpx `ConnectError`/`ConnectTimeout`/`ReadError`/`TransportError`/`TimeoutException` 及 stdio 的 `ConnectionError`/`BrokenPipeError`/`EOFError`/`OSError` → True。
- `_disconnect_classification()`：`from fleetent.error_classifier import CLASSIFICATION_TABLE, ErrorCategory`（函数内 import），`return CLASSIFICATION_TABLE[ErrorCategory.mcp_disconnect]`——**直接索引表**取 `ErrorClassification`，拿到 `should_retry=True`。**全程不调 `classify()`**（喂断连异常给它只得 `unknown`，是死分支）。返回类型标注 `ErrorClassification`（`TYPE_CHECKING` import + `from __future__ import annotations` 前向引用，避免运行期循环 import）。
- `_handle_disconnect(server)`：读 `_disconnect_classification().should_retry`，为真且当前 `healthy` 时转 `degraded` 并 `_schedule_reconnect`，返回 D5 不可用文本。工具调用路径 `_call_http_tool`/`_call_stdio_tool` 在 `try` 内捕获，`_is_disconnect_error` 命中才走 `_handle_disconnect`，否则原样 `raise`（不吞非断连异常）。
- 守卫用例 `test_guard_classify_of_disconnect_is_unknown_not_mcp_disconnect`：对 `ConnectError`/`ConnectTimeout`/`ReadError` 断言 `classify(exc).category is ErrorCategory.unknown` 且 `is not ErrorCategory.mcp_disconnect`，证实 MCP3 不依赖也不能依赖 `classify()` 识别断连。另 `test_disconnect_maps_to_mcp_disconnect_reading_table_directly` 断言 mcp_client 侧读表得 `mcp_disconnect` + `should_retry True`。AR5 表标志位**未改**。

**健康三态按 server 持有、不进全局如何实现：**
- 状态字段 `_health`（默认 `HealthState.healthy`）/ `_reconnect_attempts`（默认 0）/ `_reconnect_lock`（`default_factory=asyncio.Lock`）经 `McpServerConfig` 的 `field(..., repr=False, compare=False)` 随每个 server 实例创建并持有——**无任何模块级 `dict[str, HealthState]` 全局**。`get_health`/`set_health`/`reset_health` 直接读写 server 实例字段。守卫用例 `test_health_state_not_module_level_global` 断言 `mcp_client` 模块上 `not hasattr "_health_states"` 且 `not hasattr "_HEALTH"`。不同 server 状态互不影响（`test_health_state_isolated_per_server`）。`_PROBE_INTERVAL` 等是只读默认常量（非每 server 可变态），测试经 `monkeypatch.setattr` 注入短值；退避基数/上限经 `_backoff_delay(..., base=, cap=)` 关键字参数直接注入，不真实长 sleep。

**探活/重连后台任务接 lifespan（裸 asyncio、不挂 cron）+ 关停取消：**
- `start_health_monitor(*, interval=_PROBE_INTERVAL)`：幂等（已有未完成 task 则复用），`asyncio.create_task(_health_monitor_loop(interval))` 存入模块级 `_health_monitor_task` 句柄并返回。`_health_monitor_loop` 为 `while True: await asyncio.sleep(interval); for server in list(_server_registry.values()): await _probe_once(server)`——纯裸 asyncio 常驻循环，**MUST NOT 经 cron_scheduler/APScheduler**（与张亮 scheduling 域已暂缓的用户级定时任务解耦，MCP3 自包含于 MCP 域）。
- server.py lifespan 在 `register_all` 之后调 `start_health_monitor()`；关停经既有 `mcp_client.close()`——`close()` 首行 `await stop_health_monitor()`：`cancel()` + `with suppress(asyncio.CancelledError): await task` + 句柄置 None，不残留 task（`test_close_cancels_health_monitor` / `test_start_health_monitor_creates_task_and_stop_cancels_it` 验证 `task.done()` 且句柄 None）。
- CLI 一次性 `run()` **不**调 `start_health_monitor`（仅服务端常驻，与 skill scan 同理）；CLI 下断连靠 D1 调用时映射发现（design D6 CLI 降级澄清），与服务端最终行为一致，差别仅「何时发现断连」。

**D3 探活 / D4 退避重连 / D5 降级 / 并发去重：**
- `_probe_once(server)`：非 `healthy` 直接 return（degraded 已在重连、unavailable 需手动）；stdio 检查 `_active_sessions.get(id) is None` → degraded + `_schedule_reconnect`；http 用 `_post_jsonrpc(client, server, "tools/list", {})` 轻量探活，异常经 `_is_disconnect_error` 判定，断连才 degraded + 重连（非断连仅 debug log，不误降级）。探活跳过 `unavailable`（`test_probe_skips_unavailable_server` 验证不发请求、不调度）。
- `_backoff_delay(attempt, base, cap) = min(base * 2**attempt, cap)`：序列 1→2→4→8→16→32→60→60（封顶保持，`test_backoff_sequence_doubles_and_caps`）；可注入短值（0.01/0.05）。
- `_attempt_reconnect(server)`：`_reconnect_lock.locked()` 时直接 return（**幂等/去重，同一服务同一时刻至多一个在途重连**，仿 session_mgr per-session Lock）；持锁内 `await _register_server(server)`，成功 `reset_health`（回 healthy + 计数清零），失败 `_reconnect_attempts += 1`，达 `_RECONNECT_MAX_ATTEMPTS` 转 `unavailable` 停自动重连。`_reconnect_with_backoff` 为 `while degraded: sleep(_backoff_delay(attempts)); _attempt_reconnect`。`_schedule_reconnect` = 裸 `create_task(_reconnect_with_backoff)`。
- `reconnect(server_id)`：手动入口，清 `_reconnect_attempts`、置 degraded、`_attempt_reconnect` 一次——使 `unavailable` 服务重新尝试并可恢复 healthy（`test_manual_reconnect_recovers_unavailable_server`）。
- D5 降级反馈：`_call_http_tool` / `_call_stdio_tool` 入口处 `server._health is not HealthState.healthy` 时直接 `return _unavailable_result(server_id)`（英文「temporarily unavailable」字符串，与 `_call_*_tool` 返回 str 类型一致），**不进真实网络/子进程**、不抛、不卡（`test_degraded_tool_call_returns_unavailable_without_network` 断言 route 未命中）。其他健康服务不受影响（`test_degraded_does_not_affect_other_healthy_server`）。

**D7 404 会话过期 vs 连接级断连边界如何区分：**
- 顺序：工具调用失败先按 MCP2 在 `_post_jsonrpc` 内判 `_is_session_expired`（404 / 带 session-invalid marker 的 4xx）→ 同请求 `_open_session` 重建一次重试（不归 mcp_disconnect、不降级）；只有抛出的是**连接级异常**（`_is_disconnect_error` True）才进 MCP3 `_handle_disconnect` 降级/重连。
- 关键实现点：`_is_disconnect_error` 对 `httpx.HTTPStatusError` 显式 return False——404 既走 MCP2 重建路径，即便重建后再 404 经 `raise_for_status` 抛 `HTTPStatusError` 也**不**被判为断连，不进 MCP3 降级。`test_404_session_expiry_does_not_degrade` 断言 404 重建成功后 server 仍 `healthy`。401/403 同理（`HTTPStatusError`，非连接异常），不降级。

**自解冲突（C·全自主，最小改动）：**
1. **断连异常类型集合**（design 列举 httpx ConnectError/ConnectTimeout/ReadError「等」+ stdio「会话失活/EOF」，未穷举）：`_is_disconnect_error` 取「httpx `TransportError`/`TimeoutException` 全族（含三个具体子类）+ stdio `ConnectionError`/`BrokenPipeError`/`EOFError`/`OSError`」，且**先**排除 `HTTPStatusError`（D7 必需）。从宽覆盖连接层、从严排除响应层，避免漏判断连或误判 404。
2. **降级文本语言**：用英文「MCP server '<id>' is temporarily unavailable (...)」，与既有 D8 oauth2 不可用文本（同为英文）风格一致；测试断言兼容中英（`"unavailable" in lower() or "不可用"`）。
3. **探活间隔 30s / 退避基数 1s 上限 60s / 阈值 5**：design 仅给「默认值内置、可注入」与 1→2→4→60s 序列；阈值 5、间隔 30s 为内置默认（`_RECONNECT_MAX_ATTEMPTS`/`_PROBE_INTERVAL` 常量可改）。属 design Open Question「阈值几次、间隔是否同频」的本次取值，零配置可用。
4. **并发去重用 `_reconnect_lock.locked()` 早返回**（design 接受「必要时按 server 加重连锁」）：本次即加 per-server `asyncio.Lock`，locked 时直接 return 实现「至多一个在途重连」，不额外排队。
5. **探活非断连异常仅 debug log 不降级**：`_probe_once` http 分支若异常非断连（如偶发 4xx/解析错误），不误转 degraded，仅 debug log——避免把非连接问题当断连触发无谓重连。

**影响：**
- pytest：base **966 → after 992 passed**（净 +26，全在 `tests/test_mcp_client.py`）。MCP1/MCP2/MCP5 既有用例全绿；AR5 表标志位未改；含「`classify(断连异常)` 仍为 `unknown`」守卫。
- ruff（仅本 change 改/建文件 `mcp_client.py` / `test_mcp_client.py` / `server.py`）：format 已应用、check `All checks passed`（`mcp_client.py` / `test_mcp_client.py`）；`server.py` 仅本 change 3 行新增、无新增 ruff 错误（既有 4 项 F401/I001 为 HEAD 遗留，已 `git stash` 对照确认）。
- mypy：base **76 → after 76**，无新增错误模式。`mcp_client.py` 仅余 2 个既有 `no-any-return`（`_call_stdio_tool` / `_call_http_tool` 返回，HEAD 即存在，行号因新增代码位移至 861/898）。

**需 zy 核实：**
1. **探活间隔 / 退避阈值默认值**（自解冲突 3，design Open Question）：间隔 30s、阈值 5 次、退避 1→60s 为内置默认。若部署希望可调，按 design 在 `config/mcp.yaml` per-server/全局加可选字段（本次未加，可注入参数 + 默认已零配置可用）。
2. **断连异常类型集合是否完备**（自解冲突 1）：stdio 子进程死亡的真实异常形态（取决于 `mcp` SDK 的 `ClientSession.call_tool` 在管道断时抛什么）未对真实子进程实测（测试用 mock）。若 SDK 以其他异常类型（非 `ConnectionError`/`OSError` 族）表达会话失活，需扩 `_is_disconnect_error`。
3. **per-server 重连锁 vs 全局并发**（design Open Question）：本次按「锁 locked 即早返回、至多一个在途」实现；若高并发实测出现重复重连或竞态，再加排队/全局协调。
4. **降级文本语言**（自解冲突 2）：当前英文。若产品要求面向终端用户的中文不可用提示，调 `_unavailable_result`。

## 14. sandbox-enablement-control (SB3)：代码执行能力三态启用控制

> 沙箱治理轨三项共享资源 owner：`agent_store.features` JSON 列 / `config/settings.yaml` 的 `sandbox:` 段骨架 / run_code 执行期上下文通道。SB2/SB4/SB5 复用。

**前置核实（tasks 1.x 结论）：**
- 1.1：`agent_loop.run()`（实际 `schemas`+`allowed_tools` 过滤在 ~480-481 行）与 `run_stream()`（~780-783 行 `stream_schemas`）确已按 `allowed_tools` 经 `check_tool_access` 做 per-agent schema 过滤。两个 gate（全局 off / agent 级 `code_execution=false`）在**同处**追加 `is_code_execution_enabled` 过滤即可，不条件化注册、不在调用入口拒绝。`run_code` 仍按 import 副作用全局注册（注册路径未动）。
- 1.2/1.3：`Agent` 原仅 `id/name/system_prompt/allowed_tools`；`_init_db` 用 `CREATE TABLE IF NOT EXISTS`。`tool_registry.dispatch` 与 `run_code` 原不透传 agent/session 上下文，确需补通道。`_safe_dispatch` 调 `dispatch` 未传 `allowed_tools` → `dispatch` 内 `check_tool_access` 在主循环是死代码（design Risk，**本 change 不修**，仅标注）。
- 1.4：仓库无集中的 `config/settings.yaml` 段加载器（`admin.py` 仅引用路径常量）。本 change 作为 `sandbox:` 段首个落地者，在 `sandbox_enablement.py` 内建轻量加载器（仿 `model_router` 的 `ROUTES_PATH` 注入式常量惯例），并在 `config/settings.yaml.example` 写入段骨架。

**⚠️ 显著记录：agent_store.features 列改用 alembic 迁移（002），非运行时 ALTER（zy 指示，覆盖 change 的 D3 / tasks 4.3-4.4）：**
- 落地方式：`_init_db` 的 `CREATE TABLE IF NOT EXISTS agents (...)` **直接含 `features TEXT`**（新库 / 测试 tmp_path 走此条，天然有列）；**不**在 `_init_db` 加 `PRAGMA table_info`+运行时 `ALTER`。
- 现有生产库由**新增 alembic 迁移 `migrations/versions/002_add_agent_features.py`** 升级：`revision="002"`、`down_revision="001"`、`upgrade()` = `op.add_column("agents", sa.Column("features", sa.Text(), nullable=True))`、`downgrade()` = `op.drop_column("agents", "features")`，仿 001 手写迁移风格（`target_metadata=None`、`sqlalchemy.url=sqlite:///data/users.db`）。
- 读取统一 `json.loads(row[4] or "{}")` 兜底（列存在但旧行 NULL）。
- 理由：避免「运行时 ALTER + 冗余迁移两条腿」（agent-skill-binding 的教训）。
- 测试：`test_alembic_002_upgrade_adds_features_to_legacy_table` 用 `MigrationContext`+`Operations` 绑定真实 sqlite 连接，对「无 features 列的旧库」实际驱动 002 的 `upgrade()`/`downgrade()`（验证 add_column / drop_column 真实生效，现代 SQLite 3.35+ 支持 DROP COLUMN）；另 `test_init_db_create_table_includes_features_column` 验证新库 CREATE TABLE 含列、`test_agent_features_null_row_falls_back_to_empty` 验证 NULL 兜底。
- **agent_store 撞车风险**：张亮正活跃在 agent_store/agents 表邻域。本 change **只**加 `features` 列、`Agent.features` 字段（`dataclasses.field(default_factory=dict)`）、`_SELECT_COLS`/`_row_to_agent`/`create_agent` 读写 SQL 的最小改动，**不动** agents 表其它列 / 其它 store 逻辑。

**D1 三态判定纯函数 + 单一生效点（schema 过滤）：**
- 新建 `src/fleetent/sandbox_enablement.py`：`Mode(StrEnum)` = `OFF/SELECTIVE/ALL`；`resolve_effective_mode(configured, docker_available)`（docker 不可用一律 OFF）；`is_code_execution_enabled(mode, code_execution)`（OFF→False；SELECTIVE→`is True`；ALL→`is not False`，即 None/True 开、显式 False 关）。纯函数，无副作用。
- 生效点：`agent_loop._filter_code_execution(schemas, sandbox_mode, agent_features)` 在 `run()`/`run_stream()` 现有 `allowed_tools` 过滤**同处**追加——判定 False 则把 `run_code` 从该 agent 的 schemas 剔除。`run()`/`run_stream()` 新增入参 `sandbox_mode: Mode | None`、`agent_features`、`session_id`。**`sandbox_mode is None` → 不过滤**（向后兼容：未传 mode 的既有调用 byte-identical，run_code 仍可见）。不条件化注册、不返回拒绝文本。

**D2 Docker 探测 + 降级 + /health 暴露：**
- `SandboxClient.docker_available()`：`docker version`（仅看 returncode），`FileNotFoundError`/`OSError`/非零 → log warning + 返回 False，不抛。
- 服务端 `lifespan` 启动期探测一次 → `resolve_effective_mode` → 存 `app.state.sandbox_mode` / `app.state.sandbox_docker_available`；可用 `logger.info`、降级 `logger.warning(... docker unavailable; configured=...)`，平台正常启动。
- `GET /health` 暴露 `{"sandbox": {"mode": <effective>, "docker_available": bool, "note"?: "off (docker unavailable)"}}`。
- 非服务端调用方（IM gateway / CLI）无 app.state：`sandbox_enablement.get_effective_mode()` 提供进程级单值缓存（`_effective_mode_cache`，可 monkeypatch 到 None），首次探测 Docker 一次后缓存，避免 per-message 探测（D2 启动期一次性意图）。这是本模块唯一的可变模块状态，仿 `model_router` 文件缓存。

**D5 run_code 上下文通道（本 change owner，为执行期 SB2/SB5 而建，非 gate）：**
- `tool_registry.ToolContext` dataclass（`agent_name` / `features` / `session_id`），仿 cancel_token 的 out-of-band 注入：新增 `_TOOL_CONTEXT_PARAM="tool_context"`，`dispatch` 仅对声明 `tool_context` 形参的工具注入、`_build_schema` 经 `_OUT_OF_BAND_PARAMS` 排除（不进 LLM schema）。未声明 `tool_context` 的既有工具调用 byte-identical（守卫测试 `test_dispatch_does_not_inject_context_into_non_opt_in_tool`）。
- `agent_loop` 在 `run()`/`run_stream()` 构造 `ToolContext` 并经 `_safe_dispatch`→`dispatch` 透传；`run_code` 据 `tool_context.session_id` 命名 workspace（供 SB2 定位/复用），**缺省上下文安全降级**到 `"run-code"` 默认 key，不抛（`test_run_code_degrades_safely_without_tool_context`）。
- 接线：server `/chat`、IM normalizer、CLI `run_sync` 均传 `sandbox_mode`/`agent_features`(+`session_id`)。

**自解冲突（C·全自主，最小改动）：**
1. **YAML `off` 解析为布尔 False**：`load_sandbox_mode` 显式把 `False`→`Mode.OFF`、`True`→`Mode.ALL`（设置文件示例注释提示给 `off` 加引号）；非法值 log warning 后回退 `Mode.ALL`。
2. **`sandbox_mode is None` 不过滤**：design 未明示「未传 mode」语义；为不回归既有 992 用例的 run_code 可见性，取「None=调用方未启用 SB3 gate，schemas 透传」。真实调用方（server/CLI/IM）都会传 effective mode，故生产路径恒经 gate。
3. **降级态非服务端缓存** `get_effective_mode()`：design 仅说服务端 lifespan 一次性探测；IM/CLI 无 lifespan，按 D2「启动期一次」精神用进程级缓存（可注入清空），而非每消息探测（被否的 alternative）。
4. **alembic downgrade 用 `op.drop_column`**：现代 SQLite（3.35+）原生支持 `ALTER TABLE DROP COLUMN`，测试实测 upgrade/downgrade 均通过；若目标部署 SQLite < 3.35，需改 batch_alter_table（标注待复核）。
5. **死代码 `_safe_dispatch` 未传 `allowed_tools`**：design Risk 已述，本 change 代码执行访问控制同样仅靠 schema 过滤这一层（与现状一致），不修死代码、不扩范围，仅标注。

**影响：**
- 改/建文件：新建 `src/fleetent/sandbox_enablement.py`、`migrations/versions/002_add_agent_features.py`、`tests/test_sandbox_enablement.py`、`tests/test_normalizer_sandbox.py`；改 `sandbox_client.py`（+`docker_available`）、`agent_store.py`（+features 列/字段/读写）、`tool_registry.py`（+`ToolContext`/`tool_context` 注入/schema 排除）、`tools.py`（`run_code` 取 ctx.session_id）、`agent_loop.py`（filter 生效点 + ctx 通道 + run()/run_stream()/run_sync 入参）、`server.py`（lifespan 探测 + /health + /chat 接线）、`im_gateway/normalizer.py`（接线）、`config/settings.yaml.example`（`sandbox:` 段骨架）。
- pytest：base **992 → after 1035 passed**（净 +43，分布 test_sandbox_enablement +15、test_agent_store +5、test_sandbox_client +3、test_tool_registry +4、test_tools +2、test_agent_loop +9、test_server +1、test_server_lifespan +3、test_normalizer_sandbox +1）。无回归。
- ruff：本 change 改/建文件 format+check 全绿（新增的 `test_agent_store` 迁移测试改用 `@contextlib.contextmanager` 避 N801、in-function import 排序修正）；`server.py`/`tools.py` 的既有 HEAD 遗留 ruff 项（I001/F401/N814/SIM117）已 `git stash` 对照确认为既有，且把 format 顺带改的无关行（webhook import 空行、schedule_task 签名换行）**已还原**。
- mypy：base **76 → after 76**，无新增错误模式（新模块 `sandbox_enablement.py` 零 mypy 错误；`sandbox_client.py`/`agent_store.py` 既有的 stdlib-logger kwargs 与 `Settings()` call-arg 项为 HEAD 遗留，仅行号位移）。

**需 zy / 张亮核实：**
1. **【需张亮复核】agent_store.features 用 alembic 002 迁移**（覆盖 D3/tasks 4.3-4.4 的运行时 ALTER）：002 迁移脚本写法、与张亮在 agents 表邻域工作的**撞车风险**、downgrade 的 `op.drop_column` 对目标部署 SQLite 版本（需 ≥3.35）的兼容性。
2. **`sandbox_mode is None → 不过滤` 的兼容语义**（自解冲突 2）：是否认可「未传 mode = 不 gate」而非「默认 all」。生产调用方都传 mode，但若希望防御性默认，可改 None→ALL。
3. **非服务端 `get_effective_mode()` 进程缓存**（自解冲突 3）：IM/CLI 用进程级单值缓存。若部署期望 IM/CLI 也随服务端 app.state 走同一 mode、或运行期 Docker 状态变化需重探，再调整。
4. **死代码 `_safe_dispatch` 不传 allowed_tools**（design Risk）：本 change 未修；若要补「调用层防御纵深」需另开 change。

## 15. sandbox-resource-limits (SB4)：沙箱资源限制可配置（按次 SandboxResources）

> 共享资源引用：`config/settings.yaml` 的 `sandbox:` 段 owner = SB3。本 change 仅向该段**追加** `resources` 子段（`memory`/`cpus`/`network`/`exec_timeout`/`read_only`），与 `sandbox.mode`（SB3）/`scope`/`idle_hours`（SB2）共处同段，不另立 yaml、不改已有段骨架。

**前置核实（tasks 1.x 结论）：**
- 1.1：`create_workspace`（sandbox_client.py，AR19/SB3 后行号位移）硬编码 `--network none --memory 256m --cpus 0.5 --read-only --tmpfs /tmp`。参数化：`--network`（三态）/`--memory`/`--cpus`/`--read-only`（可关）。保留：`--tmpfs /tmp` 始终加。`__init__` 仅收 `image`，无资源参数。AR19 的 `run_code` 编排/`destroy_workspace` 幂等、SB3 的 `docker_available` 探测均**未动**。
- 1.2：yaml 加载惯例同 `model_router.ROUTES_PATH`（模块级 `Path` 常量 + `yaml.safe_load(path.read_text())`，可 monkeypatch）。SB3 的 `sandbox_enablement.SETTINGS_PATH` 已是 `config/settings.yaml` 该模式的落地。本 change 在新模块 `sandbox_config.py` 重复同一注入式常量 `SETTINGS_PATH`（与 SB3 指向同一文件，各自独立读 `sandbox.resources` / `sandbox.mode` 段，无耦合），不集中化加载器。
- 1.3：`create_workspace(session_id)` → `create_workspace(session_id, resources=None)`，可选缺省。`resources=None` 回退 `SandboxResources()`，docker run 命令与现状 byte-equivalent（默认含 `--read-only`、`--network none`、256m、0.5），既有 `test_sandbox_client.py` 3 个 create_workspace 用例不回归。不在 `__init__` 固定资源策略。

**D1 SandboxResources + 加载 + 校验 + clamp（新建 `src/fleetent/sandbox_config.py`）：**
- `NetworkPolicy(StrEnum)`：`NONE="none"`/`PUBLIC_ONLY="public_only"`/`ALLOW_ALL="allow_all"`。
- `SandboxResources`（dataclass，默认即安全默认单一事实源）：`memory:int=256`/`cpus:float=0.5`/`network:NetworkPolicy=NONE`/`exec_timeout:int=30`/`read_only:bool=True`。
- 模块级 `SETTINGS_PATH: Path = Path("config/settings.yaml")`（可 monkeypatch；无全局可变状态）。
- `load_sandbox_resources(path=None) -> SandboxResources`：读 `sandbox.resources` 段，**逐字段**「有则覆盖、缺则默认」；文件/段/子段缺失全默认；corrupt YAML log warning 后全默认（不抛、不静默吞——记录后回退）。
- **非法校验（不静默吞）**：`memory<=0` 或非 int / `cpus<=0` 或非数 / `network` 非枚举值 / `read_only` 非 bool → log warning 后回退该字段默认（采「回退默认」取向而非抛 ValueError，与 SB3 `load_sandbox_mode` 非法值 log+回退的惯例一致，保持启动不崩）。`bool` 显式排除在 int/float 校验外（避免 `True` 被当 1）。
- **exec_timeout clamp [1,600]**：int 值一律 clamp（`0→1`、`1000→600`、范围内不变）——超范围属「范围校验」故 clamp 到边界（非回退默认）；非 int（str/None/bool）才 log 回退默认 30。

**D2 资源值 → docker run 映射（`_resource_flags` staticmethod）：**
- `memory → --memory {n}m`；`cpus → --cpus {n}`（`str(float)`，如 `0.5`/`2.0`）。
- `network`：`none → --network none`（默认推荐）；`allow_all → 不加 --network`（默认 bridge 放行全部出站）；`public_only → ` 网络未预置，按「不可用配置」处理：**log warning 后回退 `--network none`，绝不静默以 bridge 放行**（spec public_only scenario 的安全回退取向）。
- `read_only`：`True → --read-only`；`False → 不加`。`--tmpfs /tmp` **始终保留**（与 read_only 无关的可写临时目录）。
- `exec_timeout` **不进 docker run**（它是单次 docker exec 超时，本 change 仅承载传递供波次 3，不实现 `docker kill`/`--stop-timeout` 等终止逻辑）。

**D3 create_workspace 按次接收 resources（不在 __init__ 固定）：**
- `create_workspace(session_id, resources: SandboxResources | None = None)`：None 回退 `SandboxResources()`。据 resources 经 `_resource_flags` 构造参数，`*flags` splat 进 `docker run` argv（`--name` 之后、image 之前）。
- **不在 __init__ 固定资源策略**：SB2 单 client 需 per-scope 造只读/可写两种容器；同一 client 先后传只读档位、可写档位两次互不串（`test_create_workspace_per_scope_does_not_bleed` 守卫）。
- **缺省等价现状**：不传 resources 时命令含 `--network none`/`--memory 256m`/`--cpus 0.5`/`--read-only`/`--tmpfs /tmp`，既有用例不破（`test_create_workspace_default_command_matches_current_behaviour`）。

**exec_timeout 仅承载（task 5）：** `SandboxResources.exec_timeout` 可被 client 读取，但 `create_workspace` 不含任何 docker kill / 超时终止逻辑（明确划归波次 3）；`test_create_workspace_exec_timeout_not_in_docker_run` 断言其不出现在 argv。

**自解冲突（C·全自主，最小改动）：**
1. **非法配置取「回退默认」而非抛 ValueError**：design Risk 给出「回退默认或抛 ValueError」二选一。取回退默认，与 SB3 `load_sandbox_mode`（非法 mode log+回退 ALL）的既有惯例一致，保证启动不崩；记录 warning 不静默。
2. **exec_timeout 超范围 clamp ≠ 回退默认**：design D1/tasks 3.5 明确 `0→1`、`1000→600`，故超范围 int 走 clamp 到边界；只有「非 int」才回退默认 30。这要求 exec_timeout 不复用通用 `_load_positive_int`（后者对 `0` 会回退默认），单独 `_load_exec_timeout` 处理。
3. **public_only 回退 none 仅 log，不抛**：design 给「log 回退 none（或严格模式抛错）」二选一；本 change 无严格模式开关，取「log warning + 回退 none」，开箱安全且不崩。
4. **新模块独立 SETTINGS_PATH 常量**（不复用 sandbox_enablement 的）：两模块各读自己的段、各自可 monkeypatch，避免跨模块耦合；config/settings.yaml 仍是同一物理文件。
5. **flags 顺序**：默认命令资源标志顺序由 `--network none → --memory → ...` 变为 `--memory → --cpus → --network none → --read-only → --tmpfs`。docker 对标志顺序无语义依赖，既有测试改用 index 查找（非位置切片）故不回归；功能等价。

**影响：**
- 改/建文件：新建 `src/fleetent/sandbox_config.py`、`tests/test_sandbox_config.py`（+13）；改 `src/fleetent/sandbox_client.py`（`create_workspace` 按次 resources + `_resource_flags`）、`tests/test_sandbox_client.py`（+10）、`config/settings.yaml.example`（`sandbox:` 段追加 `resources` 子段）。
- pytest：base **1035 → after 1058 passed**（净 +23：test_sandbox_config +13、test_sandbox_client +10）。无回归。
- ruff：改/建文件 `sandbox_config.py`/`sandbox_client.py`/`test_sandbox_config.py` format+check 全绿；`test_sandbox_client.py` 仅余 2 项 HEAD 既有遗留（`F401 ExecResult` 未用、`SIM117` 嵌套 with，均在我未触碰的既有用例行，`git show HEAD:` 对照确认非本 change 引入），按「只动自己改的」未修。`sandbox_client.py` diff 仅本 change 行，AR19/SB3 既有编排未被 format 顺带改。
- mypy：base **76 → after 76**，无新增错误模式（新模块 `sandbox_config.py` 零 mypy 错误；checked files 53→54）。

**需 zy 核实：**
1. **非法配置回退默认 vs 抛错**（自解冲突 1）：是否认可全部非法值「log+回退默认」（含 memory/cpus/network/read_only），而非严格模式抛 `ValueError` 阻断启动。
2. **public_only 落地**（Open Question）：当前未预置网络时 log+回退 none。若部署需真实公网受限网络，需运维预置 Docker 网络并约定从何处读网络名（本 change 未引入该配置项）。
3. **exec_timeout 承载位置**：本 change 仅把值读入 `SandboxResources` 并随 create_workspace 入参可达，未在 client 持久存储 / 未传 docker exec；波次 3 取该值的具体通路待定。

## 16. sandbox-lifecycle (SB2)：沙箱容器生命周期管理（scope→档位 + 复用/销毁）

**分支** feat/sandbox-lifecycle（基于 feature/zhangyang，已含 SB3+SB4+AR19）。消费 SB3（run_code 上下文通道 + `sandbox:` 段）+ SB4（`SandboxResources`），在其上拥有 scope→档位映射与容器生命周期。

**改/建文件**
- 建 `src/fleetent/sandbox_manager.py`：`Scope`（StrEnum session/agent）、`SandboxManager`（实例持登记表 + scope→档位 + 时钟）。
- 改 `src/fleetent/sandbox_client.py`：新增 `SANDBOX_NAME_PREFIX="sandbox-"` 常量、`find_workspace` / `commit_workspace` / `image_exists`；`create_workspace` 签名收敛为 `(name, resources, image)`。
- 改 `src/fleetent/sandbox_config.py`：新增 `SandboxLifecycle` 数据类 + `load_sandbox_lifecycle`（scope/idle_hours）+ `build_resources_by_scope`（消费 SB4 resources + agent_scope override）；抽出 `_read_sandbox_section` / `_resources_from_section` 复用。
- 改 `src/fleetent/tools.py`：`run_code` 改走 `_MANAGER`（惰性单例，可 monkeypatch）`acquire`，正常路径不销毁。
- 改 `config/settings.yaml.example`：`sandbox:` 段追加 `scope` / `idle_hours` / `agent_scope`。
- 测试：新建 `tests/test_sandbox_manager.py`（17）、扩 `tests/test_sandbox_client.py`、`tests/test_sandbox_config.py`、重写 `tests/test_tools.py` 的 run_code 段。

**create_workspace 签名收敛如何兼容 SB4/AR19/既有用例**
SB4 已让 create 收 `resources`（派生名 `sandbox-{清洗 session_id}`）。本 change 把派生名职责上移到 manager（`_sanitise` 复用 client 的 `_SAFE_NAME`），client 收 `name` 直接用，并增 `image`（取代旧硬编码基础镜像、`base_image` 并入）。既有 `test_sandbox_client.py` 调用点全部改为显式传 `name`（如 `sandbox-session-1`）；以加固档 + 默认镜像（image=None 回退 `python:3.12-slim`）调用时 docker run 命令与现状逐字等价（`test_create_workspace_default_command_matches_current_behaviour` 守护）。AR19 的 `destroy_workspace` 幂等性未触碰。原 `test_create_workspace_sanitizes_session_id`（验证 client 派生名清洗）已无意义，替换为 `test_create_workspace_uses_name_verbatim`——清洗改由 manager 单测覆盖。

**run_code 与 AR19 取消硬中止如何协调（重点）**
- 正常路径（无取消）：`run_code` 经 `manager.acquire(scope, session_id, agent_name)` 取容器，执行后**不再 destroy**（复用是 scope 的核心价值）；销毁交 `release_session` / `sweep_idle`。这与原「finally 必 destroy」语义对立，故原 `test_run_code_destroys_workspace_on_error` 改为 `test_run_code_does_not_destroy_on_exec_error`、normal-path 用例断言 `destroy_workspace.assert_not_called()`。
- 取消路径：仍走 AR19 的 `_exec_or_cancel`——取消时 `docker rm -f` 硬中止销毁容器（AR19 语义不破，`destroy_workspace.assert_any_call(cid)` 守护）。但销毁的是 manager 登记表里的容器，故 `run_code` 在 `_exec_or_cancel` 返回 None 后调 `manager.forget(container_name)` 把该 key 从登记表移除；下次 `acquire` 同 key 时登记表 miss → `find_workspace`（容器已销毁）miss → 重建。`test_run_code_cancel_forgets_registry_then_reacquires` 守护：取消销毁后再 acquire 同 ctx 必触发一次 `create_workspace`。
- 兜底鲁棒：即便不 `forget`，`acquire` 的 `find_workspace` 也会兜底——登记表命中但容器实际已销毁是唯一漏洞，故显式 forget 关闭它。`forget` 是纯内存登记表操作，不发 docker 命令。

**Scope / acquire / release_session / sweep_idle + commit 固化**
- `acquire(scope, session_id, agent_name)`：key = session scope 取 session_id、agent scope 取 agent_name；算容器名 → 登记表命中则刷新 last_used 复用 → 否则 `find_workspace` 命中则登记复用 → 否则按 scope 选档位 + 选 image `create_workspace` 新建并登记。
- `release_session(session_id)`：按 `sandbox-session-{清洗}` 查登记表，仅销毁该 session 的 **session scope** 容器并移除；agent scope / 其它 session 不动。
- `sweep_idle()`：遍历登记表，对 **agent scope 且 `now-last_used > idle_hours*3600`** 的容器**先 `commit_workspace(ws_id, fleetent-sandbox-agent-{清洗 key}:latest)` 再 `destroy_workspace`**（commit-then-destroy 顺序，`test_sweep_idle_commits_then_destroys_idle_agent` 守护）；session scope 不参与。时钟经 `clock` 构造参数注入（默认 `time.monotonic`），测试用可控 lambda。

**scope→档位映射（session 加固 / agent 降档）**
`build_resources_by_scope()`：session 用 `sandbox.resources` 加固档原样（`read_only=True` + `network=none`）；agent = 加固档 `replace` 叠加 `sandbox.agent_scope` override（memory/cpus/network 三项可覆盖）**再强制 `read_only=False`**——可写 rootfs 是 commit 固化依赖成立的前提（D3）。manager 默认构造时从该函数取映射；测试用 `resources_by_scope` 参数注入隔离档位。`SandboxManager.__init__` 仅在 `resources_by_scope=None` 时读配置（含 scope/idle_hours），且仅当调用方未显式指定 scope/idle_hours（仍为默认 session/2.0）时才以配置覆盖——保证显式注入优先。

**agent 镜像复用**
`acquire(agent)` 经 `_image_for`：`image_exists(fleetent-sandbox-agent-{key}:latest)` 为真则把该 tag 作 `create_workspace(image=...)` 传入；为假回退 `image=None`（client 默认 `python:3.12-slim`）。`image_exists` 用 `docker image inspect` 返回码判定，永不抛（CLI 缺失/失败 → False）。

**自解冲突（最小改动，未停下问）**
1. **配置 `sandbox.agent_scope` 字段此前不存在**：SB4 只落了 `sandbox.resources` 的 loader，proposal/design 称 agent_scope「字段定义属 SB4，本 change 消费」，但仓库现状无该字段 loader。最小处理：本 change 在 `sandbox_config.py` 新增 `build_resources_by_scope` 读取并应用 agent_scope override（仅 memory/cpus/network），未改 SB4 既有 `SandboxResources` 数据类与 `load_sandbox_resources`。视为「消费方自带 override 解析」，未侵入 SB4 owner 代码。
2. **`scope` / `idle_hours` 字段此前不存在**：按 proposal「本 change 只追加这两个生命周期字段」，新增 `SandboxLifecycle` + `load_sandbox_lifecycle`，未改 SB3 的 `load_sandbox_mode`。
3. **`image_exists` 非 design 显式列出**：D3 要求「镜像存在则用、不存在回退默认」，需要存在性探测；SandboxClient 是唯一发 docker 命令处，故在 client 加 `image_exists`（与 `docker_available` 同风格：探测返回码、不抛）。
4. **run_code 的 scope 来源**：design 未明确 run_code 用哪个 scope。取 `manager.scope`（来自配置 `sandbox.scope`，默认 session）作为单进程统一 scope，agent_name 缺失时退 `"default"`。
5. **agent_scope override 仅认 memory/cpus/network**：read_only 由 D3 强制 False（不允许 override 翻回 True，否则固化失效）；exec_timeout 属 wave-3，不在 override 范围。

**需 zy 核实**
1. **release_session / sweep_idle 接线点（Open Question，未接线）**：本 change 只提供 `release_session` / `sweep_idle` 入口与单测，**未在 session_mgr/server/调度器接线**。release_session 挂会话关闭还是 server 请求结束待定；sweep_idle 启动触发与 SB8 孤儿清理合流、定期触发待调度器接入。当前 session scope 容器不会自动回收（依赖后续 change 或 SB8 兜底）。
2. **agent_scope override 是否应认 SB4 owner 而非本 change 自解析**：本 change 在 sandbox_config 自加 `build_resources_by_scope` 读 agent_scope。若团队认为该字段解析应归 SB4，可后移；当前作为消费方就近实现。
3. **`_MANAGER` 单进程单例 scope 固定**：所有 run_code 共用 `manager.scope`（进程级配置），不支持「不同 agent 不同 scope」。design 的 scope 是全局配置项，符合现状；若未来要 per-agent scope 需扩展。
4. **commit 镜像累积/清理策略**（Open Question）：仅销毁前 commit 一次，未实现镜像保留/清理（保留最近一份 vs 累积），待认领。

## 17. sandbox-secret-injection (SB5)：沙箱环境变量受控注入 + 统一名称过滤

**范围**：「干净环境 + 防泄漏」。不注入合法凭据、不加 allowlist、不扫描变量值（仅按名过滤）。复用 SB3 的 `features.sandbox_env`，不另立列/字段。

### 实现要点

- **D1 名称过滤纯函数**（新建 `src/fleetent/sandbox_secrets.py`）：`SENSITIVE_TOKENS: tuple[str, ...] = ("TOKEN","KEY","SECRET","PASSWORD","PASSWD","CREDENTIAL","PRIVATE","AUTH")`，模块级常量可 monkeypatch 扩展（可扩展的最小集、非穷尽）。`is_sensitive_name(name) -> bool` 对 `name.upper()` 做子串 `in` 判定。保守取向：`MONKEY`/`TURKEY`（含 `KEY`）也判敏感——宁可少注入不可泄漏，spec scenario 钉死。

- **D2 三层合并 + 统一过滤管线**：`build_sandbox_env(host_env=None, agent_env=None, runtime_env=None, include_host=False) -> dict[str, str]`。优先级 host < agent < runtime（后覆盖前同名键）。host 仅 `include_host=True` 才纳入（默认 `False`=干净环境，host_env 缺省取 `os.environ`）。**合并后对全集统一 `is_sensitive_name` 过滤**（单一过滤点，任何来源的敏感名都剔除，难绕过）。

- **D3 create_workspace 注入 + 防御性二次过滤**：`create_workspace(name, resources, image, env)` 新增 `env: dict[str, str] | None = None`。新增 `_env_flags(env)` 静态方法把每项转 `-e {k}={v}`，**注入前再跑一次 `is_sensitive_name` 兜底剔除**（纵深防御，不信任调用方）；None/空返回 `[]`（与现状等价，docker run 不带 `-e`）。`_env_flags` 插在 `*self._resource_flags(...)` 与 `image` 之间。

- **D4 注入来源仅限 agent `features.sandbox_env`（钉死）**：run_code 经 SB3 上下文通道取 `tool_context.features.get("sandbox_env")` 作 `agent_env` 传 `build_sandbox_env(agent_env=...)`（host 不传、`include_host` 默认 False）。`runtime_env` 形参保留作管线完整性，但**无任何调用方接入**（不接受运行时/AI 在 run_code 传 env，缩小攻击面）。

### env 经 acquire → create_workspace 串接（本 change 自行串接）

最小改动：给 `SandboxManager.acquire(scope, session_id, agent_name, env=None)` 加可选 `env` 形参，在新建分支透传到 `create_workspace(..., env=env)`；reuse / re-adopt（registry hit、find_workspace 命中）分支不重新注入——复用容器保留创建时的 env（与 SB2 复用语义一致）。`env=None` 时 acquire/create_workspace 行为与 SB2 等价，既有用例不破。

run_code 调用链：`run_code` 读 `tool_context.features`（无 context 时 `{}`）→ `agent_env = features.get("sandbox_env")` → `env = build_sandbox_env(agent_env=agent_env)` → `manager.acquire(scope, session_id, agent_name, env=env)`。无 `sandbox_env` 时 `agent_env=None`，`build_sandbox_env` 返回 `{}`（空映射，等价干净环境）。

### 宿主 ANTHROPIC_API_KEY 不泄漏守卫

`config.Settings.anthropic_api_key` 经 `os.environ` 的 `ANTHROPIC_API_KEY`，名称含 `KEY` → `is_sensitive_name` 命中剔除。即便 `include_host=True` 或某来源显式写入 `ANTHROPIC_API_KEY`，统一过滤都剔除；create_workspace 内还有防御性二次过滤兜底。单测 `test_build_sandbox_env_host_anthropic_key_never_leaks` 把该键写入 host/agent/runtime 三处并断言输出不含。

### 1.x 前置核实结论

- 1.1：`create_workspace`（SB2 收敛签名）当前 docker run 不带 `-e`，加 `env` 形参 None/空与现状等价——已核实。
- 1.2：宿主 `ANTHROPIC_API_KEY` 含 `KEY`，被过滤规则命中剔除——已核实。
- 1.3：agent 注入承载位 = SB3 `agent_store.features` 列下 `sandbox_env` 键；`ToolContext.features`（SB3 D5）已就位，docstring 已预留 "SB5 env injection"，上下文通道已通——已核实。

### 自解冲突 / 决策

- **acquire 复用分支不重注入 env**：reuse/re-adopt 容器保留创建时 env，符合 SB2「容器复用」语义；只在新建分支注入。最小改动且不破坏既有复用测试。
- **`features.get("sandbox_env")` 返回 Any**：`ToolContext.features` 为 `dict[str, Any]`，`get` 返回 `Any`，直接传 `build_sandbox_env(agent_env=...)`（形参 `dict[str,str]|None`）mypy 不报错（Any 可赋值）；不额外加运行时类型转换（信任 SB3 承载位约定 + create_workspace 防御过滤兜底）。
- **`_env_flags` 做成 `@staticmethod`**：与既有 `_resource_flags` 风格一致，纯映射无实例状态。

**需 zy 核实**

1. **复用容器的 env 变更不生效**：agent 改了 `features.sandbox_env` 后，已在 registry 的 session/agent 容器不会重建注入新 env，需等容器销毁重建（release_session / sweep_idle）才生效。当前可接受（env 多为静态配置），若需热更新需扩展。
2. **`-e` 明文出现在宿主 `docker run` 进程参数**（design D3 已记 trade-off）：仅非敏感变量经此路径，敏感已过滤；占位符级方案留后续。

## sandbox-orphan-cleanup (SB8)

孤儿沙箱容器清理：平台启动时触发一次 + 提供按需手动触发入口，**不引入调度器**。复用 SB2 的 `SANDBOX_NAME_PREFIX`。

### 改/建文件

- 新建 `src/fleetent/sandbox_cleanup.py`：`cleanup_orphans(client: SandboxClient) -> int`。
- 改 `src/fleetent/sandbox_client.py`：新增 `list_containers(name_prefix: str) -> list[str]`（插在 `find_workspace` 与 `commit_workspace` 之间）。
- 改 `src/fleetent/server.py` lifespan：复用 SB3 探测结果，可用才调清理。
- 新建 `tests/test_sandbox_cleanup.py`；扩 `tests/test_sandbox_client.py`、`tests/test_server_lifespan.py`。

### D1 清理独立模块

`sandbox_cleanup.cleanup_orphans` 为纯编排：`names = await client.list_containers(SANDBOX_NAME_PREFIX)` → 逐个 `startswith` 校验后 `await client.destroy_workspace(name)` → 返回成功销毁计数。空列表/Docker 不可用（`list_containers` 返回空）→ 返回 0。前缀常量 `from fleetent.sandbox_client import SANDBOX_NAME_PREFIX`，**不在本模块重复定义**（单一事实来源）。

### D2 list_containers

`docker ps -a --filter name={prefix} --format {{.Names}}`，按 `splitlines()` 解析、过滤空行。`-a` 含已停止容器（孤儿可能 exited 未删）。失败安全降级（与 `docker_available` 同风格）：`FileNotFoundError`/`OSError` → log warning 返回 `[]`；非零 returncode → log warning（含 stderr）返回 `[]`，**不抛**。

### D3 前缀二次校验防误删

`docker --filter name=` 是**子串匹配**，可能误纳入名字中段含 `sandbox-` 的无关容器（如 `my-sandbox-backup`）。故对 `list_containers` 返回的每个名称，销毁前在 Python 侧再校验 `name.startswith(SANDBOX_NAME_PREFIX)`，不满足则 log warning 跳过、不计数、不销毁。单测 `test_cleanup_orphans_skips_names_without_prefix` 钉死：混入 `my-sandbox-backup`/`not-related` 时只销毁真前缀容器、计数为 1。

### D4 lifespan 复用 SB3 探测结果（不重复探测）+ 失败不阻断

**关键接线**：SB3 原本 inline `await SandboxClient().docker_available()`，改为先建 `sandbox_client = SandboxClient()` 实例、`docker_available = await sandbox_client.docker_available()`（**只探测一次**）。该 `docker_available` 结果同时驱动 SB3 的 `resolve_effective_mode` 与本 change 是否清理。SB8 紧跟其后：`if docker_available: try: await cleanup_orphans(sandbox_client) except Exception: log warning 继续`。

- **不重复探测**：复用同一 `sandbox_client` 实例与同一 `docker_available` 布尔，无第二次 `docker version` 子进程。单测 `test_lifespan_skips_cleanup_when_docker_unavailable` 用 `probe.assert_awaited_once()` 钉死「探测仅一次」。
- **失败不阻断**：`cleanup_orphans` 抛异常被 try/except 捕获，log `sandbox_orphan_cleanup_failed` warning 后继续启动（`/health` 仍 200）。单测 `test_lifespan_cleanup_failure_does_not_block_startup` 验证。
- **Docker 不可用跳过清理**：`docker_available=False` 时整段跳过（mode 由 SB3 降级 OFF），不调 `cleanup_orphans`。单测 `test_lifespan_skips_cleanup_when_docker_unavailable` 验证 `cleanup.assert_not_awaited()`。

### 审计 log

`cleanup_orphans` 结束 `logger.info("sandbox_cleanup_done count=%d destroyed=%s", len(destroyed), destroyed)`——**计数 + 被删容器名列表**。被跳过的非前缀名单独 `logger.warning("sandbox_cleanup_skipped_non_prefix name=%s")`。写入 trace 的形态待 SB9 落地后协调（本 change 仅 log）。单测 `test_cleanup_orphans_logs_count_and_names` 断言日志含计数与各名称。

### 按需触发入口

`cleanup_orphans(client)` 是可独立调用的纯函数，不依赖 server/lifespan/调度器，返回计数供 admin/运维手动触发。单测 `test_cleanup_orphans_callable_standalone_returns_count` 验证（仅传 mock client 即可调用）。admin CLI 子命令暴露为可选收尾（design Open Question），**本 change 不实现**。

### 1.x 前置核实结论

- 1.1：前缀 `SANDBOX_NAME_PREFIX = "sandbox-"`（sandbox_client.py 行 18，SB2 定义）；`destroy_workspace`（行 217，`docker rm -f` 幂等，已忽略 returncode）——已核实，清理直接复用销毁。
- 1.2：lifespan 行 69；SB3 探测在行 78（原 inline）。改造形态：提取 `sandbox_client` 实例变量，`docker_available` 布尔可在同函数后续复用——已核实，SB8 紧随其后接线。
- 1.3：前缀常量定义在 `sandbox_client.py`，本 change `import` 复用、不重复定义——已核实。

### 自解冲突 / 决策

- **复用 SB3 client 实例**：将 SB3 的匿名 `SandboxClient()` 提升为 `sandbox_client` 命名变量，供 `cleanup_orphans` 复用同一实例（client 无状态廉价，复用纯为可读性与「同一探测结果」语义）。最小改动，SB3 既有用例不破（探测仍一次、mode/health 行为不变）。
- **空行/格式**：`ruff format` 误在 `from fleetent import webhook_router as _wr` 后插空行（非本 change 触碰行），已还原。server.py 既有 ruff 错误（`os`/`typing.Any` 未用、import 排序）为遗留，stash 验证基线同样报 4 条，未触碰。

### 基线对比

- pytest：1123 → **1137 passed**（+14 新增，无回归）。
- ruff（自有文件 `sandbox_cleanup.py`/`sandbox_client.py` 及三测试文件）：format + check 全绿。
- mypy `src`：74 → **74**（无新增错误模式；新建 `sandbox_cleanup.py` 无 mypy 错误，checked files 56→57）。

### 需 zy 核实

1. **审计写 trace 待 SB9**：当前仅 `logger.info` 计数+名单，未写 traces 表；SB9 落地后是否将清理记录纳入 trace（design D4 已记「与 SB9 协调」）。
2. **admin CLI 子命令**：design Open Question 提到 `fleetent-admin sandbox-cleanup` 按需入口，本 change 仅提供函数入口未加 CLI 子命令——是否需作为 SB8 收尾补一个 admin 子命令。

## sandbox-trace-logging — feat/sandbox-trace-logging

SB9（sandbox 轨末环）：`run_code` 执行结果写入 trace。

**前置核实结论（tasks 1.x）：**
- 1.1 `eval_logger` 的 `_LOG_PATH`（行 12，log_run 用）与 `TRACE_PATH`（行 13，log 用）取值完全相同（`Path("data/traces.jsonl")`），既有 append 写法一致（`parent.mkdir(parents=True, exist_ok=True)` + `json.dumps(..., ensure_ascii=False) + "\n"`），可选字段为 `if x is not None: entry[...]=x` 模式——可安全合并为单一常量并复用写法。
- 1.2 `log_run`/`log` 既有记录**均无 `kind` 字段**；`traces.jsonl` 全仓**只写不读**（无任何消费者）——追加 `kind` 为纯增量、零回归。
- 1.3 `run_code` 经 `_exec_or_cancel` 返回 `ExecResult`（含 `stdout`/`stderr`/`exit_code`），耗时用 `time.monotonic()` 包 exec、字节大小用 `len(s.encode("utf-8"))`，均在现路径廉价算出，**无需改 `SandboxClient`**。
- 1.4 `sandbox_scope` 来源：SB2 已合，`manager.scope` 是 `Scope` 枚举（非 None），取其 `.value`（`"session"`/`"agent"`）传入——传真实 scope 值，不传 None。

**实现：**
- `eval_logger.py`：①合并路径常量（见下）；②`log_run` entry 追加 `kind: "agent_run"`、`log` entry 追加 `kind: "im_message"`（紧跟 `ts` 之后，既有字段一个不动）；③新增 `log_sandbox_exec(elapsed_s, exit_code, stdout_bytes, stderr_bytes, sandbox_scope=None, agent_name=None, user_id=None)`，append `{"ts", "kind":"sandbox_exec", "elapsed_s":round(.,3), "exit_code", "stdout_bytes", "stderr_bytes"}`，可选三字段非 None 才写（同 log_run 模式），复用统一常量 mkdir+append 写法。
- `tools.py`：`run_code` 顶部 `import time`/`import logging`、`from fleetent import eval_logger`、模块级 `logger`；`start=time.monotonic()` 包住 `_exec_or_cancel`、`elapsed=monotonic()-start`（仅测 exec，不含 acquire）；exec 后调 `log_sandbox_exec`（`stdout_bytes/stderr_bytes` 用 `len(.encode("utf-8"))`、`sandbox_scope=scope.value`、`agent_name=agent_name`），包 try/except，失败 `logger.warning(..., exc_info=True)` 不 re-raise。

**自解冲突 / 决策：**
- **常量合并如何保向后兼容**：D6 要单一隔离点，但既有测试两处分别 monkeypatch `_LOG_PATH`（11 处）与 `TRACE_PATH`（3 处）。若保留 `_LOG_PATH = TRACE_PATH` 别名，仍是两个模块属性 → monkeypatch 其一不影响另一，隔离漏洞照旧、违背 D6 本意。故**取消 `_LOG_PATH`，保留 `TRACE_PATH` 为唯一常量**，`log_run`/`log`/`log_sandbox_exec` 三处统一引用它；同步把 `test_eval_logger.py` 11 处 `_LOG_PATH` monkeypatch 更新为 `TRACE_PATH`（指令明确允许「更新引用确保单一隔离点」）。新增断言 `not hasattr(el, "_LOG_PATH")` 守卫第二常量不再复活。
- **取消路径是否写 trace**：**不写**。取消时 `_exec_or_cancel` 返回 None，没有 `ExecResult`，无真实 `exit_code`/输出字节；`elapsed` 此时是「取消检测延迟」而非执行时长。写占位 metadata 会污染 `sandbox_exec` 的语义（其字段应恒为真实 exec 结果），故取消路径直接 return，不写 trace。加测试 `test_run_code_does_not_log_trace_on_cancel` 断言取消时 `log_sandbox_exec` 不被调用。
- **sandbox_scope 取 manager.scope 真实值**：SB2 已合，`manager.scope` 为 `Scope` 枚举（非 None），传 `scope.value`（字符串 `"session"`/`"agent"`），非 design 早期假设的 None。测试断言 `sandbox_scope == "session"`。
- **user_id 不传**：`log_sandbox_exec` 形参含可选 `user_id`，但 `ToolContext`（SB3 所有）当前**无 `user_id` 字段**，run_code 执行上下文拿不到。给 ToolContext 加字段属改 SB3、超出本 change 范围（「不改 SB3」），故 run_code 调用**省略 user_id**（可选字段省略即不写入）；保留 `log_sandbox_exec` 的 user_id 形参供未来接通。

**验证：**
- pytest：1137 → **1149 passed**（+12 新增：eval_logger 9、tools 3；无回归）。
- ruff（自有文件 `eval_logger.py` + `test_eval_logger.py` + `test_tools.py`）：format + check 全绿。`tools.py` 残留 2 个 I001/F401（`schedule_task` 内 `cron_scheduler` 未用导入）经 `git stash` 验证为**基线既有**，非本 change 引入，未触碰。
- mypy `src`：74 → **74**（无新增错误模式）。

### 需 zy 核实

1. **取消路径不写 trace**：本 change 决定取消时不记 trace（无真实 exec metadata）。若运营需统计取消频率，未来可考虑用一个独立 `kind`（如 `sandbox_cancelled`）记录——本 change 不做，待确认是否需要。
2. **user_id 维度缺失**：因 ToolContext 无 user_id，sandbox_exec trace 暂无 user_id 维度（仅 agent_name + scope）。若需按用户统计 run_code，需在 SB3 给 ToolContext 加 user_id 并接通——属跨 change，未做。
3. **elapsed 仅测 exec**：依 design D4/Open Question 取「仅 exec 时长」，容器获取时长归 SB2，未含在内。

## plugin-tools (AR7) — feat/plugin-tools

第三个工具来源（插件目录）：企业团队在 `plugins/{name}/` 放 `plugin.yaml` + `__init__.py`（含 `@tool`），平台启动扫描加载 `enabled: true` 的插件，工具加 `{插件名}__{工具名}` 命名空间，agent 经 `plugins` 白名单授权。

**前置核实结论（tasks 1.x）：**
- 1.1 `tool_registry._registry` 为 `dict[name, (callable, schema)]`（行 32）、`_risk_levels` 为 `dict[name, str]`（行 33）。改键需同步迁移**两处**（`_registry` + `_risk_levels`）并改 `schema["function"]["name"]`。`@tool` 注册时键 = 函数名（行 57-58）。
- 1.2 `mcp_client._make_tool_name`（行 164-165）= `f"{server_id}__{tool_name}"`（双下划线）；MCP 直接写 `tr._registry[...]`（行 500-501）。插件改键**沿用同一双下划线格式**。
- 1.3 `Agent` 现字段 `id/name/system_prompt/allowed_tools/features`（dataclass 行 14-23）。读写点：`create_agent`、`_row_to_agent`（被 `get_by_name`/`get_agent_for_user`/`get_agent_for_channel` 复用）、`_SELECT_COLS`、`_init_db` DDL。
- 1.4 **真实授权门 = agent_loop 暴露给 LLM 前的 schema 过滤**（`run()` 行 519-520、`run_stream()` 行 849-851 调 `check_tool_access`）。`dispatch` 内的 `check_tool_access` 分支（行 118-122）在生产路径**死分支**——`_safe_dispatch` 从不传 `allowed_tools`。故 plugins 展开并入 server 构造的 `allowed_tools`、经 schema 过滤生效，**不改 `check_tool_access` 签名、不碰 dispatch**。
- 1.5 `skill_registry._resolve_skills_dir`（行 54-58）现状**已读 `FLEETENT_SKILLS_DIR`**（CLAUDE.md 的改名已落地，artifact 里的 `MINI_AGENT_` 已过时）。插件随此约定用 **`FLEETENT_PLUGINS_DIR`**。lifespan 调用点 server.py 行 71（`scan_skills()`）。
- 1.6 **plugins 加列走 alembic**（同 SB3 features，zy 指示）：`_init_db` 的 CREATE TABLE 内联 `plugins TEXT NOT NULL DEFAULT '[]'`（新库/测试天然有列）；新增 alembic `003_add_agent_plugins`（`op.add_column`，供现有生产库），**非运行时 PRAGMA+ALTER**。

**实现（改/建文件）：**
- **建** `src/fleetent/plugin_loader.py`：`PLUGINS_DIR="./plugins"`（模块级可 monkeypatch）、`_resolve_plugins_dir`（arg > `FLEETENT_PLUGINS_DIR` env > 默认）、`PluginMeta`（frozen：name/enabled/path[+version/description]）、`expand_plugin_patterns(plugins)->["{name}__*",...]`、`load_plugins(plugins_dir=None)->list[PluginMeta]`（扫子目录→读 manifest→enabled 过滤→唯一性校验→importlib 导入→`_namespace_new_keys` 改键）。
- **建** `migrations/versions/003_add_agent_plugins.py`：`revision="003"`, `down_revision="002"`, `upgrade()` `op.add_column("agents", sa.Column("plugins", sa.Text(), nullable=False, server_default="[]"))`, `downgrade()` `op.drop_column`。参照 002。
- **改** `src/fleetent/agent_store.py`：`Agent` 加 `plugins: list[str]=field(default_factory=list)`；`create_agent` 加 `plugins` 形参 + INSERT；`_SELECT_COLS` 加 `plugins`；`_row_to_agent` `json.loads(row[5] or "[]")`；`_init_db` CREATE TABLE 加列。**仅** plugins 相关最小改动，不动其它（撞车风险，见下）。
- **改** `src/fleetent/server.py`：import `expand_plugin_patterns, load_plugins`；lifespan `scan_skills()` 后调 `load_plugins()`；行 ~229 `allowed_tools = agent.allowed_tools + expand_plugin_patterns(agent.plugins) if agent else None`。
- **改** `src/fleetent/agent_loop.py`：`run_sync` 在 `scan_skills()` 后局部 import 并调 `load_plugins()`（CLI 加载时机，见下）。
- **改** 测试：`tests/test_plugin_loader.py`（新建，22 例）、`tests/test_agent_store.py`（+4 plugins 例）、`tests/test_server.py`（+plugins 并入 allowed_tools、+lifespan load_plugins）、`tests/test_agent_loop.py`（+run_sync load_plugins）。

**plugin_loader 改键三要点：**
- **只对本插件包内键**：`_namespace_new_keys` 仅改写 (a) import 前 registry 不存在的新键 **且** (b) callable `__module__` 属于本插件包（`owner == package or owner.startswith(f"{package}.")`）。排除插件 `__init__.py` 间接 import 的注册副作用模块（如 `fleetent.tools` 或第三方 helper）带来的既有/外来工具键——避免污染内置/MCP 工具键。守卫测试 `test_indirect_import_does_not_namespace_foreign_tools` 已验证（去掉 owner 过滤即变红）。
- **双下划线命名空间**：`{插件名}__{工具名}`，与 MCP 一致。
- **命名空间全局唯一校验（D6）**：`_reserved_namespaces()` = MCP `_server_registry` 键 ∪ 内置工具命名空间前缀（`key.split("__",1)[0]` 或裸键）；`taken` 累加已加载插件名。插件名冲突（与 MCP server_id / 内置前缀 / 另一插件）→ `logger.warning("plugin_namespace_conflict")` + 跳过、**不 import、不改写既有键**。改键时目标命名空间名已存在→ `logger.warning("plugin_tool_name_conflict")` + 跳过该工具。

**D3 授权（plugins 展开经 schema 过滤）：** agent 的 `plugins` 经 `expand_plugin_patterns` 展开为 `{name}__*` 并入 server 构造的 `allowed_tools`，交由 agent_loop 暴露给 LLM 前的 schema 过滤（`check_tool_access`）判定。未授权插件工具不出现在 LLM 工具列表。**不改 `check_tool_access` 签名、不依赖 dispatch 死分支**。测试用 `check_tool_access` 直接断言 schema 可见性（授权可见、未授权被过滤）。

**D4 容错 + D5 加载时机：**
- 每插件 `_load_one` 全程 try/except（仿 `mcp_client.register_all`）：manifest 缺失/非法 YAML/顶层非 mapping/缺 name → `logger.warning("plugin_manifest_invalid")` + 跳过；import 抛异常 → `logger.warning("plugin_import_failed")` + 跳过。单插件失败不中断遍历，目录不存在返回 `[]`。不吞异常（均以 warning log）。
- **server**：lifespan `scan_skills()` 后调 `load_plugins()`（启动一次）。
- **CLI（自解 Open Question）**：`run_sync` 已每次调用 `scan_skills()`，**为一致性也每次调 `load_plugins()`**（局部 import 避免顶层循环依赖）。CLI 不解析 agent、`allowed_tools=None`，故插件工具在 CLI 路径**不受 agent 级授权门控、全部暴露**——与 CLI 暴露全部内置工具的现状一致（CLI 无 per-agent 授权语义）。

**自解冲突 / 决策：**
- **env 前缀**：artifact 称 skill 现用 `MINI_AGENT_`，但核实发现 `skill_registry` **已改为 `FLEETENT_SKILLS_DIR`**。插件直接用 `FLEETENT_PLUGINS_DIR`，与现状一致。
- **enabled 缺省**：manifest 无 `enabled` 字段 → 视为 `False`（`parsed.get("enabled", False)`），保守不加载（避免误把未声明启用的目录当插件 import）。disabled 插件仍返回 meta（供 introspect），但不 import。
- **plugins NOT NULL 的 NULL-行测试**：列为 `NOT NULL DEFAULT '[]'`（alembic `op.add_column(nullable=False, server_default="[]")` 会回填既有行为 `'[]'`，真实 NULL 不会出现）。`_row_to_agent` 仍保留 `or "[]"` 防御性兜底；NULL-行测试改为直接对 `_row_to_agent` 传 `row[5]=None` 验证兜底（无法对 NOT NULL 列写 NULL）。
- **load_plugins 返回值语义**：返回所有 manifest 解析成功的插件 meta（含 disabled），便于 introspect 已发现什么。

**验证：**
- pytest：1149 → **1177 passed**（+28：plugin_loader 22、agent_store 4、server 2（plugins 并入 + lifespan）、agent_loop 1（run_sync load）；无回归）。每批严格 TDD 先红后绿；owner-filter 守卫测试经「去掉过滤→变红」反向验证为 load-bearing。
- ruff（自有/改动文件）：`plugin_loader.py`/`003_*.py`/`test_plugin_loader.py`/`test_agent_store.py`/`agent_store.py` 全绿；`server.py`(4)、`agent_loop.py`(1) 残留 ruff 错误经 `git show HEAD` 对比为**基线既有**（N814/I001/F401，非本 change 引入）；`test_server.py` 经排序内联 import 回到基线 2 个 I001（均既有函数）。
- mypy `src`：74 → **74**（无新增错误模式；plugin_loader.py 零 mypy 错误）。

### 需 zy / 张亮 核实

1. **【需张亮复核迁移】** plugins 列按 zy 指示走 **alembic 003 迁移**（`op.add_column`，非运行时 ALTER），CREATE TABLE 内联。`003_add_agent_plugins.py` 的 revision 链（003→002→001）、`server_default="[]"` 回填既有行——**需张亮（agents 表 / db-migration 邻域 owner）复核迁移**。
2. **【需张亮签字 / 归档闸门】** 本 change 在 Modified Capabilities 声明 MODIFY 张亮的 `agent-definition` spec（Agent/agents 表加 plugins + allowed_tools 通配纳入 plugins 展开）。apply 阶段**只实现代码，未手动改 `openspec/specs/agent-definition/spec.md` 主 spec**（archive 时 sync）。change 目录下 specs/ delta 为 propose 时所写，未动。**agent-definition spec MODIFY 需张亮签字后方可归档**。
3. **【agent_store 撞车风险】** 张亮活跃于 agents 表邻域（features/SB3）。本 change **仅**加 `plugins` 列 + `Agent.plugins` + 最小读写改动，未动其它字段/查询。merge 时需关注与张亮 agents 表改动的冲突。
4. **CLI 加载时机**：自解为「`run_sync` 每次调 `load_plugins()` + CLI 无 agent 授权门控、插件工具全暴露」。若需 CLI 也按某默认 agent 的 plugins 授权，需 zy 确认（本 change 维持 CLI 暴露全部工具的现状）。

## 21. connector-credential-injection（T1：dispatch 接通 connector 凭证注入）

**范围**：纯地基——`@tool` 声明 connector/scopes、新建 `connectors.py` 契约 + provider 缝、`dispatch` 注入隐藏 `client` / `NeedsConsent` 短路、`user_id` 向后兼容。真实 OAuth 存储/刷新是后续 connector-oauth-store change。

**前置核实（tasks 1.x）：**
- **1.1** `_build_schema` 现状**未**排除 keyword-only / `client`：REPL 验证 `def t(q, *, client)` 的 schema `properties` 含 `client` 且进 `required`。→ 需补过滤（见下）。
- **1.2** dispatch 调用点：`agent_loop._safe_dispatch`（行 ~200）唯一直接调 `dispatch` 处；其下游 3 个 `_safe_dispatch` 调用点（run 审批分支、run 非审批分支、run_stream）均在 `user_id` 作用域内。`sub_agent.py` 不直接调 dispatch（经 agent_loop）。新增末位 kw `user_id=None` 向后兼容，无既有调用点报错。
- **1.3** `eval_logger._serialize` / `log_run` 写的是 messages（assistant tool_calls 的 arguments + tool role 的 content=dispatch 返回值）；注入的 `client` 既不在 LLM arguments、也不写回 kwargs、也不进返回值 → 天然不入 trace。加 `test_no_credential_in_trace` 守卫。

**自解决策：**
- **client 不进 schema 用 `_OUT_OF_BAND_PARAMS`（非 keyword-only kind 判定）**：与现状机制一致——现有代码已用模块级 `_OUT_OF_BAND_PARAMS` frozenset 排除 `cancel_token`/`tool_context`。最小一致做法是新增模块级常量 `_CLIENT_PARAM = "client"` 并并入该 frozenset，`_build_schema` 的既有 `if param_name in _OUT_OF_BAND_PARAMS: continue` 同时覆盖三者。**否决** D4 备选的 `param.kind == KEYWORD_ONLY` 判定：会改既有过滤口径、且 cancel_token/tool_context 当前是普通带默认值参数（非 keyword-only），统一按名字排除更一致、侵入更小。代价：tool 必须用名为 `client` 的参数接注入（约定固定名，与 cancel_token/tool_context 同模式）。
- **provider 缝默认 `NeedsConsent`**：`connectors._default_provider` 永远返回 `NeedsConsent`（真实 OAuth 未实现）。`_provider` 为模块级可 monkeypatch 名字（非全局可变单例）；额外提供 `set_provider()`（`global _provider`，供后续 OAuth store change 接入，测试以 monkeypatch 为主）。`get_credential(user_id=None,...)` 不咨询 provider、直接返回 `NeedsConsent`（安全降级，D6）。
- **凭证不泄漏守卫（D5 双保险）**：①`Credential.secret` 字段 `field(repr=False)` + 自定义 `__repr__`/`__str__` 固定输出 `Credential(connector=..., client=<redacted>)`，不含 secret 文本；②`dispatch` 注入的 `client` 经 `fn(**kwargs, client=cred.client)` 带外传入，不写回 `kwargs`、不进返回值；③守卫测试：`test_dispatch_does_not_leak_secret_in_result`（返回值无 secret）+ `test_no_credential_in_trace`（完整 dispatch → `eval_logger._serialize` 序列化 messages，断言 JSON blob 无 secret）。dispatch / connectors 自身抛出的异常消息不含凭证（NeedsConsent 提示串只含 connector 名 + consent_url，无 secret）。
- **NeedsConsent 提示串格式**：`"connector '{connector}' requires authorization before this tool can run. Ask the user to grant access here: {consent_url}"`——含 connector 名 + consent_url，不含 secret，LLM 可据此引导用户授权。
- **connector 元数据平行存储（D1）**：模块级 `_connectors: dict[str, tuple[str, list[str]]]`（与 `_risk_levels` 平行）+ `get_connector(name) -> tuple[str,list[str]]|None`。`scopes` 缺省 `[]`。不进 LLM schema。`@tool` 新增 `connector`/`scopes` kw（含 overload 签名更新）。test_tool_registry 的 `clean_registry` fixture 扩展为同时快照/恢复 `_connectors`（防注册泄漏）。
- **dispatch 流程（D3）**：access control 通过 → 注入 cancel_token/tool_context（现状不变）→ `get_connector(name)`：None → 现状 `fn(**kwargs)`（无 connector 工具行为字节级不变、不调 get_credential）；非 None → `connectors.get_credential(user_id, connector, scopes)`，`NeedsConsent` 短路返回提示串、不调用工具，`Credential` → `fn(**kwargs, client=cred.client)`。`connectors` 在 dispatch 内局部 import（避免顶层循环依赖、与 agent_policy 局部 import 同模式）。

**验证：**
- pytest：1177 → **1195 passed**（+18：test_connectors 7、test_tool_registry 10（connector 元数据 3 + client 不进 schema 1 + dispatch 注入/短路/不泄漏 6，去重后实际 +10）、test_agent_loop 1（_safe_dispatch 透传 user_id））。每批严格 TDD 先红后绿。
- ruff（自有/改动文件）：`connectors.py`/`tool_registry.py`/`test_connectors.py`/`test_tool_registry.py`/`test_agent_loop.py` 全绿。`agent_loop.py` 残留 1 个 N814（`CompletionUsage as _CU`，行号经 git show HEAD 对比为**基线既有**，非本 change 引入，且不在本 change 改动行）。
- mypy `src`：74 → **74**（无新增错误模式；connectors.py / tool_registry.py 零 mypy 错误；agent_loop.py 8→8 同模式，仅行号位移）。

**需 zy / 张亮 核实：**
1. NeedsConsent 提示串文案（英文 + connector 名 + consent_url）是否符合 LLM 引导授权预期——本次定稿，后续 connector-oauth-store 可调整。
2. `client` 固定参数名约定（与 cancel_token/tool_context 同走 `_OUT_OF_BAND_PARAMS` 名字排除）——若后续需多 client 或自定义注入名，需扩展机制。
3. `set_provider()` 用 `global _provider`：本 change 测试全部走 monkeypatch（不调 set_provider 改全局），`set_provider` 仅为后续 OAuth store change 预留接入点；若团队认为 `set_provider` 也算「全局可变状态」红线，可移除只留 monkeypatch 缝。
