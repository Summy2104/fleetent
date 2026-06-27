## Why

platform 后端 `user_admin_api.py` 暴露 31 个用户/身份管理端点,但管理 SPA 只接通约 17 个(~55%)。四类管理员刚需操作有后端、无 UI:**创建服务主体**(只能 curl/CLI)、**渠道身份绑定/解绑**(`/link`)、**审计日志查看**(治理/合规盲区)。同时 IM 身份管理被切成两个并存的前端面——用户页 "IM Identities" 标签(运维:绑定/禁用/恢复)与独立路由 `/im-identities`(仅新建映射),二者底层是同一张 `im_users` 表,管理员不知该去哪个面,边界只写在后端一行注释里、UI 无体现。本 change 把这些 UI 缺口一次补齐,让管理控制台与后端能力对齐。

## What Changes

- **合并 IM 身份管理为单一面**:把独立路由 `/im-identities` 的"新建映射(create)"能力并入用户页 "IM Identities" 标签,使该面覆盖 IM 身份全生命周期(新建/绑定/重绑/禁用/恢复/删除/编辑元数据);**移除**独立 `/im-identities` 路由与其顶级导航项。**BREAKING**(仅前端导航/路由):书签到 `/admin/ui/im-identities` 的深链失效,功能迁至用户页标签。
- **新增服务主体创建 UI**:用户管理面新增"创建服务主体"对话框,调用既有 `POST /admin/service-principals`,创建后展示一次性凭证(复用现有 API key 弹窗模式)。
- **新增渠道身份绑定/解绑 UI**:新增发起绑定(`POST /admin/link/initiate`,展示一次性 code + TTL)与解绑(`POST /admin/link/unlink`)的交互入口。
- **新增审计日志查看 UI**:新增审计日志页面,支持按 actor / action / target / 时间范围检索(`GET /admin/audit`)与导出。
- 接通现有但前端未用的 IM 身份端点:编辑元数据(`PATCH /admin/im-users/{id}`)、删除(`DELETE`)、字段定义(`GET /admin/im-users/fields`)。

后端端点全部已存在且已被对应后端 spec 覆盖,本 change **不改后端行为、不动数据库 schema**,纯前端补完。

## Capabilities

### New Capabilities
- `user-admin-ui`: 管理 SPA 的用户管理域前端能力基线——含服务主体创建入口、IM 身份单一管理面(整合新建+生命周期)、渠道身份手动绑定/解绑入口。补齐 `*-admin-ui` 既有模式中缺失的用户域。
- `audit-admin-ui`: 管理 SPA 的审计日志查看器——按 actor/action/target/时间检索与导出,对接 `platform-audit-log` 已定义的可检索/可导出后端行为。

### Modified Capabilities
<!-- 无。后端行为(web-user-management / im-user-mapping / agent-service-principal / platform-audit-log)的 requirement 不变;被移除的 /im-identities 前端路由从未进入任何 spec,故不构成 spec 级修改。 -->

## Impact

- **owning package**: `frontend/`(React + Vite SPA)。改动集中在 `frontend/src/features/users/`(page.tsx / api.ts 扩展)、新增 `frontend/src/features/audit/`;**删除** `frontend/src/features/im-identities/`;调整 `frontend/src/app/routes.tsx` 与 `nav.ts`。
- **public API surface**: 无新增。仅消费既有 `/admin/*` 端点(service-principals / link / audit / im-users)。
- **owned tables**: 无(纯前端)。
- **config namespace**: 无。
- **cross-module dependencies**: 前端 → platform admin API(HTTP),方向不变;不引入新后端依赖。
- **migration / shim plan**: 移除 `/im-identities` 路由 + 导航项;无数据迁移。i18n 文案随各域新增。
- **测试**:前端测试栈(参见 `admin-frontend-spa` 的 TDD 纪律要求),组件/数据层测试覆盖新增对话框、合并后的 IM 面、审计检索;后端无新增测试。
