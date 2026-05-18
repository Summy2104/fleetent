# User Store Design

## 职责

管理用户账号和 API key 认证。是 API 层的依赖，不渗透进 agent_loop 内部。

## 两种 API key 的区别

| | 模型 API key | 用户 API key |
|--|-------------|-------------|
| 示例 | `ANTHROPIC_API_KEY` | `ma-<token>` |
| 用途 | mini-agent 调用 LLM 提供商 | 外部客户端调用 mini-agent 服务 |
| 存储 | 环境变量 | `data/users.db` |
| 管理方 | Anthropic/OpenAI | user_store.py |

## 数据模型

单张表，SQLite 存储于 `data/users.db`：

```sql
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,    -- uuid4
    name       TEXT NOT NULL,
    api_key    TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);
```

## API key 格式

`ma-<secrets.token_hex(32)>`（64 位随机 hex，`ma-` 前缀标识来源）

## 模块接口

```python
def create_user(name: str) -> User:
    """Create user with generated uuid and api_key."""

def get_by_api_key(api_key: str) -> User | None:
    """Look up user by api_key. Used by API layer for auth."""

def get_by_id(user_id: str) -> User | None:
    """Look up user by id."""
```

## 和其他模块的关系

```
POST /chat (Authorization: Bearer ma-xxx)
  → user_store.get_by_api_key("ma-xxx") → user_id
  → agent_loop.run(user_input, user_id=user_id)
      → memory_layer  用 user_id 隔离记忆文件
      → user_grant    用 user_id 隔离 OAuth token
```

API 层提取 user_id 后作为参数往下传，user_store 不感知 agent_loop 内部。

## 生产升级路径

| 项目 | 现在 | 生产 |
|------|------|------|
| 存储 | SQLite | PostgreSQL（换连接串） |
| api_key 存储 | 明文 | `hashlib.sha256(key).hexdigest()` |
| 连接池 | 无 | asyncpg + pool |
| 迁移工具 | 无 | Alembic |
| 多租户 | 无 | 加 `tenant_id` 列 |

接口不变，只换后端实现。
