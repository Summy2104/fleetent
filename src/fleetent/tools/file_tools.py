"""File operation built-in tools: read_file, write_file, edit_file, search_content, search_files."""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fleetent.integrations.sandbox.enablement import Mode, get_effective_mode
from fleetent.tools import file_sandbox_io as fsio
from fleetent.tools.registry import ToolContext, tool

if TYPE_CHECKING:
    from fleetent.integrations.sandbox.client import ExecResult, SandboxClient
    from fleetent.integrations.sandbox.manager import SandboxManager

logger = logging.getLogger(__name__)

# ── constants (injectable for tests) ─────────────────────────────────────────

READ_DEFAULT_LIMIT = 200
DIR_MAX_ENTRIES = 200

# Binary detection: non-printable byte ratio threshold (sample first 512 bytes)
_BINARY_SAMPLE = 512
_BINARY_RATIO = 0.30

# Common binary magic byte signatures
_MAGIC_SIGNATURES: list[bytes] = [
    b"\x89PNG",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF8",  # GIF
    b"GIF9",  # GIF
    b"%PDF",  # PDF
    b"PK\x03\x04",  # ZIP / DOCX / XLSX / JAR
    b"\x7fELF",  # ELF binary
    b"MZ",  # Windows PE
    b"\x1f\x8b",  # gzip
    b"BZh",  # bzip2
    b"\xfd7zXZ",  # xz
    b"RIFF",  # WAV/AVI
    b"\x00\x00\x00",  # various binary formats
    b"\xca\xfe\xba\xbe",  # Java class
    b"\xfe\xed\xfa",  # Mach-O
]

_MAGIC_DESCRIPTIONS: dict[bytes, str] = {
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF8": "image/gif",
    b"GIF9": "image/gif",
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/zip",
    b"\x7fELF": "application/elf",
    b"MZ": "application/exe",
    b"\x1f\x8b": "application/gzip",
    b"BZh": "application/bzip2",
    b"\xfd7zXZ": "application/xz",
    b"RIFF": "audio/video",
    b"\xca\xfe\xba\xbe": "application/java-class",
    b"\xfe\xed\xfa": "application/mach-o",
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _detect_binary_bytes(sample: bytes) -> str | None:
    """Return MIME-like type string if the byte sample looks binary, else None."""
    for magic in _MAGIC_SIGNATURES:
        if sample.startswith(magic):
            return _MAGIC_DESCRIPTIONS.get(magic, "application/binary")

    if len(sample) == 0:
        return None

    non_printable = sum(
        1
        for b in sample
        if b < 32 and b not in (9, 10, 13)  # tab, LF, CR are OK
    )
    if non_printable / len(sample) > _BINARY_RATIO:
        return "application/binary"

    return None


def _detect_binary(path: Path) -> str | None:
    """Return MIME-like type string if binary, None if text (host-path overload)."""
    try:
        sample = path.read_bytes()[:_BINARY_SAMPLE]
    except OSError:
        return None
    return _detect_binary_bytes(sample)


def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size}{unit}"
        size //= 1024
    return f"{size}TB"


def _format_dir_listing(path: str, entries: list[_DirEntry]) -> str:
    """Format a directory listing (mtime-sorted, sizes), backend-agnostic."""
    entries = sorted(entries, key=lambda e: e.mtime, reverse=True)
    total = len(entries)
    truncated = total > DIR_MAX_ENTRIES
    visible = entries[:DIR_MAX_ENTRIES]

    suffix = (
        f"（共 {total} 项，已截断至前 {DIR_MAX_ENTRIES} 条）" if truncated else f"（共 {total} 项）"
    )
    lines = [f"{path}/ {suffix}"]
    for entry in visible:
        size = "dir" if entry.is_dir else _format_size(entry.size)
        indicator = "/" if entry.is_dir else ""
        lines.append(f"  {entry.name}{indicator}  {size}")

    if truncated:
        lines.append(f"\n[截断：共 {total} 条，仅显示前 {DIR_MAX_ENTRIES} 条]")

    return "\n".join(lines)


