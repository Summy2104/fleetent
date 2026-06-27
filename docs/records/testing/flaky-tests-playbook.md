# Flaky / order-dependent 测试调试 playbook

本文是一份**可复用的排障手册**：当 fleetent 出现「PR 绿、合进 main 红/次日红」或 CI 间歇红时，按本文复现、定位、修复、验收。目标是让任何一位工程师不依赖口口相传就能独立处理这类问题。

> 历史事故清单（什么改动踩了什么坑）单独记在本目录的 `2026-06-10-integration-drift-repair.md` 等记录里；本文只讲**通用方法**。

---

## 1. 先理解 CI 的现实（决定了风险有多大）

- **integration 现在是 PR + main push 的并行门禁**：`make test-integration-ci` = `pytest tests/integration -n auto -p no:cacheprovider`（零失败判据，无 coverage 插桩，~60s）。所以 integration-only 的破坏**合并前就会被挡**。
- **CI 不随机化测试顺序**：`pytest-randomly` **故意没进 deps**。CI 跑的是**固定默认收集顺序** + xdist `--dist load` 的**运行时分发**。后者是 CI 唯一的不确定性来源。

由此，flaky 分成两类，风险完全不同：

| 类型 | 触发条件 | 在 CI 的表现 |
|------|----------|--------------|
| **order 依赖**（共享态跨测试泄漏） | 仅在**收集顺序变化**或随机顺序下触发 | 当前默认顺序不踩就**休眠**；未来某 PR 增删/移动测试改变顺序时**突然炸**（经典"炸弹"） |
| **并行 / 计时 race** | xdist 运行时分发 + CPU 争用 | **每次 CI 都可能间歇红**，与顺序无关 |

**推论**：并行/计时 race 是更紧迫的（每次都可能踩）；order 依赖多数处于休眠，动测试集时才浮出。

---

## 2. 复现

### 纯 order 依赖（串行，确定性优先）

```bash
# 随机顺序扫描，固定 seed 可复现某次顺序
uv run --with pytest-randomly pytest tests/integration -p randomly --randomly-seed=N -p no:cacheprovider -q
```

定位到具体测试后，**构造确定性复现**——把"污染者"和"受害者"放进同一进程、强制顺序，比靠随机概率可靠得多：

```bash
# leaker 先跑、victim 后跑，关掉随机：必然红
uv run pytest <leaker>::<test> <victim>::<test> -p no:randomly -p no:cacheprovider -q
```

### 并行 / 计时 race

与顺序无关，靠**重复并行跑**暴露：

```bash
# 整套或 race-prone 子集，重复多轮看是否偶发红 / 异常变慢（计时 race 常伴随超时 stall）
for i in $(seq 1 25); do uv run pytest <files> -n auto -p no:cacheprovider -q | tail -1; done
```

### 复现期的两个真实坑

- **别并发跑两个 `uv run --with pytest-randomly`**：两个进程会撞 uv 的临时 env，表现为 `no tests ran`（假阴性，soak 等于空跑）。soak 串行做，或后台只留一个。
- **zsh 不对未加引号的 `$VAR` 做分词**：`pytest $FILES` 会把整串当成**一个**路径 → `file or directory not found` / `no tests ran`。用 `pytest ${=FILES}`（zsh 强制分词）或直接写字面路径。

---

## 3. 根因清单（先查这些，按命中率排序）

1. **模块级可变全局没被复位**：`<module>._state_db` / `cron_scheduler._current` / provider 健康缓存 / vector 单例等。一个测试设了、没还原，泄漏给同 worker 后续测试。
2. **测试依赖邻居泄漏的全局**：自己没接线、靠别人先跑帮它接好。单独跑就 `RuntimeError: ... not initialized`。
3. **宿主全局资源用固定名**：Docker 容器名、固定端口、固定临时路径。`-n auto` 跨 worker 并发就撞（`Conflict ... already in use` / `No such container`）。
4. **对异步/worker 前置条件用固定 sleep**：`time.sleep(0.05)` 赌某事已完成。负载下赌输 → 空转 / 超时 stall / 拿到半成品。
5. **生产命名冲突**：包内同时有 `def foo`（`__init__.py`）和 `foo.py` 子模块；任何地方 `import pkg.foo` 会把子模块绑到包属性、**覆盖同名函数**，污染整个进程。
6. **日历 / 硬编码近期日期炸弹**：测试数据写死某日期，撞上「相对 now 的 N 天窗口」，过了那天就掉出窗口。

---

## 4. 修复模式

- **自包含接线优先于全局复位**：让测试用**会自动还原的 `monkeypatch.setattr`** 把它依赖的所有全局接好（镜像生产 `set_state_db()` 之类的 boot 入口）。
  - 为什么不首选"在 conftest 加全局复位 fixture"：那会让**所有**依赖泄漏的测试同时变红，级联暴露、scope 失控。优先修当前这一个、让它自包含。
- **conftest autouse 复位 fixture**：当某个全局是**普遍**污染源（如 structlog、cron `_current`）时才用。`tests/conftest.py` 已有一排模板：`_reset_cron_current_scheduler` / `_reset_structlog_config` / `_reset_traces_reflection_state_db` / `_reset_long_term_ctx_knowledge_provider` / `_reset_agent_config_index` / `_reset_vector_store_singletons` / `_reset_sandbox_workspace_root` / `_isolate_*`。照抄模式扩展。
- **宿主全局资源按 worker 隔离**：把 worker 维度拼进资源名——`os.environ.get("PYTEST_XDIST_WORKER", "gw0")`。worker 内串行，故 per-worker 足够。
- **condition-based waiting 取代 sleep**：轮询直到条件满足（如 worker 真正认领到 job），而不是睡固定时长。
- **命名冲突 = 删/改名**：死代码直接删（消除冲突源）；活代码就改名，别留同名 landmine。
- **日历炸弹**：测试数据锚定 `datetime.now(UTC) - timedelta(...)`，别写死日期。

---

## 5. 验收标准（声明"修好了"之前）

- **确定性红→绿**：先用强制定序拿到确定性红，再证明修后绿（光"跑几次没红"不够）。
- **多 seed 扫描**：`--randomly-seed` 跑十几个不同顺序全绿。
- **race 类额外做重复并行 soak**：同一子集重复跑 N 轮，0 失败、无异常 stall。
- **双门禁**：`make test-pr`（unit + 层边界 + 改动文件 ruff）和 `make test-integration-ci` 全绿。
- 改动 `AGENTS.md` / `Makefile` / `bitbucket-pipelines.yml` 这三个文件**必跑 `make test-pr`**——它们有 unit guard 测试钉死了措辞/阈值。

---

## 6. 关于"要不要把 pytest-randomly 设成门禁"

当前决定：**不设**（`pytest-randomly` 不进 deps）。理由：order 依赖的尾巴没一次清完，设成默认门禁会间歇红、阻塞所有 PR。

如果想在**不阻塞**的前提下提前暴露休眠的 order 耦合，推荐做法是加一个**非阻塞的 nightly 随机顺序 job**（只在定时管道里 `--with pytest-randomly`，产出报告、不 gate 合并）——把"炸弹"变"预警"。这是一个尚未落地的可选项，不是现状。

---

## 7. 指针

- 复位 fixture 模板：`tests/conftest.py`（顶部一排 autouse fixture，每个 docstring 写了它防的是什么）。
- 测试分层 / 何时跑什么 / mock 策略：`AGENTS.md` 的「测试规范」段（有 unit guard 测试，别随意改措辞）。
- 历史事故记录：本目录 `docs/records/testing/`。
