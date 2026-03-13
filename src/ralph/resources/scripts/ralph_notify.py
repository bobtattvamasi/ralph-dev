#!/usr/bin/env python3
"""Send a Telegram notification from ralph.sh."""
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

RALPH_VERSION = '0.1.0'

load_dotenv(Path(__file__).parent.parent / ".env")

TOKEN = os.environ.get("RALPH_TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("RALPH_TELEGRAM_CHAT_ID", "")


def send(text: str) -> None:
    if not TOKEN or not CHAT_ID:
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
        urllib.request.urlopen(urllib.request.Request(api, data=data), timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    send(" ".join(sys.argv[1:]) if len(sys.argv) > 1 else "ping")
