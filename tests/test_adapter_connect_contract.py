"""Regression tests for the Hermes platform adapter contract."""

import ast
from pathlib import Path


ADAPTER_FILE = Path(__file__).parents[1] / "adapter.py"
LIFECYCLE_FILE = ADAPTER_FILE.parent / "events" / "lifecycle.py"


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


def test_signatures_align_with_base_platform_adapter() -> None:
    """Verify signatures match BasePlatformAdapter expectations."""
    tree = ast.parse(ADAPTER_FILE.read_text(encoding="utf-8"))
    adapter_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DiscordPyAdapter"
    )
    methods = {
        node.name: node
        for node in adapter_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    # send_typing
    assert "metadata" in [a.arg for a in methods["send_typing"].args.args]

    # edit_message
    assert "finalize" in [a.arg for a in methods["edit_message"].args.kwonlyargs]

    # send_clarify
    clarify_args = [a.arg for a in methods["send_clarify"].args.args]
    assert "choices" in clarify_args and "clarify_id" in clarify_args


def test_actions_are_attached_only_to_notified_final_replies() -> None:
    """Intermediate/status sends must not expose turn actions."""
    source = ADAPTER_FILE.read_text(encoding="utf-8")
    assert 'if not is_dm and metadata and metadata.get("notify"):' in source


def test_bot_message_deletions_are_not_reprocessed_as_inbound_events() -> None:
    """Cleaning a bot reply must not synthesize another /stop turn."""
    source = ADAPTER_FILE.read_text(encoding="utf-8")
    assert "if is_bot:\n                return" in source


def test_button_actions_use_gateway_commands() -> None:
    """Regeneration/closure must use control commands, not agent prose."""
    source = ADAPTER_FILE.read_text(encoding="utf-8")
    assert 'MessageType.COMMAND if action in {"regenerate", "close"}' in source


def test_edit_lifecycle_does_not_dispatch_visible_stop() -> None:
    """Editing must cancel directly, otherwise /stop leaks a duplicate reply."""
    source = LIFECYCLE_FILE.read_text(encoding="utf-8")
    edit_source = source.split("async def handle_message_edit", 1)[1]
    assert "cancel_session_processing" in edit_source
    assert 'text="/stop"' not in edit_source


def test_edit_lifecycle_cleans_post_edit_bot_messages() -> None:
    """Replies after an edited prompt are stale and must be removed."""
    source = LIFECYCLE_FILE.read_text(encoding="utf-8")
    edit_source = source.split("async def handle_message_edit", 1)[1]
    assert "channel.history" in edit_source
    assert "oldest_first=True" in edit_source
