## 1. 后端选型 + agent 端点解耦（地基）

- [x] 1.1 写测试：`node.backend` 缺省 `process`、配 `container` 选容器后端的工厂选型（unit）
- [x] 1.2 写测试：agent 端点解析——local 后端返回 `127.0.0.1`+loopback 端口；container 后端返回容器 host+端口（unit）
- [x] 1.3 实现 node config 增 `backend` 字段 + 后端选型工厂，`app.py:main()` 经工厂注入
- [x] 1.4 实现 backend 接口 `agent_endpoint(name, tenant) -> (host, port)`，`LocalProcessBackend` 实现（loopback）
- [x] 1.5 跑 unit 见绿

## 2. forwarder 寻址改造

- [x] 2.1 写测试：forwarder 经 `agent_endpoint` 取目标而非硬编码 `127.0.0.1`，`/chat` 与 `/ws` 均走解析端点（unit，mock backend）
- [x] 2.2 改 `forwarder.py`：`forward_chat`/`forward_ws` 用 `agent_endpoint` 拼 upstream URL
- [x] 2.3 跑 unit 见绿（local 后端路径零回归）

## 3. ContainerBackend 实现

- [x] 3.1 写测试：`spawn` 以正确 image/命令/label/网络/卷参数调 docker（unit，mock docker 调用，断言参数）
- [x] 3.2 写测试：`is_alive`/认领按 label 查容器运行态——存活返真、消失返假、node 重启认出已存活容器不重 spawn（unit，mock）
- [x] 3.3 写测试：`stop` 经 `docker exec fleetent agent stop` 触发优雅 drain、失败回落 `docker stop`（unit，mock）
- [x] 3.4 写测试：container 后端 `agent_endpoint` 返回容器网络 host + 内部固定端口（unit）
- [x] 3.5 实现 `ContainerBackend`（spawn/stop/is_alive/gateway_port/agent_endpoint）
- [x] 3.6 跑 unit 见绿

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿（无新增失败）；`node.backend=process` 路径零回归
- [x] 4.2 与 [[dockerize-deploy-stack]] 对齐 A↔B 契约定值（label 规约、网络名、内部端口、`agent run` entrypoint 角色）
- [x] 4.3 更新 specs（opsx:archive 前）
