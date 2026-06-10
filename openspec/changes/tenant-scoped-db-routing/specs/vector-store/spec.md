## MODIFIED Requirements

### Requirement: Namespace helpers
系统 SHALL 提供固定 namespace helper，避免调用方手写 namespace 字符串。namespace 家族（`mem:` / `shared:` / `kb:`）SHALL 由**显式枚举 `VectorFamily`** 定义，并经**单一 `family_of()` 路由入口**判别——禁止 ad-hoc `startswith` 散落各处；未知前缀 SHALL 抛错（fail-fast），不得静默兜底。KB 向量 SHALL 与 KB 关系库经**同一 tenant 作用域**路由到同主体的向量后端。

#### Scenario: Memory namespace
- **WHEN** 调用 `memory_namespace("user-1")`
- **THEN** 返回 `mem:user-1`

#### Scenario: Knowledge namespace
- **WHEN** 调用 `knowledge_namespace("default", "global")`
- **THEN** 返回 `kb:default:global`

#### Scenario: Empty namespace part is invalid
- **WHEN** namespace helper 收到空 user_id、tenant_id 或 kb_id
- **THEN** 系统抛出 `ValueError`

#### Scenario: family_of 显式判别家族
- **WHEN** 用 `family_of()` 判别一个 namespace（如 `kb:default:global`）的家族
- **THEN** 返回对应的 `VectorFamily` 枚举值（`KB`），由该单一入口决定路由

#### Scenario: 未知家族前缀抛错
- **WHEN** `family_of()` 收到不属于任何已知 `VectorFamily` 的前缀
- **THEN** 系统抛错（fail-fast），不静默归入任何后端
