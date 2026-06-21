> TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `uv run pytest <file>::<test> -x -q`。测试先于实现。纯节点侧。合并由主会话串行做(窗口只实现 + push)。

## 1. 健康探测 + 上报(TDD)

- [ ] 1.1 写测试:`_status_payload`(或新探测函数)对 running agent——/health 200 → `health="healthy"`;非 200/连不上 → `unhealthy`;无 gateway_port → 回退 is_alive→healthy。stub backend.gateway_port + mock httpx。先见红。
- [ ] 1.2 写测试:探测抛错/超时 → 该 agent `unhealthy`,异常不外抛,reconcile 循环与其它 agent 上报不受影响(舱壁化)。先见红。
- [ ] 1.3 实现:`node/reconcile.py` 探测 loopback `/health`(短超时 httpx)+ 把 `health` 加进 `_status_payload`;按需在 `node/backend.py` 暴露 `gateway_port`(④ 已加,确认可取)。跑 1.1/1.2 见绿。

## 2. Change 收尾验证

- [ ] 2.1 `make test-pr` + `make test-unit-ci`(76% 覆盖)全绿,对照 main 基线无新增失败。
- [ ] 2.2 受影响层集成测试(node reconcile / status 上报)无新增失败。
- [ ] 2.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过;确认未引入 node→platform 反向依赖。
