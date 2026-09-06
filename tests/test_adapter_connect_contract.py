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
