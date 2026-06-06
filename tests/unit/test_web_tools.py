"""Tests for web_fetch and web_search (builtin-web-tools spec)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleetent.tools.web_tools import web_fetch, web_search
from fleetent.tools import registry as tr


# ── web_fetch ─────────────────────────────────────────────────────────────────


async def test_web_fetch_returns_markdown_by_default(respx_mock):
    import httpx
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(
            200,
            content=b"<html><body><h1>Hello</h1><p>World</p></body></html>",
            headers={"content-type": "text/html"},
        )
    )
    result = await web_fetch("https://example.com")
    assert "Hello" in result
    assert "<h1>" not in result  # converted to markdown, no raw HTML tags


async def test_web_fetch_text_format_strips_html(respx_mock):
    import httpx
    respx_mock.get("https://example.com/page").mock(
        return_value=httpx.Response(
            200,
            content=b"<html><body><p>Plain text</p><script>bad()</script></body></html>",
            headers={"content-type": "text/html"},
        )
    )
    result = await web_fetch("https://example.com/page", format="text")
    assert "Plain text" in result
    assert "bad()" not in result
    assert "<" not in result


async def test_web_fetch_html_format_returns_raw(respx_mock):
    import httpx
    raw_html = b"<html><body><p>Hi</p></body></html>"
    respx_mock.get("https://example.com/raw").mock(
        return_value=httpx.Response(
            200,
            content=raw_html,
            headers={"content-type": "text/html"},
        )
    )
    result = await web_fetch("https://example.com/raw", format="html")
    assert "<html>" in result or "<p>" in result


async def test_web_fetch_binary_content_type_returns_error(respx_mock):
    import httpx
    respx_mock.get("https://example.com/img.png").mock(
        return_value=httpx.Response(
            200,
            content=b"\x89PNG\r\n",
            headers={"content-type": "image/png"},
        )
    )
    result = await web_fetch("https://example.com/img.png")
    assert "error" in result.lower()
    assert "image/png" in result


async def test_web_fetch_timeout_returns_error(respx_mock):
    import httpx
    respx_mock.get("https://slow.example.com").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    result = await web_fetch("https://slow.example.com", timeout=1)
    assert "error" in result.lower()
    assert "超时" in result or "timeout" in result.lower()


async def test_web_fetch_5mb_size_limit(respx_mock):
    import httpx
    big_content = b"x" * (6 * 1024 * 1024)  # 6MB > 5MB limit
    respx_mock.get("https://big.example.com").mock(
        return_value=httpx.Response(
            200,
            content=big_content,
            headers={"content-type": "text/plain"},
        )
    )
    result = await web_fetch("https://big.example.com", format="text")
    assert "截断" in result or len(result.encode()) <= 5 * 1024 * 1024 + 200


async def test_web_fetch_http_error_returns_error(respx_mock):
    import httpx
    respx_mock.get("https://example.com/404").mock(
        return_value=httpx.Response(404, content=b"Not Found")
    )
    result = await web_fetch("https://example.com/404")
    assert "error" in result.lower() or "404" in result


# ── web_search ────────────────────────────────────────────────────────────────


def test_web_search_not_in_schema_without_searxng_url(monkeypatch):
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    names = [s["function"]["name"] for s in tr.get_schemas()]
    assert "web_search" not in names


def test_web_search_in_schema_with_searxng_url(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8888")
    names = [s["function"]["name"] for s in tr.get_schemas()]
    assert "web_search" in names


async def test_web_search_returns_results(monkeypatch, respx_mock):
    import httpx
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.local")
    payload = {
        "results": [
            {"title": "Result 1", "url": "https://r1.com", "content": "snippet 1"},
            {"title": "Result 2", "url": "https://r2.com", "content": "snippet 2"},
        ]
    }
    respx_mock.get("http://searxng.local/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await web_search("python asyncio")
    assert "Result 1" in result
    assert "https://r1.com" in result
    assert "snippet 1" in result


async def test_web_search_num_results_param(monkeypatch, respx_mock):
    import httpx
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.local")
    payload = {"results": [{"title": f"R{i}", "url": f"http://r{i}.com", "content": f"s{i}"} for i in range(10)]}
    respx_mock.get("http://searxng.local/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await web_search("query", num_results=3)
    # Should only show 3 results
    assert result.count("http://r") == 3


async def test_web_search_error_on_unreachable(monkeypatch, respx_mock):
    import httpx
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.local")
    respx_mock.get("http://searxng.local/search").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    result = await web_search("test")
    assert "error" in result.lower()
