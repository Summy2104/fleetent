## Context

管理 SPA(`frontend/`,React 18 + Vite + TS + React Query + Radix + Tailwind)已接通约 17/31 个用户/身份管理端点。剩余缺口的后端端点全部现成且已被后端 spec 覆盖(`web-user-management` / `im-user-mapping` / `agent-service-principal` / `platform-audit-log`),故本 change 是**纯前端补完**,不动后端与 DB。

当前相关代码:
- 用户管理面:`frontend/src/features/users/page.tsx`(含 `CreateUserDialog`、`KeysDialog`、`ImUserRow`)、`frontend/src/features/users/api.ts`(React Query hooks)。
- 独立 IM 映射面:`frontend/src/features/im-identities/`(page.tsx + api.ts),路由挂在 `frontend/src/app/routes.tsx`、导航在 `frontend/src/app/nav.ts`。
- 两个 IM 面底层同为管理库 `im_users` 表 + `im_gateway_management/identity.py` store;`/admin/im-identities` router 源码注释自述"与 `/admin/im-users` 控件并存,这是聚焦的映射管理面"。

## Goals / Non-Goals

**Goals:**
- 把服务主体创建、渠道 link 绑定/解绑、审计日志查看三块后端已有能力接出 UI。
- 将 IM 身份管理从两个并存前端面收敛为用户页 "IM Identities" 标签单一面,覆盖全生命周期。
- 复用既有组件模式(对话框、一次性凭证弹窗、React Query mutation + invalidate),保持设计系统一致。

**Non-Goals:**
- 不改任何后端端点、store、DB schema、迁移。
- 不改 IM 身份解析/并号语义(属 `im-user-mapping` 后端,本 change 不碰)。
- 不做 CSV 批量导入 UI(`web-user-management` 提及但本轮不在范围;`bulk_import_users` 仍无端点,另议)。

## Decisions

**D1 — IM 合并到用户页标签,删独立路由(而非反向)。** 把 `/im-identities` 的"新建映射"对话框迁入 `users/page.tsx` 的 IM 标签,删除 `frontend/src/features/im-identities/` 与其路由/导航项。理由:IM 身份本质是"用户的渠道账号",归在用户管理域比独立顶级导航更内聚;用户页标签已具备生命周期操作(block/restore/bind),仅缺 create,迁移成本最低。备选(保留独立面、把生命周期搬过去)被否:会让更年轻、更简单的面承载更多职责,且与"用户域"归属相悖。

**D2 — 新建映射沿用 `POST /admin/im-identities`,不切到 `/admin/im-users`。** create 语义(查重、JOIN 返回 user_name/email)已在 `im-identities` 端点实现良好,前端只搬 UI 不换端点,降低回归面。生命周期操作继续打 `/admin/im-users/*`。两端点共享底层 store 的 `delete_im_identity()`,删除行为一致。

**D3 — 服务主体创建复用 `CreateUserDialog` + `KeysDialog` 模式。** 新增 `CreateServicePrincipalDialog`,提交 `POST /admin/service-principals`,成功后用现有一次性凭证弹窗展示 `ma-` key。理由:与现有 API key 发放 UX 一致,用户无学习成本。

**D4 — 审计日志独立为 `audit-admin-ui` 能力 / `frontend/src/features/audit/` 新域。** 审计是跨域平台关注点(`platform-audit-log` 覆盖所有 admin 写操作,不止用户),不应塞进用户管理面。新建独立页面 + 导航项,匹配既有 `*-admin-ui` 每域一面的模式。

**D5 — link 绑定/解绑入口落在用户管理面用户行级操作。** initiate 返回的一次性 code + TTL 用提示性弹窗展示(非敏感长期凭证,但需提示有效期)。

## Risks / Trade-offs

- **[删 `/im-identities` 路由使旧深链/书签失效] → Mitigation**:这是有意的前端 BREAKING,范围仅管理员书签;client-side 路由对未知子路径已回落 SPA(见 `admin-frontend-spa`),不会白屏报错;在 change 说明中标注迁移路径(功能移至用户页 IM 标签)。
- **[两个 IM 面合并后操作密度变高,用户页标签可能拥挤] → Mitigation**:沿用既有 ImUserRow 行级操作菜单收纳低频操作(编辑元数据/删除),create 用对话框而非内联。
- **[审计端点 `GET /admin/audit` 的过滤/分页/导出参数形状需对齐] → Mitigation**:实现前先读 `user_admin_api.py:547` 的实际 query 参数与响应结构,以后端为准接线,避免臆测字段。
- **[i18n 遗漏导致新 UI 出现裸 key] → Mitigation**:每个新增文案同步加入翻译文件(项目已有 i18n,见近期 commit `1b33c910`)。

## Migration Plan

1. 先合并 IM 面(迁 create 对话框入用户页标签 → 删除 `im-identities` feature 目录 → 摘除 routes/nav 项)。
2. 再分别补服务主体创建对话框、link 绑定/解绑入口、审计页面。
3. 各步骤前端 TDD(组件/数据层测试),按 `admin-frontend-spa` 的前端测试纪律。
4. 回滚:纯前端改动,`git revert` 即可;无 DB/后端状态需回滚。

## Open Questions

- `GET /admin/audit` 是否已支持导出(CSV)或需前端自行从结果生成?实现 audit 页面前以后端实际能力为准——若后端无导出、`platform-audit-log` 又要求可导出,则前端基于已拉取结果生成 CSV(标注于 tasks)。
