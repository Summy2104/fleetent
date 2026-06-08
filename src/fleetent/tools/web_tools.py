"""Web access tools: web_fetch and web_search (SearXNG backend).

web_fetch: HTTP GET with HTML→Markdown/text conversion, 5MB limit.
web_search: SearXNG self-hosted search, availability-gated on SEARXNG_URL.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Literal

import httpx

from fleetent.tools.registry import tool

logger = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB

_BINARY_CONTENT_TYPES = (
    "image/",
    "audio/",
    "video/",
    "application/pdf",
    "application/octet-stream",
    "application/zip",
    "application/x-",
)


def _is_binary_content_type(ct: str) -> bool:
    ct_lower = ct.lower().split(";")[0].strip()
    return any(ct_lower.startswith(b) for b in _BINARY_CONTENT_TYPES)


def _html_to_markdown(html: str) -> str:
    import html2text as h2t

    converter = h2t.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0
    return converter.handle(html)


def _html_to_text(html: str) -> str:
    """Extract plain text from HTML, stripping scripts/styles."""
    import re

    # Remove script and style blocks
    html = re.sub(
        r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    # Strip tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@tool(risk_level="low")
async def web_fetch(
    url: Annotated[str, "要获取的 URL"],
    format: Annotated[
        Literal["markdown", "text", "html"], "返回格式（默认 markdown）"
    ] = "markdown",
    timeout: Annotated[int, "超时秒数（默认 30，最大 120）"] = 30,
) -> str:
    """Fetch a web page and return its content in the specified format.

    HTML is converted to Markdown (default) or plain text. Raw HTML is also
    available. Binary content types (images, PDFs) return an error with a hint.
    Response size is capped at 5 MB.
    """
    timeout_clamped = min(max(timeout, 1), 120)

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_clamped) as client:
        try:
            response = await client.get(
                url,
                headers={"Accept": "text/html,text/plain,*/*", "User-Agent": "fleetent/1.0"},
            )
        except httpx.TimeoutException:
            return f"error: 请求超时（{timeout_clamped}s）: {url}"
        except httpx.RequestError as exc:
            return f"error: 请求失败: {exc}"

    if response.status_code >= 400:
        return f"error: HTTP {response.status_code}: {url}"

    content_type = response.headers.get("content-type", "")
    if _is_binary_content_type(content_type):
        hint = (
            "图片请使用 analyze_image 工具"
            if content_type.startswith("image/")
            else "二进制内容无法作为文本返回"
        )
        return f"error: 内容类型为 {content_type}，{hint}"

    raw = response.content
    if len(raw) > _MAX_RESPONSE_BYTES:
        raw = raw[:_MAX_RESPONSE_BYTES]
        truncated = True
    else:
        truncated = False

    text = raw.decode("utf-8", errors="replace")

    if format == "html":
        result = text
    elif format == "text":
        result = _html_to_text(text) if "html" in content_type.lower() else text
    else:  # markdown (default)
        result = _html_to_markdown(text) if "html" in content_type.lower() else text

    if truncated:
        result += "\n[响应过大，已截断至 5MB]"

    return result


@tool(
    risk_level="low",
    availability=lambda: bool(os.getenv("SEARXNG_URL")),
)
async def web_search(
    query: Annotated[str, "搜索查询词"],
    num_results: Annotated[int, "返回结果数（默认 8，最大 20）"] = 8,
) -> str:
    """Search the web via a self-hosted SearXNG instance (SEARXNG_URL env var).

    Returns a numbered list of results with title, URL, and snippet.
    Only available when SEARXNG_URL is configured.
    """
    searxng_url = os.getenv("SEARXNG_URL", "").rstrip("/")
    if not searxng_url:
        return "error: SEARXNG_URL 未配置"

    n = min(max(num_results, 1), 20)
    params: dict[str, str | int] = {"q": query, "format": "json", "pageno": 1}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(f"{searxng_url}/search", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.RequestError as exc:
            return f"error: SearXNG 搜索失败: {exc}"
        except httpx.HTTPStatusError as exc:
            return f"error: SearXNG 返回 HTTP {exc.response.status_code}"
        except Exception as exc:
            return f"error: SearXNG 响应解析失败: {exc}"

    results = data.get("results", [])[:n]
    if not results:
        return "(无搜索结果)"

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(无标题)")
        url = r.get("url", "")
        snippet = r.get("content", "")
        lines.append(f"{i}. [{title}]({url})")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)
