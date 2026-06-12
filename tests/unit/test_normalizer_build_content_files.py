"""_build_user_content injects file references; images and files stay separate."""

from unittest.mock import AsyncMock

import fleetent.tools.builtin_tools as bt
import fleetent.tools.vision_client as vc
from fleetent import paths
from fleetent.im_gateway import normalizer
from fleetent.im_gateway.normalizer import FileAttachment, NormalizedMessage

_SHEET_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _noop(text):
    pass


def _msg(text, attachments):
    return NormalizedMessage(
        platform="slack",
        session_id="s",
        user_id="u",
        text=text,
        attachments=attachments,
        reply_func=_noop,
    )


async def test_success_file_injects_workspace_path(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    fa = FileAttachment(data=b"xlsx-bytes", mime=_SHEET_MIME, filename="data.xlsx")
    content = await normalizer._build_user_content(_msg("总结表格内容", [fa]), "sess1")
    assert "总结表格内容" in content
    assert "data.xlsx" in content
    assert "uploads/data.xlsx" in content
    assert "read_file" in content or "run_code" in content


async def test_failed_file_injects_placeholder(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    fa = FileAttachment(
        data=None, mime="text/csv", filename="big.csv", note="超过大小上限（20 MB）"
    )
    content = await normalizer._build_user_content(_msg("看看", [fa]), "s")
    assert "未能接收" in content
    assert "超过大小上限" in content
    assert "big.csv" in content


async def test_no_attachments_returns_plain_text():
    content = await normalizer._build_user_content(_msg("hello", []), "s")
    assert content == "hello"


async def test_image_and_file_each_own_channel(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    analyze = AsyncMock(return_value="图片分析")
    monkeypatch.setattr(vc, "analyze", analyze)
    monkeypatch.setattr(bt, "_save_upload", lambda data, mime, ctx=None: "uploads/img.png")
    fa = FileAttachment(data=b"csv", mime="text/csv", filename="d.csv")
    content = await normalizer._build_user_content(_msg("处理", [(b"png", "image/png"), fa]), "s")
    assert "[图片 uploads/img.png]" in content
    assert "图片分析" in content
    assert "d.csv" in content
    assert "uploads/d.csv" in content
    analyze.assert_awaited_once()
