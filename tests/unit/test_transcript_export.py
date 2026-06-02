"""Pure Markdown rendering for session export (任务 5.x)."""

from fleetent.platform.chat_management import transcript_export as te


def test_render_markdown_has_roles_and_content():
    md = te.render_markdown(
        "s1", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
    )
    assert "# Session s1" in md
    assert "**user**" in md and "hi" in md
    assert "**assistant**" in md and "yo" in md


def test_render_markdown_empty_still_has_header():
    assert "# Session s1" in te.render_markdown("s1", [])
