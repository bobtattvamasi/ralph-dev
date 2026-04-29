#!/usr/bin/env python3
"""Send a Telegram notification from ralph.sh."""
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

try:
    from ralph_common import get_telegram_timeout_sec
except ImportError:
    from scripts.ralph_common import get_telegram_timeout_sec

RALPH_VERSION = '0.1.0'
LOGGER = logging.getLogger("ralph.notify")

load_dotenv(Path(__file__).parent.parent / ".env")

TOKEN = os.environ.get("RALPH_TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("RALPH_TELEGRAM_CHAT_ID", "")
TELEGRAM_TIMEOUT_SEC = get_telegram_timeout_sec()


def _payload_preview(text: str) -> str:
    return text[:300].replace("\n", "\\n")


def _read_error_body(exc: BaseException) -> str:
    body_stream = getattr(exc, "fp", None)
    if body_stream is None:
        return ""
    try:
        body = body_stream.read()
    except Exception:
        return ""
    finally:
        try:
            body_stream.close()
        except Exception:
            pass
    if isinstance(body, str):
        return body
    if isinstance(body, (bytes, bytearray)):
        try:
            return body.decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def _log_send_failure(exc: BaseException, text: str) -> None:
    LOGGER.error(
        "Notification failed: error=%s payload_length=%s payload_preview=%s timeout=%ss error_body=%s",
        f"{exc.__class__.__name__}: {exc}",
        len(text),
        _payload_preview(text),
        TELEGRAM_TIMEOUT_SEC,
        _read_error_body(exc),
    )


def send(text: str) -> None:
    if not TOKEN or not CHAT_ID:
        LOGGER.warning("Notification skipped: Telegram token/chat id not configured")
        return
    api = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": CHAT_ID,
            "text": text[:4096],
            "parse_mode": "HTML",
        }
    ).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(api, data=data),
            timeout=TELEGRAM_TIMEOUT_SEC,
        )
    except urllib.error.URLError as exc:
        _log_send_failure(exc, text)
    except OSError as exc:
        _log_send_failure(exc, text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    send(" ".join(sys.argv[1:]) if len(sys.argv) > 1 else "ping")
