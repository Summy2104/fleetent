# eval_logger.py

## 为什么用 JSONL

每行一个独立 JSON 对象，append-only 写入。崩溃不破坏之前的记录，每行独立可解析，grep 友好。

## 一条 trace 包含什么

ts（时间戳）、input、reply、messages（完整对话历史）、elapsed_s（耗时）、tokens（prompt/completion/total）。

## _serialize 为什么用 hasattr 而不是 isinstance

duck typing：只要对象有 `model_dump()` 就调，不导入 SDK 内部类型，不与具体类绑死。OpenAI SDK 基于 Pydantic，所有响应对象都有 `model_dump()`。换 SDK 不用改这里。

## data/*.jsonl 不入 git

运行时日志不属于代码库：污染 diff、可能泄露对话内容、文件持续增长。`.gitignore` 排除 `data/*.jsonl`。
