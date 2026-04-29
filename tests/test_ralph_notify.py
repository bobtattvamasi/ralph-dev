from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError, URLError

from scripts import ralph_notify as notify


def test_send_skips_when_telegram_not_configured(caplog) -> None:
    old_token = notify.TOKEN
    old_chat_id = notify.CHAT_ID
    try:
        notify.TOKEN = ""
        notify.CHAT_ID = ""
        with caplog.at_level("WARNING", logger="ralph.notify"):
            notify.send("hello")
    finally:
        notify.TOKEN = old_token
        notify.CHAT_ID = old_chat_id

    assert "Notification skipped: Telegram token/chat id not configured" in caplog.text


def test_send_logs_http_error_diagnostics(monkeypatch, caplog) -> None:
    old_token = notify.TOKEN
    old_chat_id = notify.CHAT_ID
    old_timeout = notify.TELEGRAM_TIMEOUT_SEC
    try:
        notify.TOKEN = "TEST"
        notify.CHAT_ID = "123"
        notify.TELEGRAM_TIMEOUT_SEC = 9

        def failing_urlopen(_req, timeout=10):  # noqa: ARG001
            raise HTTPError(
                url="https://api.telegram.org/botTEST/sendMessage",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=BytesIO(b"{\"ok\":false,\"description\":\"Bad Request: can't parse entities\"}"),
            )

        monkeypatch.setattr("urllib.request.urlopen", failing_urlopen)
        with caplog.at_level("ERROR", logger="ralph.notify"):
            notify.send("broken <payload>")
    finally:
        notify.TOKEN = old_token
        notify.CHAT_ID = old_chat_id
        notify.TELEGRAM_TIMEOUT_SEC = old_timeout

    assert "Notification failed:" in caplog.text
    assert "HTTPError: HTTP Error 400: Bad Request" in caplog.text
    assert "payload_length=16" in caplog.text
    assert "payload_preview=broken <payload>" in caplog.text
    assert "timeout=9s" in caplog.text
    assert "can't parse entities" in caplog.text


def test_send_logs_url_error_diagnostics_without_body(monkeypatch, caplog) -> None:
    old_token = notify.TOKEN
    old_chat_id = notify.CHAT_ID
    try:
        notify.TOKEN = "TEST"
        notify.CHAT_ID = "123"

        def failing_urlopen(_req, timeout=10):  # noqa: ARG001
            raise URLError("network unreachable")

        monkeypatch.setattr("urllib.request.urlopen", failing_urlopen)
        with caplog.at_level("ERROR", logger="ralph.notify"):
            notify.send("network check")
    finally:
        notify.TOKEN = old_token
        notify.CHAT_ID = old_chat_id

    assert "Notification failed:" in caplog.text
    assert "URLError: <urlopen error network unreachable>" in caplog.text
    assert "payload_preview=network check" in caplog.text
    assert "error_body=" in caplog.text
