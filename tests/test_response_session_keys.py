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
