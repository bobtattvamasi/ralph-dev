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
        LOGGER.error("Notification failed: %s", exc)
    except OSError as exc:
        LOGGER.error("Notification failed: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    send(" ".join(sys.argv[1:]) if len(sys.argv) > 1 else "ping")
