## 1. im_users unlink + pending-link 存储

- [x] 1.1 **测试（红）**：`im_gateway_management/identity.py` 新增 `unlink_identity(platform, platform_user_id)` 删该映射行（幂等：不存在不报错）；pending-link 存储（`put(code,user_id,tenant)` / `pop_valid(code)` 含 TTL 过期）。先跑见红。
- [x] 1.2 **实现（绿）**：`unlink_identity` + pending-link 临时存储（短 TTL，仿 session 内存态）。跑见绿。

## 2. 平台 link 端点（web 发起 initiate / unlink，OIDC-session 认证）

- [x] 2.1 **测试（红）**：`POST .../link/initiate`（OIDC/admin session）→ 出一次性 code + 存 pending-link；`POST .../link/unlink`（认证）→ 调 `unlink_identity` + 写审计；未认证→拒。先跑见红。
- [x] 2.2 **实现（绿）**：两端点（platform user_management 或 link 模块），用 #1 的 session 认证发起方；unlink 写 `audit_log`。跑见绿。

## 3. 平台 link-confirm（node→platform）+ attach-only 绑定

- [x] 3.1 **测试（红，integration 真 DB）**：`POST /nodes/{node_id}/link-confirm`（node-key）带 `(platform, platform_user_id, code)`：(a) code 有效 + 渠道未映射 → `_attach_identity` 到 pending.user_id + 审计；(b) code 过期/错 → 拒；(c) 渠道已映射别的 user → 拒不合并（attach-only）；(d) 无/错 node-key → 401/403。先跑见红。
- [x] 3.2 **实现（绿）**：在 `node_desired_state_api` 加 link-confirm 端点（仿 identity/resolve），校验 code + attach-only 绑定 + 审计。跑见绿。

## 4. node IM-edge 截 /link + 收尾

- [x] 4.1 **测试（红）**：node IM-edge 在转发给 agent normalizer **之前**识别 `/link <code>` → 调 link-confirm（不进 agent loop）；普通消息不受影响。先跑见红。
- [x] 4.2 **实现（绿）**：`node/im_edge.py`（或其入站处理）拦截 `/link <code>` → POST link-confirm；回执给用户（linked/失败）。跑见绿。
- [x] 4.3 **收尾**：`make test-pr` 全绿（对照 main 基线无新增失败）+ 跑相关测试 `uv run pytest tests/integration/test_node_desired_state_api.py tests/integration/<im identity 测试> tests/unit/<im_user 测试> -q`（无新增失败）+ 边界核验（im_gateway 不 import platform、无 agent→platform）+ 覆盖率门禁 `make test-unit-ci`（--fail-under=76）不被拉破。
- [x] 4.4 standalone 保真：`/link` 是 managed 能力；确认 standalone `fleetent agent run` 不受影响。
