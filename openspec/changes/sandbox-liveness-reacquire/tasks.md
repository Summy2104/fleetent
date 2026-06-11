## 1. acquire 复用前存活校验

- [ ] 1.1 Write failing tests: mock backend 注册表命中但容器已死（liveness 返回 False/inspect 抛失踪）→ acquire 丢弃注册项并新建容器返回新 id；存活时仍复用同一 id（既有语义）。最窄命令见红
- [ ] 1.2 Implement verify-on-reuse：backend 暴露存活检查；`acquire` 注册表命中后校验，死则删项落回收养/新建路径。同一命令见绿

## 2. exec 容器失踪自愈

- [ ] 2.1 Write failing tests: 执行返回 container-missing 类错误 → 注册项被注销且重试一次成功；连续两次失踪 → 返回明确沙箱基础设施错误。最窄命令见红
- [ ] 2.2 Implement deregister + retry-once（识别放 backend 层错误分类，manager 消费）。同一命令见绿

## 3. 文件工具错误诚实化

- [ ] 3.1 Write failing tests: `_ContainerBackend.probe`/`search_files` 在 exec 基础设施失败（非零退出 + 失踪类 stderr）时抛 `_BackendError`（文案含沙箱不可用），不得返回 missing/无匹配；容器内真实缺失路径仍返回「路径不存在」。最窄命令见红
- [ ] 3.2 Implement exec 结果分类：先判基础设施失败再解析 stdout。同一命令见绿

## 4. 收尾

- [ ] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 4.2 Slack 真机复现验证：重装重启 my-bot → ① API 上传 xlsx，bot 能读出内容；② `docker rm -f` 杀掉该会话容器后再次让 bot 读文件，自愈重建并成功读取（事故场景闭环）
