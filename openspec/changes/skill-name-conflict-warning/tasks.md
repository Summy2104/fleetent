## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `scan()` 现以 `_index[name] = (...)` 直接赋值（行 24），同名时 dict 后写覆盖且无报警，覆盖结果取决于遍历顺序
- [ ] 1.2 确认 structlog warning 用法（参照 config.py），定冲突 warning 字段为 `{name, kept_path, dropped_path}`
- [ ] 1.3 确认 name 来源（frontmatter 优先、缺失回落 `skill_md.parent.name`），冲突可由显式同名或同目录名引发

## 2. 冲突检测与报警

- [ ] 2.1 Write failing tests：两个不同路径但同 `name` 的 Skill 经 `scan` 后产生 warning（捕获 structlog/caplog，断言含 name 与两路径）。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：`scan` 写入前检测 name 是否已被本次扫描占用，命中即记结构化 warning。运行 `uv run pytest -x -q` 看到绿

## 3. 确定性选定

- [ ] 3.1 Write failing tests：同名冲突时索引保留「路径字符串排序靠前」者；以两种扫描顺序构造同一对冲突，断言胜出者一致（与到达顺序无关）；三重同名时每次落选各记一条 warning。看到红
- [ ] 3.2 Implement：冲突时按 `SKILL.md` 路径排序选定胜出者写入 `_index`，对每个落选条目记一条 warning。看到绿

## 4. 无冲突回归守卫

- [ ] 4.1 Write tests：所有 name 互异时索引含全部 Skill 且无冲突 warning（回归守卫，确认无冲突行为不变）。看到绿
- [ ] 4.2 确认无需额外实现（无冲突路径不进入冲突分支）

## 5. 收尾

- [ ] 5.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），确认无回归（既有 5 个 skill_registry 测试仍绿）
- [ ] 5.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误
