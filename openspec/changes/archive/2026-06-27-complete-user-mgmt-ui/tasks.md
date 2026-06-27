## 1. 前置勘察（接线前对齐后端真实形状）

- [x] 1.1 读 `src/fleetent/platform/user_management/user_admin_api.py` 的 `/admin/service-principals`(307)、`/admin/link/initiate`(248)、`/admin/link/unlink`(264)、`/admin/audit`(547)、`/admin/im-users/*`、`/admin/im-users/fields`,记录各自请求体/查询参数/响应结构
- [x] 1.2 读 `src/fleetent/platform/im_gateway_management/im_identity_admin_api.py` 的 `POST /admin/im-identities` 请求/响应形状
- [x] 1.3 确认 `GET /admin/audit` 是否原生支持导出(CSV);若不支持,记录"前端基于结果生成 CSV"为实现路径（回填 design Open Question）

## 2. IM 身份管理合并为单一面（user-admin-ui）

- [x] 2.1 写测试（红）：用户页 "IM Identities" 标签内新建映射的组件/数据层测试——提交调用 `POST /admin/im-identities` 并刷新列表
- [x] 2.2 实现（绿）：把 `im-identities/` 的新建映射对话框迁入 `users/page.tsx` 的 IM 标签，复用 `users/api.ts` 的 React Query mutation 模式
- [x] 2.3 写测试（红）：接通编辑元数据(`PATCH /admin/im-users/{id}`)、删除(`DELETE`)、字段定义(`GET /admin/im-users/fields`)的行级操作测试
- [x] 2.4 实现（绿）：在 `ImUserRow` 行级菜单补齐编辑元数据 / 删除；用 `/admin/im-users/fields` 渲染可编辑字段
- [x] 2.5 删除 `frontend/src/features/im-identities/` 目录，摘除 `routes.tsx` 的 `/im-identities` 路由与 `nav.ts` 的导航项
- [x] 2.6 补 i18n 文案；跑受影响前端测试，确认 IM 合并面无新增失败

## 3. 服务主体创建 UI（user-admin-ui）

- [x] 3.1 写测试（红）：`CreateServicePrincipalDialog` 提交调用 `POST /admin/service-principals`，成功后展示一次性 `ma-` 凭证；失败保留表单并报错
- [x] 3.2 实现（绿）：新增 `CreateServicePrincipalDialog`（参照 `CreateUserDialog`），成功后复用 `KeysDialog` 的一次性凭证展示+复制
- [x] 3.3 在用户管理面挂入"创建服务主体"入口按钮；补 i18n；跑受影响测试

## 4. 渠道身份绑定/解绑 UI（user-admin-ui）

- [x] 4.1 写测试（红）：发起绑定调用 `POST /admin/link/initiate` 并展示一次性 code + TTL；解绑调用 `POST /admin/link/unlink` 并刷新
- [x] 4.2 实现（绿）：在用户行级操作新增绑定/解绑入口与 code/TTL 提示弹窗，接 `users/api.ts` 新增 mutation
- [x] 4.3 补 i18n；跑受影响测试

## 5. 审计日志查看器（audit-admin-ui）

- [x] 5.1 写测试（红）：审计页面按 actor/action/target/时间范围检索调用 `GET /admin/audit` 并渲染结果；空态提示；导出当前过滤视图
- [x] 5.2 实现（绿）：新增 `frontend/src/features/audit/`（page.tsx + api.ts），实现检索表单、结果表格、空态、导出（依 1.3 结论：后端导出或前端从结果生成 CSV）
- [x] 5.3 注册 `routes.tsx` 路由与 `nav.ts` 导航项；补 i18n
- [x] 5.4 跑受影响测试，确认审计域无新增失败

## 6. change 收尾

- [x] 6.1 跑前端测试栈全绿（`make test-frontend`）
- [x] 6.2 本 change 纯前端，按执行指令不跑 `make test-pr` / integration；前端 CI 门禁以 `make test-frontend` 为准
- [x] 6.3 `make frontend-build` 确认 SPA 静态构建产物正常生成（`frontend/dist/`）
- [x] 6.4 自动化覆盖：服务主体创建、IM 单面生命周期、link 绑定/解绑、审计检索与导出；本轮未做浏览器人工走查
