# sdfm/communication/telegram.py

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from sdfm import config

DEFAULT_TIMEOUT_SEC = 5.0


class TelegramNotifier:
    """
    Simple Telegram notification client for SDFM.

    Intended for:
    - system status
    - diagnostics
    - mission status
    - warning
    - failsafe notification

    Telegram is NOT part of the flight-control safety path.
    Failure to send a Telegram message must never block flight logic.
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:

        self.bot_token = (
            bot_token
            or os.getenv("SDFM_TELEGRAM_BOT_TOKEN")
        )

        self.chat_id = (
            chat_id
            or os.getenv("SDFM_TELEGRAM_CHAT_ID")
        )

        self.timeout_sec = timeout_sec

    @property
    def configured(self) -> bool:
        return bool(
            self.bot_token
            and self.chat_id
        )

    def send(
        self,
        message: str,
    ) -> bool:
        """
        Send Telegram text message.

        Returns:
            True  -> Telegram accepted message
            False -> sending failed

        This method intentionally does not raise network errors
        into flight-control code.
        """

        if not self.configured:
            return False

        url = (
            f"https://api.telegram.org/"
            f"bot{self.bot_token}/sendMessage"
        )

        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": message,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=self.timeout_sec,
            ) as response:

                data = json.loads(
                    response.read().decode("utf-8")
                )

            return bool(
                data.get("ok")
            )

        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
        ):
            return False

        except Exception:
            return False