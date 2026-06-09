## 1. 容器文件 IO helper + 路径解析

- [x] 1.1 Write failing unit tests: `resolve_ws_path`（相对路径相对 `/workspace`、绝对路径越界拒绝、`..` 规范化后越界拒绝、`/workspace-evil` 前缀 lookalike 拒绝）；helper 命令组装（cat/wc/ls）（tests/unit）
- [x] 1.2 Implement `tools/file_sandbox_io.py` helper（resolve_ws_path 边界校验 + build_read/size/list_command），pass unit tests

## 2. sandbox 可用性探测 + 降级路径围栏

- [x] 2.1 Write failing unit tests: sandbox 可用→走容器后端；不可用→宿主后端且路径经 `normpath`+workspace 根前缀判定限制、越界拒绝（tests/unit，mock 可用性）
- [x] 2.2 Implement 可用性探测 + 容器/宿主双后端选择，pass unit tests

## 3. read_file 走容器（保留分页/二进制/目录）

- [x] 3.1 Write failing unit tests: read_file 经 helper 读 workspace 文件、行级分页、目录列举、二进制检测拒绝；越界路径拒绝（tests/unit，mock client）
- [x] 3.2 Implement read_file 改造（容器 IO + 保留功能逻辑），pass unit tests

## 4. write_file 走容器

- [x] 4.1 Write failing unit tests: write_file 经 helper 把内容经 stdin 写入 workspace；越界路径拒绝（tests/unit）
- [x] 4.2 Implement write_file 改造，pass unit tests

## 5. edit_file 走容器（保留 6 层 fallback）

- [x] 5.1 Write failing unit tests: edit_file 容器读内容→宿主 6 层 match→容器写回；保留命中层名、no-op 防护、未找到错误；越界拒绝（tests/unit）
- [x] 5.2 Implement edit_file 改造，pass unit tests

## 6. search_content / search_files 走容器

- [x] 6.1 Write failing unit tests: search_content（grep/rg 正则）、search_files（find/rg glob）限定在 workspace；越界根路径拒绝（tests/unit）
- [x] 6.2 Implement search 改造，pass unit tests

## 7. 风险定级 + tool_context 贯穿

- [ ] 7.1 Write failing unit tests: read_file/search_content/search_files 为 LOW、write_file/edit_file 为 medium；5 工具接受 tool_context 并据此定位 scope 容器（与 run_code 一致）（tests/unit）
- [ ] 7.2 Implement 风险定级 + tool_context 贯穿，pass unit tests

## 8. integration（真实 docker）

- [ ] 8.1 Write failing integration tests: 文件工具在容器内读写 workspace、越界路径拒绝、workspace 外宿主路径不可达、edit/search 端到端（tests/integration，无 docker 则 skip）
- [ ] 8.2 Implement 直到 integration 通过

## 9. 收尾验证

- [ ] 9.1 解耦验证：file_tools + file_sandbox_io 零 platform import；模块依赖护栏测试通过；无 platform DB 环境下文件工具可用（容器路径 + 降级路径）
- [ ] 9.2 全量收尾：`make test-pr` + ruff format/check + mypy 改动文件 + integration 对照 main 基线无新增失败