# ── sandbox backend selection ─────────────────────────────────────────────────

# Default scope key when a tool is called without a ToolContext (direct/unbound
# call) — mirrors run_code's "run-code" fallback so both share a coherent default.
_DEFAULT_KEY = "file-tools"


class _BackendError(Exception):
    """A backend IO command failed (non-zero exit / unreadable path)."""


@dataclass
class _Stat:
    kind: str  # "file" | "dir" | "missing" | "other"
    size: int = 0


@dataclass
class _DirEntry:
    name: str
    is_dir: bool
    size: int
    mtime: float


def _parse_probe(stdout: str) -> _Stat:
    head = stdout.strip()
    if head.startswith("file"):
        parts = head.split()
        size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return _Stat("file", size)
    if head == "dir":
        return _Stat("dir")
    if head == "other":
        return _Stat("other")
    return _Stat("missing")


def _parse_listdir(stdout: str) -> list[_DirEntry]:
    entries: list[_DirEntry] = []
    for line in stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        name, kind, size, mtime = parts
        entries.append(
            _DirEntry(
                name=name,
                is_dir=kind == "d",
                size=int(size) if size.isdigit() else 0,
                mtime=float(mtime) if mtime else 0.0,
            )
        )
    return entries


def _get_sandbox_manager() -> SandboxManager:
    """Return the process-wide SandboxManager, shared with run_code.

    Imported lazily to avoid the import cycle (builtin_tools imports this module to
    re-export read_file/write_file). Sharing run_code's manager means the file tools
    reuse the same per-session container/registry instead of booting their own.
    """
    from fleetent.tools.builtin_tools import _get_manager

    return _get_manager()


@dataclass
class _ContainerBackend:
    """File IO executed inside the sandbox container, locked to ``/workspace``."""

    client: SandboxClient
    ws_id: str
    session_id: str

    async def _exec(self, command: str) -> ExecResult:
        return await self.client.exec(self.ws_id, command, session_id=self.session_id)

    async def probe(self, path: str) -> _Stat:
        rp = fsio.resolve_ws_path(path)
        res = await self._exec(fsio.build_probe_command(rp))
        return _parse_probe(res.stdout)

    async def read_bytes(self, path: str) -> bytes:
        rp = fsio.resolve_ws_path(path)
        res = await self._exec(fsio.build_read_b64_command(rp))
        if res.exit_code != 0:
            raise _BackendError(res.stderr.strip() or "读取文件失败")
        try:
            return base64.b64decode(res.stdout)
        except ValueError as exc:  # binascii.Error is a ValueError subclass
            raise _BackendError(f"解码失败: {exc}") from exc

    async def list_dir(self, path: str) -> list[_DirEntry]:
        rp = fsio.resolve_ws_path(path)
        res = await self._exec(fsio.build_listdir_command(rp))
        return _parse_listdir(res.stdout)

    async def write_bytes(self, path: str, data: bytes) -> None:
        rp = fsio.resolve_ws_path(path)
        res = await self.client.exec(
            self.ws_id, fsio.build_write_command(rp), session_id=self.session_id, stdin=data
        )
        if res.exit_code != 0:
            raise _BackendError(res.stderr.strip() or "写入文件失败")


