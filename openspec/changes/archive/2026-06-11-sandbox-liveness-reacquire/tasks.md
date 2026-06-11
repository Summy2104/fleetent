## 1. acquire 复用前存活校验

- [x] 1.1 Write failing tests: mock backend 注册表命中但容器已死（liveness 返回 False/inspect 抛失踪）→ acquire 丢弃注册项并新建容器返回新 id；存活时仍复用同一 id（既有语义）。最窄命令见红
- [x] 1.2 Implement verify-on-reuse：backend 暴露存活检查；`acquire` 注册表命中后校验，死则删项落回收养/新建路径。同一命令见绿

## 2. exec 容器失踪自愈

- [x] 2.1 Write failing tests: 执行返回 container-missing 类错误 → 注册项被注销且重试一次成功；连续两次失踪 → 返回明确沙箱基础设施错误。最窄命令见红
- [x] 2.2 Implement deregister + retry-once（识别放 backend 层错误分类，manager 消费）。同一命令见绿

## 3. 文件工具错误诚实化

- [x] 3.1 Write failing tests: `_ContainerBackend.probe`/`search_files` 在 exec 基础设施失败（非零退出 + 失踪类 stderr）时抛 `_BackendError`（文案含沙箱不可用），不得返回 missing/无匹配；容器内真实缺失路径仍返回「路径不存在」。最窄命令见红
- [x] 3.2 Implement exec 结果分类：先判基础设施失败再解析 stdout。同一命令见绿

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [x] 4.2 Slack 真机复现验证 —— **用户豁免**（2026-06-11 决定：开发完成后直接归档合并，跳过真机验证；单元/集成层已覆盖事故场景）
