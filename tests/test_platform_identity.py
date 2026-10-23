import ast
from pathlib import Path


def test_adapter_initializer_uses_registered_plugin_platform():
    source = Path(__file__).parents[1] / "services" / "initialization.py"
    module = ast.parse(source.read_text(encoding="utf-8"))

    initializer = next(
        node for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    base_init_call = next(
        node for node in ast.walk(initializer)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "__init__"
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Name)
        and node.func.value.func.id == "super"
    )

    assert ast.unparse(base_init_call.args[1]) == "Platform('discord-frflo')"
