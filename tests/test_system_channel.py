from types import SimpleNamespace

from adapter import _looks_like_nonconversational_history_message
from services.messaging import MessagingMixin
from services.standalone import _configured_system_channel_id as standalone_system_channel_id


def _messaging(system_channel=None):
    instance = object.__new__(MessagingMixin)
    instance.config = SimpleNamespace(extra={"system_channel": system_channel})
    return instance


def test_gateway_shutdown_warning_is_nonconversational():
    message = "⚠️ Gateway shutting down — Your current task will be interrupted."

    assert _looks_like_nonconversational_history_message(message)


def test_shutdown_warning_routes_to_configured_system_channel_without_metadata():
    messaging = _messaging({"platform": "discord-frflo", "chat_id": "1548801731427700787"})

    assert messaging._configured_system_channel_id(
        "⚠️ Gateway shutting down — Your current task will be interrupted.", None,
    ) == "1548801731427700787"


def test_regular_message_does_not_route_to_system_channel():
    messaging = _messaging({"platform": "discord-frflo", "chat_id": "1548801731427700787"})

    assert messaging._configured_system_channel_id("Hello", None) is None


def test_standalone_shutdown_warning_uses_same_system_channel():
    config = SimpleNamespace(extra={
        "system_channel": {"platform": "discord-frflo", "chat_id": "1548801731427700787"},
    })

    assert standalone_system_channel_id(
        config, "⚠️ Gateway shutting down — Your current task will be interrupted.",
    ) == "1548801731427700787"