@dataclass
class _HostBackend:
    """File IO on the host (docker-unavailable degrade), fenced to ``root``."""

    root: Path

    def _resolve(self, path: str) -> Path:
        return fsio.resolve_host_path(self.root, path)

    async def probe(self, path: str) -> _Stat:
        p = self._resolve(path)
        if p.is_dir():
            return _Stat("dir")
        if p.is_file():
            return _Stat("file", p.stat().st_size)
        if p.exists():
            return _Stat("other")
        return _Stat("missing")

    async def read_bytes(self, path: str) -> bytes:
        try:
            return self._resolve(path).read_bytes()
        except OSError as exc:
            raise _BackendError(str(exc)) from exc

    async def list_dir(self, path: str) -> list[_DirEntry]:
        p = self._resolve(path)
        entries: list[_DirEntry] = []
        try:
            children = list(p.iterdir())
        except OSError as exc:
            raise _BackendError(str(exc)) from exc
        for child in children:
            try:
                st = child.stat()
                entries.append(_DirEntry(child.name, child.is_dir(), st.st_size, st.st_mtime))
            except OSError:
                entries.append(_DirEntry(child.name, False, 0, 0.0))
        return entries

    async def write_bytes(self, path: str, data: bytes) -> None:
        p = self._resolve(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        except OSError as exc:
            raise _BackendError(str(exc)) from exc


async def _select_backend(tool_context: ToolContext | None) -> _ContainerBackend | _HostBackend:
    """Pick the container backend when the sandbox is usable, else the host fence.

    Container is the structural-defense path (mount namespace makes workspace-external
    host paths physically unreachable). When docker is unavailable the effective mode
    degrades to OFF; we then operate on the same host workspace dir behind a normpath
    path fence (no namespace — the documented degrade).
    """
    session_id = (
        tool_context.session_id if tool_context and tool_context.session_id else _DEFAULT_KEY
    )
    agent_name = (tool_context.agent_name if tool_context else None) or "default"
    manager = _get_sandbox_manager()
    mode = await get_effective_mode()
    if mode is Mode.OFF:
        root = manager.workspace_host_path(manager.scope, session_id, agent_name)
        return _HostBackend(root=root)
    from fleetent.integrations.sandbox import build_sandbox_env

    features = tool_context.features if tool_context else {}
    env = build_sandbox_env(agent_env=features.get("sandbox_env"))
    ws_id = await manager.acquire(manager.scope, session_id, agent_name, env=env)
    return _ContainerBackend(client=manager.client, ws_id=ws_id, session_id=session_id)


# ── tools ─────────────────────────────────────────────────────────────────────


@tool
async def read_file(
    path: Annotated[str, "文件或目录的路径（限定在 workspace 内）"],
    offset: Annotated[int, "起始行号（1-indexed，默认 1）"] = 1,
    limit: Annotated[int, "最大读取行数（默认 200）"] = READ_DEFAULT_LIMIT,
    tool_context: ToolContext | None = None,
) -> str:
    """Read a file with line-level pagination, or list a directory.

    Runs inside the sandbox container locked to the workspace (host degrade fenced to
    the same dir when docker is unavailable). For files: returns lines [offset,
    offset+limit) with line-number prefixes. For directories: a listing sorted by
    mtime (newest first). Binary files are detected and rejected.
    """
    backend = await _select_backend(tool_context)
    try:
        stat = await backend.probe(path)
    except ValueError as exc:  # path escapes the workspace
        return f"error: {exc}"
    except _BackendError as exc:
        return f"error: {exc}"

    if stat.kind == "missing":
        return f"error: 路径不存在: {path}"

    if stat.kind == "dir":
        try:
            entries = await backend.list_dir(path)
        except _BackendError as exc:
            return f"error: {exc}"
        return _format_dir_listing(path, entries)

    try:
        data = await backend.read_bytes(path)
    except _BackendError as exc:
        return f"error: {exc}"

    binary_type = _detect_binary_bytes(data[:_BINARY_SAMPLE])
    if binary_type is not None:
        hint = (
            "图片请使用 analyze_image 工具"
            if binary_type.startswith("image")
            else "无法作为文本读取"
        )
        return f"error: 二进制文件 ({binary_type})，{hint}"

    all_lines = data.decode("utf-8", errors="replace").splitlines()

    total = len(all_lines)
    start = max(0, offset - 1)  # convert 1-indexed to 0-indexed
    end = start + limit
    page = all_lines[start:end]

    width = len(str(total))
    numbered = [f"{start + i + 1:{width}d} | {line}" for i, line in enumerate(page)]
    result = "\n".join(numbered)

    if end < total:
        next_offset = end + 1
        result += (
            f"\n\n[第 {offset}–{end} 行，共 {total} 行。"
            f"继续：read_file(path='{path}', offset={next_offset})]"
        )

    return result


@tool(risk_level="medium")
async def write_file(
    path: Annotated[str, "目标文件路径（限定在 workspace 内）"],
    content: Annotated[str, "写入的完整内容"],
    tool_context: ToolContext | None = None,
) -> str:
    """Write content to a workspace file (full overwrite). Requires approval.

    Runs inside the sandbox container (content streamed over stdin) or the host fence
    when docker is unavailable; the path is locked to the workspace.
    """
    backend = await _select_backend(tool_context)
    data = content.encode("utf-8")
    try:
        await backend.write_bytes(path, data)
    except ValueError as exc:  # path escapes the workspace
        return f"error: {exc}"
    except _BackendError as exc:
        return f"error: {exc}"
    return f"written {len(content)} bytes to {path}"


# ── edit_file: 6-layer fallback matcher ───────────────────────────────────────


def _exact_replace(text: str, old: str, new: str, replace_all: bool) -> str | None:
    if old not in text:
        return None
    return text.replace(old, new) if replace_all else text.replace(old, new, 1)


def _line_trimmed_replace(text: str, old: str, new: str, replace_all: bool) -> str | None:
    """Layer 2: match after stripping each line."""
    old_stripped = "\n".join(line.rstrip() for line in old.splitlines())
    # Build stripped version for matching
    stripped_text = "\n".join(line.rstrip() for line in text.splitlines())
    if old_stripped not in stripped_text:
        return None
    # Find the actual span in original text
    # Map stripped positions back to original — simpler: re-do with line alignment
    old_lines = old.splitlines()
    text_lines = text.splitlines()
    for i in range(len(text_lines) - len(old_lines) + 1):
        chunk = text_lines[i : i + len(old_lines)]
        if all(a.rstrip() == b.rstrip() for a, b in zip(chunk, old_lines, strict=True)):
            new_lines = new.splitlines()
            replaced = text_lines[:i] + new_lines + text_lines[i + len(old_lines) :]
            result = "\n".join(replaced)
            if text.endswith("\n"):
                result += "\n"
            if not replace_all:
                return result
            # For replace_all: continue finding more occurrences
            # Simple approach: recurse on remainder
            return result
    return None


def _ws_normalized(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s)


def _whitespace_normalized_replace(text: str, old: str, new: str, replace_all: bool) -> str | None:
    """Layer 3: treat consecutive whitespace as equivalent."""
    old_norm = _ws_normalized(old)
    text_norm = _ws_normalized(text)
    if old_norm not in text_norm:
        return None
    idx = text_norm.index(old_norm)
    # Map normalized index back to original by counting chars
    return text[:idx] + new + text[idx + len(old) :]


def _line_ending_normalize(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _line_ending_replace(text: str, old: str, new: str, replace_all: bool) -> str | None:
    """Layer 4: normalize CRLF/CR to LF before matching."""
    text_n = _line_ending_normalize(text)
    old_n = _line_ending_normalize(old)
    if old_n not in text_n:
        return None
    result = text_n.replace(old_n, new, 1 if not replace_all else -1)
    return result


def _remove_common_indent(s: str) -> str:
    lines = s.splitlines()
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return s
    indent = min(len(line) - len(line.lstrip()) for line in non_empty)
    return "\n".join(line[indent:] if len(line) > indent else line for line in lines)


def _indentation_flexible_replace(text: str, old: str, new: str, replace_all: bool) -> str | None:
    """Layer 5: remove common indentation before matching."""
    old_stripped = _remove_common_indent(old)
    text_stripped = _remove_common_indent(text)
    if old_stripped not in text_stripped:
        return None
    idx = text_stripped.index(old_stripped)
    return text[:idx] + new + text[idx + len(old_stripped) :]


def _context_aware_replace(text: str, old: str, new: str, replace_all: bool) -> str | None:
    """Layer 6: anchor on first+last line, match middle lines by strip comparison."""
    old_lines = old.splitlines()
    if len(old_lines) < 2:
        return None
    text_lines = text.splitlines()
    first = old_lines[0].strip()
    last = old_lines[-1].strip()

    for i in range(len(text_lines) - len(old_lines) + 1):
        chunk = text_lines[i : i + len(old_lines)]
        if chunk[0].strip() != first or chunk[-1].strip() != last:
            continue
        if all(a.strip() == b.strip() for a, b in zip(chunk[1:-1], old_lines[1:-1], strict=True)):
            new_lines = new.splitlines()
            replaced = text_lines[:i] + new_lines + text_lines[i + len(old_lines) :]
            result = "\n".join(replaced)
            if text.endswith("\n"):
                result += "\n"
            return result
    return None


_LAYERS = [
    ("ExactReplacer", _exact_replace),
    ("LineTrimmedReplacer", _line_trimmed_replace),
    ("WhitespaceNormalizedReplacer", _whitespace_normalized_replace),
    ("LineEndingNormalizedReplacer", _line_ending_replace),
    ("IndentationFlexibleReplacer", _indentation_flexible_replace),
    ("ContextAwareReplacer", _context_aware_replace),
]


def _find_line_number(text: str, old: str) -> int:
    """Return 1-indexed line number of old_string in text, or 0 if not found."""
    idx = text.find(old)
    if idx == -1:
        return 0
    return text[:idx].count("\n") + 1


@tool(risk_level="medium")
def edit_file(
    path: Annotated[str, "目标文件路径"],
    old_string: Annotated[str, "要替换的原始字符串（必须在文件中存在）"],
    new_string: Annotated[str, "替换后的新字符串"],
    replace_all: Annotated[bool, "是否替换所有匹配（默认 False 只替换第一处）"] = False,
) -> str:
    """Replace old_string with new_string in a file using 6-layer fallback matching.

    Tries exact match first, then progressively more flexible strategies (line
    trim, whitespace normalization, line-ending normalization, indentation
    normalization, context-aware anchor matching). Returns which layer matched.
    """
    p = Path(path)
    if not p.exists():
        return f"error: 文件不存在: {path}"

    try:
        original = p.read_text(encoding="utf-8")
    except OSError as exc:
        return f"error: 读取文件失败: {exc}"

    # No-op guard
    if old_string.strip() == new_string.strip() and old_string == new_string:
        return "no-op: old_string 与 new_string 内容相同，文件未修改"

    for layer_name, layer_fn in _LAYERS:
        result = layer_fn(original, old_string, new_string, replace_all)
        if result is not None and result != original:
            line_no = _find_line_number(original, old_string)
            try:
                p.write_text(result, encoding="utf-8")
            except OSError as exc:
                return f"error: 写入文件失败: {exc}"
            loc = f"第 {line_no} 行附近" if line_no > 0 else "文件中"
            return f"替换成功（{loc}，使用 {layer_name}）"

    return (
        f"error: 无法在文件中找到匹配的 old_string\n"
        f"尝试了 {len(_LAYERS)} 种匹配策略均失败\n"
        f"建议：先用 read_file(path='{path}') 读取该段代码，确认实际内容后重试"
    )


# ── search_content (grep) ─────────────────────────────────────────────────────

_RG_BIN = shutil.which("rg")


@tool
def search_content(
    pattern: Annotated[str, "正则表达式搜索模式"],
    path: Annotated[str, "搜索目录或文件（默认当前目录）"] = ".",
    include: Annotated[str, "文件 glob 过滤，如 '*.py'（可选）"] = "",
    max_results: Annotated[int, "最大返回条数（默认 100）"] = 100,
) -> str:
    """Search for a regex pattern across files.

    Uses ripgrep when available, falls back to Python regular expressions.
    """
    if _RG_BIN:
        return _rg_search(pattern, path, include, max_results)
    return _py_search(pattern, path, include, max_results)


def _rg_search(pattern: str, path: str, include: str, max_results: int) -> str:
    assert _RG_BIN is not None
    cmd: list[str] = [
        _RG_BIN,
        "--line-number",
        "--no-heading",
        "--color=never",
        pattern,
        path,
    ]
    if include:
        cmd += ["--glob", include]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.splitlines()
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"error: ripgrep 执行失败: {exc}"

    if not lines and result.returncode not in (0, 1):
        return f"error: ripgrep 错误: {result.stderr[:200]}"

    truncated = len(lines) > max_results
    visible = lines[:max_results]
    output = "\n".join(visible)
    if truncated:
        output += f"\n[截断：仅显示前 {max_results} 条，请用 include 参数缩小范围]"
    return output or "(无匹配结果)"


def _py_search(pattern: str, path: str, include: str, max_results: int) -> str:
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"error: 无效正则表达式: {exc}"

    results: list[str] = []
    root = Path(path)
    paths_to_search = [root] if root.is_file() else root.rglob(include or "*")

    for fp in paths_to_search:
        if len(results) >= max_results:
            break
        if not fp.is_file():
            continue
        binary_type = _detect_binary(fp)
        if binary_type:
            continue
        try:
            for lineno, line in enumerate(
                fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if regex.search(line):
                    results.append(f"{fp}:{lineno}:{line}")
                    if len(results) >= max_results:
                        break
        except OSError:
            continue

    if not results:
        return "(无匹配结果)"

    output = "\n".join(results[:max_results])
    if len(results) >= max_results:
        output += f"\n[截断：仅显示前 {max_results} 条，请用 include 参数缩小范围]"
    return output


# ── search_files (glob) ───────────────────────────────────────────────────────


@tool
def search_files(
    pattern: Annotated[str, "glob 模式，如 '**/*.py' 或文件名子串"],
    path: Annotated[str, "搜索根目录（默认当前目录）"] = ".",
    max_results: Annotated[int, "最大返回条数（默认 100）"] = 100,
) -> str:
    """Find files by glob pattern, sorted by modification time (newest first)."""
    if _RG_BIN:
        return _rg_files(pattern, path, max_results)
    return _py_files(pattern, path, max_results)


def _rg_files(pattern: str, path: str, max_results: int) -> str:
    assert _RG_BIN is not None
    cmd: list[str] = [_RG_BIN, "--files", "--glob", pattern, path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        files = result.stdout.splitlines()
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"error: ripgrep 执行失败: {exc}"

    if not files and result.returncode not in (0, 1):
        return f"error: ripgrep 错误: {result.stderr[:200]}"

    # Sort by mtime descending
    def _mtime(p: str) -> float:
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0.0

    files.sort(key=_mtime, reverse=True)
    truncated = len(files) > max_results
    visible = files[:max_results]
    output = "\n".join(visible)
    if truncated:
        output += f"\n[截断：仅显示前 {max_results} 条]"
    return output or "(无匹配文件)"


def _py_files(pattern: str, path: str, max_results: int) -> str:
    root = Path(path)
    try:
        matches = list(root.rglob(pattern))
    except OSError as exc:
        return f"error: {exc}"

    matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    truncated = len(matches) > max_results
    visible = matches[:max_results]
    output = "\n".join(str(p) for p in visible)
    if truncated:
        output += f"\n[截断：仅显示前 {max_results} 条]"
    return output or "(无匹配文件)"
