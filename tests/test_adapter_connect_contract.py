"""Regression tests for the Hermes platform adapter contract."""

import ast
from pathlib import Path


ADAPTER_FILE = Path(__file__).parents[1] / "adapter.py"


def test_connect_accepts_gateway_reconnect_keyword() -> None:
    """The gateway forwards ``is_reconnect`` on every retry."""
    tree = ast.parse(ADAPTER_FILE.read_text(encoding="utf-8"))
    adapter_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DiscordPyAdapter"
    )
    connect = next(
        node
        for node in adapter_class.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "connect"
    )

    assert any(arg.arg == "is_reconnect" for arg in connect.args.kwonlyargs)


def test_message_events_use_normalized_field_names() -> None:
    """Keep plugin events compatible with the current gateway dataclass."""
    files = [ADAPTER_FILE, ADAPTER_FILE.parent / "events" / "lifecycle.py"]
    unsupported = {"reply_to", "raw"}

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            if not isinstance(call.func, ast.Name) or call.func.id != "MessageEvent":
                continue
            names = {keyword.arg for keyword in call.keywords if keyword.arg is not None}
            assert not names & unsupported, f"{path}: unsupported fields {names & unsupported}"
