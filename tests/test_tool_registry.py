import pytest
from mini_agent import tool_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate each test — snapshot and restore the registry."""
    before = dict(tool_registry._registry)
    yield
    tool_registry._registry.clear()
    tool_registry._registry.update(before)


def test_tool_decorator_registers_function():
    @tool_registry.tool
    def my_tool(x: str) -> str:
        """Do something."""
        return x

    assert "my_tool" in tool_registry._registry


def test_get_schemas_returns_openai_format():
    @tool_registry.tool
    def greet(name: str) -> str:
        """Greet someone."""
        return f"hello {name}"

    schemas = tool_registry.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "greet" in names
    schema = next(s for s in schemas if s["function"]["name"] == "greet")
    assert schema["type"] == "function"
    assert "parameters" in schema["function"]
    assert "name" in schema["function"]["parameters"]["properties"]


def test_dispatch_calls_function():
    @tool_registry.tool
    def add(a: str, b: str) -> str:
        """Add two numbers."""
        return str(int(a) + int(b))

    result = tool_registry.dispatch("add", '{"a": "2", "b": "3"}')
    assert result == "5"


def test_dispatch_unknown_tool_returns_error():
    result = tool_registry.dispatch("nonexistent", "{}")
    assert "unknown tool" in result


def test_schema_required_params():
    @tool_registry.tool
    def required_fn(required: str, optional: str = "default") -> str:
        """Test required vs optional."""
        return required

    schemas = tool_registry.get_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "required_fn")
    params = schema["function"]["parameters"]
    assert "required" in params["required"]
    assert "optional" not in params["required"]


def test_schema_type_mapping():
    @tool_registry.tool
    def typed_fn(s: str, n: int, f: float, b: bool) -> str:
        """Test type mapping."""
        return ""

    schemas = tool_registry.get_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "typed_fn")
    props = schema["function"]["parameters"]["properties"]
    assert props["s"]["type"] == "string"
    assert props["n"]["type"] == "integer"
    assert props["f"]["type"] == "number"
    assert props["b"]["type"] == "boolean"
