import asyncio

from views.tool_trace import (
    _format_tool_call,
    _format_tool_result,
    _trace_text,
    format_live_tool_call,
    send_ephemeral_trace,
    split_discord_messages,
)


def test_format_tool_call_uses_code_call_shape():
    rendered = _format_tool_call("read_file", {"path": "README.md"})

    assert rendered == '\n⚙️ `read_file(path="README.md")`'


def test_format_tool_call_empty_arguments_is_compact():
    assert _format_tool_call("show_tip", {}) == "\n⚙️ `show_tip()`"


def test_format_live_tool_call_honors_off_and_log_modes():
    event = type("Event", (), {"tool_name": "terminal", "args": {"command": "pwd"}})()

    assert format_live_tool_call(event, mode="off") is None
    assert format_live_tool_call(event, mode="log") is None


def test_format_live_tool_call_uses_real_arguments():
    event = type("Event", (), {"tool_name": "terminal", "args": {"command": "pwd"}})()

    assert format_live_tool_call(event) == '\n⚙️ `terminal(command="pwd")`'


def test_verbose_live_tool_call_uses_multiline_json():
    event = type("Event", (), {"tool_name": "patch", "args": {"file": "x.py"}})()

    rendered = format_live_tool_call(event, mode="verbose")
    assert rendered.startswith("\n⚙️ `patch`(\n```json")
    assert '"file": "x.py"' in rendered


def test_format_tool_result_keeps_nested_fences_readable():
    rendered = _format_tool_result("output\n```python\nprint('ok')\n```")

    assert rendered.startswith("↳ **Result**\n````")
    assert rendered.endswith("\n````")


def test_trace_renders_call_and_result_together():
    rendered = _trace_text([
        {"role": "user", "content": "Inspect the file"},
        {"role": "assistant", "tool_calls": [{
            "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
        }]},
        {"role": "tool", "content": "12 lines"},
    ])

    assert "⚙️ `read_file(path=" in rendered
    assert "↳ **Result**" in rendered
    assert "12 lines" in rendered


def test_split_trace_never_exceeds_discord_safe_limit():
    chunks = split_discord_messages("first\n" + ("x" * 5000) + "\nlast")

    assert len(chunks) > 1
    assert all(len(chunk) <= 1900 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == "first" + ("x" * 5000) + "last"


def test_ephemeral_trace_uses_followups_for_remaining_chunks():
    class Response:
        def __init__(self):
            self.messages = []

        async def send_message(self, content, *, ephemeral):
            self.messages.append((content, ephemeral))

    class Followup:
        def __init__(self):
            self.messages = []

        async def send(self, content, *, ephemeral):
            self.messages.append((content, ephemeral))

    class Interaction:
        def __init__(self):
            self.response = Response()
            self.followup = Followup()

    interaction = Interaction()
    asyncio.run(send_ephemeral_trace(interaction, "x" * 4000))

    assert len(interaction.response.messages) == 1
    assert len(interaction.followup.messages) == 2
    assert all(ephemeral for _, ephemeral in interaction.followup.messages)
