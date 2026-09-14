import asyncio

from services.messaging import MessagingMixin


def _messaging():
    instance = object.__new__(MessagingMixin)
    instance._hermes_session_keys_by_message_id = {}
    return instance


def test_preview_message_inherits_inbound_session_key():
    messaging = _messaging()
    messaging._remember_response_session_key("inbound-1", "agent:discord:dm:42")

    session_key = messaging._response_session_key(None, "inbound-1")
    messaging._remember_response_session_key("preview-1", session_key)

    assert messaging._response_session_key(None, "preview-1") == "agent:discord:dm:42"


def test_explicit_session_metadata_takes_precedence_over_cache():
    messaging = _messaging()
    messaging._remember_response_session_key("preview-1", "cached-session")

    assert messaging._response_session_key(
        {"_hermes_session_key": "explicit-session"}, "preview-1",
    ) == "explicit-session"


def test_response_tracking_deduplicates_all_discord_chunks():
    messaging = _messaging()
    messaging._session_store = None

    asyncio.run(messaging._track_response_message_ids(
        "session-1", "inbound-1", ["preview-1", "continuation-1"],
    ))
    asyncio.run(messaging._track_response_message_ids(
        "session-1", "inbound-1", ["continuation-1", "continuation-2"],
    ))

    assert messaging._hermes_response_message_ids[("session-1", "inbound-1")] == [
        "preview-1", "continuation-1", "continuation-2",
    ]
    assert messaging._response_session_key(None, "continuation-2") == "session-1"


def test_pending_regeneration_turn_supplies_response_identity():
    messaging = _messaging()
    messaging._hermes_pending_response_turns = {
        "channel-1": ("session-1", "inbound-1"),
    }

    assert messaging._pending_response_turn("channel-1") == (
        "session-1", "inbound-1",
    )
    assert messaging._pending_response_turn("channel-2") == (None, None)


def test_regenerated_final_edit_gets_buttons_and_is_tracked():
    class Message:
        def __init__(self):
            self.edits = []

        async def edit(self, **kwargs):
            self.edits.append(kwargs)

    class Channel:
        id = "channel-1"

        def __init__(self, message):
            self.message = message

        def get_partial_message(self, _message_id):
            return self.message

    class Client:
        def __init__(self):
            self.views = []

        def add_view(self, view):
            self.views.append(view)

    messaging = _messaging()
    message = Message()
    channel = Channel(message)
    messaging._client = Client()
    messaging._session_store = None
    messaging._last_overflow_preview = {}
    messaging._hermes_pending_response_turns = {
        "channel-1": ("session-1", "inbound-1"),
    }
    messaging.MAX_MESSAGE_LENGTH = 2000
    messaging.format_message = lambda content: content

    async def resolve_channel(_chat_id):
        return channel

    async def record_response(*_args):
        return None

    messaging._resolve_channel = resolve_channel
    messaging._record_response_async = record_response

    result = asyncio.run(messaging.edit_message(
        "channel-1", "20", "regenerated answer", finalize=True,
    ))

    assert result.success is True
    assert message.edits[0]["content"] == "regenerated answer"
    assert [button.label for button in message.edits[0]["view"].children] == [
        "Afficher le raisonnement", "Tout régénérer", "Continuer", "Supprimer",
    ]
    assert messaging._hermes_response_message_ids[("session-1", "inbound-1")] == ["20"]
