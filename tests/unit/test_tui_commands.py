"""Slash-command parsing + completer (tui-gateway 8.1)."""

from prompt_toolkit.document import Document

from fleetent.tui import commands as c


def test_parse_plain_text_is_not_a_command():
    assert c.parse_command("hello there") is None


def test_parse_simple_commands():
    assert c.parse_command("/new") == c.Command("new", [])
    assert c.parse_command("/quit") == c.Command("quit", [])
    assert c.parse_command("/help") == c.Command("help", [])


def test_parse_command_with_args():
    assert c.parse_command("/abort r123") == c.Command("abort", ["r123"])
    assert c.parse_command("/approve a1 approved") == c.Command("approve", ["a1", "approved"])
    assert c.parse_command("/session list") == c.Command("session", ["list"])


def test_parse_strips_and_handles_extra_whitespace():
    assert c.parse_command("  /abort   r9  ") == c.Command("abort", ["r9"])


def test_unknown_command_parses_but_is_not_known():
    cmd = c.parse_command("/frobnicate x")
    assert cmd == c.Command("frobnicate", ["x"])
    assert "frobnicate" not in c.KNOWN_COMMANDS
    assert "abort" in c.KNOWN_COMMANDS


def test_completer_lists_all_commands_on_slash():
    completer = c.SlashCommandCompleter()
    comps = list(completer.get_completions(Document("/"), None))
    texts = {comp.text for comp in comps}
    assert {"new", "session", "abort", "approve", "quit", "help"} <= texts


def test_completer_filters_by_prefix():
    completer = c.SlashCommandCompleter()
    comps = list(completer.get_completions(Document("/ap"), None))
    assert {comp.text for comp in comps} == {"approve"}


def test_completer_silent_for_non_slash():
    completer = c.SlashCommandCompleter()
    assert list(completer.get_completions(Document("hello"), None)) == []
