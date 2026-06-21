> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `yarn --cwd frontend vitest run <file>`。测试先于实现。只动 `features/agents/`(不碰 routes.tsx)。合并由主会话串行做(窗口只实现 + push)。

## 1. 绑定数据层(api.ts,TDD)

- [ ] 1.1 写测试(Vitest+MSW):agent 绑定 hooks——skills(list+toggle)、MCP(bind/unbind,选项 `GET /admin/mcp/servers`)、OAuth(`GET /bindings/oauth`+bind/unbind,选项 `GET /admin/connectors`)、KB(list+bind/unbind)、user 访问(`GET /bindings`+bind/unbind);mutation 后失效对应绑定查询。先见红。
- [ ] 1.2 写测试:IM 访问(群组 `POST /bindings/groups`、`PUT /im-capabilities`)、默认 agent(`PUT/DELETE default`)、secrets(`GET /secrets`、`PUT/DELETE /secrets/{env}`,值只写不反显)。先见红。
- [ ] 1.3 实现 `features/agents/api.ts` 新增上述绑定 hooks(经 `useAdminApi`)。跑 1.1/1.2 见绿。

## 2. 绑定面板(page.tsx,TDD)—— 替换 legacy 深链 aside

- [ ] 2.1 写测试(`page.test.tsx`,MSW):每类绑定面板渲染当前绑定 + add/remove/toggle 调对应端点 + 列表刷新;secrets 值不反显;viewer 隐藏写控件;**断言不再有 `/admin/ui-legacy#` 深链**。用 `within(<section>)` scope 避免同名二义。先见红。
- [ ] 2.2 实现:把 `features/agents/page.tsx` 的「Bindings and legacy entry points」aside 换成原生面板(skills/MCP/OAuth/KB/users/IM 访问/默认/secrets),逐类与 legacy parity。跑 2.1 见绿。

## 3. Change 收尾验证

- [ ] 3.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [ ] 3.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [ ] 3.3 手动核对:agent 详情各绑定原生可管(增删/toggle/IM/默认/secrets),无 legacy 深链;viewer 只读。
