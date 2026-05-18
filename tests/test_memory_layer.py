import json
import pytest
from unittest.mock import MagicMock, patch
from mini_agent import memory_layer


@pytest.fixture(autouse=True)
def patch_mem_path(tmp_path, monkeypatch):
    """Redirect _mem_path to tmp_path so tests don't touch real data/."""
    original = memory_layer._mem_path

    def _patched(user_id: str = "default") -> object:
        return tmp_path / user_id / "memories.jsonl"

    monkeypatch.setattr(memory_layer, "_mem_path", _patched)


def _write_memories(path, facts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for fact in facts:
            f.write(json.dumps({"ts": "2026-01-01T00:00:00Z", "text": fact}) + "\n")


def test_load_memories_empty_when_no_file():
    result = memory_layer.load_memories(user_id="alice")
    assert result == ""


def test_load_memories_returns_formatted_string(tmp_path):
    path = tmp_path / "alice" / "memories.jsonl"
    _write_memories(path, ["Likes Python", "Speaks Chinese"])
    result = memory_layer.load_memories(user_id="alice")
    assert "[Memory]" in result
    assert "Likes Python" in result
    assert "Speaks Chinese" in result


def test_load_memories_truncates_to_n(tmp_path):
    path = tmp_path / "alice" / "memories.jsonl"
    facts = [f"fact {i}" for i in range(30)]
    _write_memories(path, facts)
    result = memory_layer.load_memories(user_id="alice", n=5)
    lines = [l for l in result.splitlines() if l.startswith("- ")]
    assert len(lines) == 5
    assert "fact 29" in result  # last one present
    assert "fact 0" not in result  # earliest truncated


def test_load_memories_skips_malformed_lines(tmp_path):
    path = tmp_path / "alice" / "memories.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("not json\n")
        f.write(json.dumps({"ts": "x", "text": "valid fact"}) + "\n")
        f.write(json.dumps({"ts": "x", "no_text": True}) + "\n")
    result = memory_layer.load_memories(user_id="alice")
    assert "valid fact" in result
    assert "not json" not in result


def test_load_memories_user_id_isolation(tmp_path):
    path_a = tmp_path / "alice" / "memories.jsonl"
    path_b = tmp_path / "bob" / "memories.jsonl"
    _write_memories(path_a, ["Alice memory"])
    _write_memories(path_b, ["Bob memory"])
    assert "Alice memory" in memory_layer.load_memories(user_id="alice")
    assert "Bob memory" not in memory_layer.load_memories(user_id="alice")
    assert "Bob memory" in memory_layer.load_memories(user_id="bob")


def test_extract_and_save_writes_facts(tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = (
        '["User is learning Python", "Prefers short answers"]'
    )
    mock_config = MagicMock()
    mock_config.model = "test-model"
    mock_config.max_tokens = 512

    with patch("mini_agent.memory_layer.get_client_and_config", return_value=(mock_client, mock_config)):
        memory_layer.extract_and_save(
            "how do I learn Python?",
            [{"role": "user", "content": "how do I learn Python?"}],
            user_id="alice",
        )

    result = memory_layer.load_memories(user_id="alice")
    assert "User is learning Python" in result
    assert "Prefers short answers" in result


def test_extract_and_save_handles_empty_list(tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = "[]"
    mock_config = MagicMock()
    mock_config.model = "test-model"
    mock_config.max_tokens = 512

    with patch("mini_agent.memory_layer.get_client_and_config", return_value=(mock_client, mock_config)):
        memory_layer.extract_and_save("hello", [], user_id="alice")

    assert memory_layer.load_memories(user_id="alice") == ""


def test_extract_and_save_handles_malformed_json(tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = "not json"
    mock_config = MagicMock()
    mock_config.model = "test-model"
    mock_config.max_tokens = 512

    with patch("mini_agent.memory_layer.get_client_and_config", return_value=(mock_client, mock_config)):
        memory_layer.extract_and_save("hello", [], user_id="alice")

    assert memory_layer.load_memories(user_id="alice") == ""
