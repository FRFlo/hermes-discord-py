import asyncio

from views.tool_trace import (
    _format_tool_call,
    _format_tool_result,
    _trace_text,
    format_live_tool_call,
    delete_response_turn_from_session,
    delete_tracked_response,
    send_ephemeral_trace,
    split_discord_messages,
)


def test_final_action_view_contains_all_response_buttons():
    from views.tool_trace import build_tool_trace_view

    class Button:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class View:
        def __init__(self, **_kwargs):
            self.children = []

        def add_item(self, item):
            self.children.append(item)

    discord = type("Discord", (), {
        "ui": type("UI", (), {"View": View, "Button": Button}),
        "ButtonStyle": type("Styles", (), {
            "secondary": "secondary", "primary": "primary", "danger": "danger",
        }),
    })

    view = build_tool_trace_view(discord, object(), "agent:discord:dm:42")

    assert [button.label for button in view.children] == [
        "Afficher le raisonnement", "Exporter en Markdown", "Tout régénérer", "Continuer", "Supprimer",
    ]


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

    assert "🔧 read_file({\"path\":\"README.md\"}) → ✅" in rendered
    assert "12 lines" in rendered


def test_compact_trace_reduces_large_nested_values_and_keeps_keys():
    rendered = _trace_text([{
        "role": "assistant", "tool_calls": [{"function": {
            "name": "search", "arguments": {
                "query": "short", "documents": [{"title": "a", "body": "x" * 1000}],
            },
        }}],
    }])

    line = rendered.splitlines()[1]
    assert len(line) <= 240
    assert '"query":"short"' in line
    assert '"documents"' in line
    assert "1000 caractères" in line


def test_full_trace_markdown_uses_same_layout_without_truncation():
    rendered = _trace_text([{
        "role": "assistant", "tool_calls": [{"function": {
            "name": "write", "arguments": {"content": "x" * 400},
        }}],
    }], compact=False)

    assert rendered.startswith("🔎 **Tool trace**\n🔧 write(")
    assert "x" * 400 in rendered


def test_trace_marks_explicit_technical_errors_and_missing_results():
    rendered = _trace_text([
        {"role": "assistant", "tool_calls": [
            {"function": {"name": "broken", "arguments": {}}},
            {"function": {"name": "pending", "arguments": {}}},
        ]},
        {"role": "tool", "content": "failure", "is_error": True},
    ])

    assert "🔧 broken() → ❌ \"failure\"" in rendered
    assert "🔧 pending() → ✅ ∅" in rendered


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


def test_delete_tracked_response_removes_every_chunk_and_cache_entry():
    class Adapter:
        def __init__(self):
            self._hermes_response_message_ids = {
                ("session-1", "inbound-1"): ["10", "11", "12"],
            }
            self._hermes_session_keys_by_message_id = {
                "10": "session-1", "11": "session-1", "12": "session-1",
            }
            self.deleted = []

        async def delete_message(self, channel_id, message_id):
            self.deleted.append((channel_id, message_id))
            return True

    adapter = Adapter()
    target = type("Message", (), {
        "id": 12, "channel": type("Channel", (), {"id": 99})(),
    })()

    asyncio.run(delete_tracked_response(adapter, target, "session-1"))

    assert adapter.deleted == [("99", "10"), ("99", "11"), ("99", "12")]
    assert adapter._hermes_response_message_ids == {}
    assert adapter._hermes_session_keys_by_message_id == {}


def test_delete_response_turn_removes_matching_turn_only():
    class Entry:
        session_id = "db-session"
        last_prompt_tokens = 42

    class Store:
        def __init__(self):
            self.entry = Entry()
            self.rewritten = None

        def lookup_by_session_key(self, _session_key):
            return self.entry

        def load_transcript(self, _session_id):
            return [
                {"role": "user", "content": "first", "message_id": "in-1"},
                {"role": "assistant", "content": "old answer"},
                {"role": "tool", "content": "old tool"},
                {"role": "user", "content": "second", "message_id": "in-2"},
                {"role": "assistant", "content": "new answer"},
            ]

        def rewrite_transcript(self, session_id, messages, **kwargs):
            self.rewritten = (session_id, messages, kwargs)
            return True

    class Runner:
        def __init__(self):
            self.evicted = []

        def _evict_cached_agent(self, session_key):
            self.evicted.append(session_key)

    adapter = type("Adapter", (), {})()
    adapter._session_store = Store()
    adapter.gateway_runner = Runner()

    removed = asyncio.run(delete_response_turn_from_session(adapter, "session-1", "in-1"))

    assert removed is True
    _, messages, kwargs = adapter._session_store.rewritten
    assert [message["content"] for message in messages] == ["second", "new answer"]
    assert kwargs == {"active_only": True, "reject_active_turn_lease": True}
    assert adapter._session_store.entry.last_prompt_tokens == 0
    assert adapter.gateway_runner.evicted == ["session-1"]


def test_regenerate_confirmation_is_ephemeral_ack_and_dispatches_retry():
    from views.tool_trace import build_tool_trace_view

    class Button:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.view = None

    class View:
        def __init__(self, **_kwargs):
            self.children = []

        def add_item(self, item):
            item.view = self
            self.children.append(item)

    discord = type("Discord", (), {
        "ui": type("UI", (), {"View": View, "Button": Button}),
        "ButtonStyle": type("Styles", (), {
            "secondary": "secondary", "primary": "primary", "danger": "danger",
        }),
    })

    class Response:
        def __init__(self):
            self.sent = None
            self.edited = None

        async def send_message(self, content, **kwargs):
            self.sent = (content, kwargs)

        async def edit_message(self, **kwargs):
            self.edited = kwargs

        def is_done(self):
            return self.sent is not None or self.edited is not None

    class Adapter:
        def __init__(self):
            self._hermes_response_message_ids = {("session-1", "in-1"): ["10", "11"]}
            self._hermes_session_keys_by_message_id = {"10": "session-1", "11": "session-1"}
            self.deleted = []
            self.handled = []

        async def _check_slash_authorization(self, _interaction, command):
            return command == "/retry"

        async def delete_message(self, channel_id, message_id):
            self.deleted.append((channel_id, message_id))
            return True

        def _build_slash_event(self, interaction, text):
            return interaction, text

        async def handle_message(self, event):
            self.handled.append((
                event,
                dict(getattr(self, "_hermes_pending_response_turns", {})),
            ))

    adapter = Adapter()
    target = type("Message", (), {
        "id": 11, "channel": type("Channel", (), {"id": 99})(),
    })()
    initial = type("Interaction", (), {"response": Response(), "message": target})()
    initial.followup = type("Followup", (), {"send": lambda *_args, **_kwargs: None})()

    view = build_tool_trace_view(discord, adapter, "session-1")
    regenerate_button = next(button for button in view.children if button.label == "Tout régénérer")
    asyncio.run(regenerate_button.callback(initial))

    confirmation = initial.response.sent[1]["view"]
    assert initial.response.sent[1]["ephemeral"] is True
    confirmed = type("Interaction", (), {"response": Response()})()
    confirmed.followup = type("Followup", (), {})()
    confirm_button = next(button for button in confirmation.children if button.label == "Régénérer")
    asyncio.run(confirm_button.callback(confirmed))

    assert confirmed.response.edited == {
        "content": "La réponse va être régénérée.", "view": None,
    }
    assert adapter.deleted == [("99", "10"), ("99", "11")]
    assert adapter.handled == [(
        (confirmed, "/retry"),
        {"99": ("session-1", "in-1")},
    )]
    assert adapter._hermes_pending_response_turns == {}
