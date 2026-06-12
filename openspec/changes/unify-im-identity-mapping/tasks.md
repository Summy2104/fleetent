# unify-im-identity-mapping Tasks

> 每个实现 task 严格 TDD：先写测试见红，再实现见绿。测试任务在对应实现任务之前。

## 1. 注入点与透传语义（agent 侧）

- [ ] 1.1 [测试] unit：`im_gateway/access.py` 注入点行为——未注入时 `resolve_identity` 恒等返回原生 id（standalone 锁死，守护测试）；注入 stub resolver 后返回其映射值；`set_im_identity_resolver(None)` 重置回透传（先红：注入点不存在）
- [ ] 1.2 [测试] unit：`resolve_identity` / `resolve_principal` 可选 `owner_id` 参数透传给 resolver，未传时默认 `"default"`（先红）
- [ ] 1.3 [实现] `im_gateway/access.py`：`set_im_identity_resolver` + `resolve_identity`/`resolve_principal` 扩展；docstring 声明 resolver 归属 platform、可写 platform 身份表、agent 侧不得感知实现 → 1.1/1.2 转绿
- [ ] 1.4 [测试→实现] slack.py（2 处调用点）与 telegram.py 调用 `resolve_identity` 时传入各自 connector 身份作 `owner_id`；既有 im_gateway 测试无新增失败；依赖护栏（`test_module_dependency_guardrails`）维持 im_gateway 零 platform import

## 2. platform 侧 resolver 注入与 tenant 校验

- [ ] 2.1 [测试] integration：platform 启动（server lifespan）后向 IM 路径送消息，断言落库的 `Principal.user_id` 是内部 `users.id` 且 `im_users` 出现映射行；同一 `(platform, platform_user_id)` 二次消息复用同一 user（先红：未注入）
- [ ] 2.2 [测试] integration：同一人"IM 先、bearer 后"双入口，断言两路径 `user_id` 相同（归并语义，先红）
- [ ] 2.3 [测试] integration：resolver 映射出的 user `tenant_id` 与 connector edge tenant 不一致时消息被拒 + 可诊断日志（先红）
- [ ] 2.4 [实现] `server.py` 启动注入：包装 `platform.im_gateway_management.identity.get_or_create` 的 resolver（含 tenant 校验层，校验失败抛标记异常）→ 2.1–2.3 转绿
- [ ] 2.5 [测试→实现] conftest：注入点测试间重置 fixture（防全局状态泄漏，仿 `set_api_key_resolver` 处理）

## 3. cron 复检与边界确认

- [ ] 3.1 [测试] integration：managed 模式下 IM 用户创建的 `scheduled_tasks.user_id`（现为内部 users.id）在该 user 被 block 后触发任务被拒（identity-port 平台用户复检分支自动生效）；standalone 渠道担保分支行为不变（既有测试无新增失败）
- [ ] 3.2 [实现/核实] `im_users` 唯一性维度核实（`(owner_id, platform, puid)` vs `(platform, puid)`）——若带 owner_id 维度导致同一渠道用户经两个 connector 建两个映射，按"同一 (platform, platform_user_id) 复用同一 user"处理（见 design D5/Risks）

## 4. 文档同步

- [ ] 4.1 `docs/architecture/target-architecture.md` §6：补"managed 模式下 IM edge 延伸至 platform——身份注册写由注入的 platform-owned resolver 完成，不构成 agent→platform 写；standalone 无注入、原生 id 透传"
- [ ] 4.2 `docs/architecture/data-model.md`：§3.1 跨库边 `memory_items.user_id ⇢ users` 等注明语义（managed 成立 / standalone 为 opaque 渠道原生 id）；`im_users` 实体描述更新为"渠道身份归并真相源（managed 运行时经注入 resolver 消费）"
- [ ] 4.3 `docs/capabilities/im-gateway.md` / `user-center` 相关描述复核：身份解析段落对齐注入模式（有则改，无则跳过）

## 5. 收尾

- [ ] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 5.2 `openspec validate unify-im-identity-mapping` 通过；所有 checkbox 标记 `[x]`
