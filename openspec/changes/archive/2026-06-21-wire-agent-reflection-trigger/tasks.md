> TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `uv run pytest <file>::<test> -x -q`。测试先于实现。镜像 `session/manager.py` 的 maintenance-loop 范式。合并由主会话串行做(窗口只实现 + push)。

## 1. 配置块(默认 OFF + 可配 interval,TDD)

- [x] 1.1 写测试:agent reflection 配置默认 `enabled = False`、`interval_seconds` 有保守默认且可被 agent.yaml 覆盖。先见红。
- [x] 1.2 实现:`agent_config.py` 新增 reflection 配置块(镜像 `scheduling: SchedulingSettings` / `session_cleanup_interval_seconds` 约定)。跑 1.1 见绿。

## 2. reflection 周期循环(镜像 session-maintenance,TDD)

- [x] 2.1 写测试:`_reflection_loop` 按 interval 调 `run_reflection`(patch 掉 run_reflection);单次抛错后下次仍触发(舱壁化、退出码不变);`start_reflection_scheduler` 幂等(已运行返回现有 task)、`stop_reflection_scheduler` 取消无残留。先见红。
- [x] 2.2 实现 `reflection/scheduler.py`(`_reflection_loop` + `start_reflection_scheduler`/`stop_reflection_scheduler`,模块级单 task 句柄,best-effort + 舱壁化)。跑 2.1 见绿。

## 3. boot 启停接线(TDD)

- [x] 3.1 写测试:`reflection.enabled = False` 时 boot **不**起循环;`= True` 时起;shutdown 取消且无残留。先见红。
- [x] 3.2 实现:`runtime/agent_app.py` boot 段(`start_session_maintenance` 附近)按 `reflection.enabled` 启动、shutdown/drain 段停止。跑 3.1 见绿。

## 4. apply 后 reload skill(Part 2,TDD)

- [x] 4.1 写测试:`apply_skill_proposal_to_boundary` 在 `write_skill` 后调用 `skills.registry.reload()`(spy/patch 断言被调);reload 失败不破坏 apply 既有语义。先见红。
- [x] 4.2 实现:`reflection/reflection.py` 的 `apply_skill_proposal_to_boundary` write 后调 `skills.registry.reload()`。跑 4.1 见绿。

## 5. Change 收尾验证

- [x] 5.1 `make test-pr` + `make test-unit-ci`(76% 覆盖)全绿,对照 main 基线无新增失败。
- [x] 5.2 受影响层集成测试无新增失败(reflection / agent_app boot 相关)。
- [x] 5.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过;确认未引入 agent→platform 反向依赖。
- [x] 5.4 基线冒烟:默认配置(reflection OFF)下 `fleetent agent run` 行为与改动前一致(零变化)。
