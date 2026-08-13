# scripts/test_telegram.py

from __future__ import annotations

import socket
import sys

from sdfm.communication.telegram import TelegramNotifier


def main() -> int:

    print()
    print("=" * 60)
    print(" SDFM TELEGRAM TEST")
    print("=" * 60)

    telegram = TelegramNotifier()

    if not telegram.configured:

        print("Telegram : NOT CONFIGURED")
        print()
        print(
            "Required environment variables:"
        )

        print(
            "SDFM_TELEGRAM_BOT_TOKEN"
        )

        print(
            "SDFM_TELEGRAM_CHAT_ID"
        )

        return 1

    hostname = socket.gethostname()

    message = (
        "🚁 SDFM Telegram Test\n"
        f"Vehicle: DR01\n"
        f"Host: {hostname}\n"
        "Status: Communication OK"
    )

    print("Sending Telegram message...")

    success = telegram.send(
        message
    )

    if not success:

        print("Telegram : FAILED")
        return 1

    print("Telegram : OK")

    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )