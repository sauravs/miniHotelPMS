# -*- coding: utf-8 -*-
"""
THE RECORDING NOTIFIER - what every test wires. A list, not a network.

Routes are handed in as a dict rather than read from the environment, so a test states who each
audience is in the test itself and never depends on the machine it runs on. `fail` makes every
send raise the given exception, for the paths where delivery goes wrong.
"""
from __future__ import annotations

from hotelcontrols.actions import EMAIL, Message


class RecordingNotifier:
    """Keeps every message it is asked to send in `sent`. Sends nothing anywhere."""

    name = "recording"
    channel = EMAIL

    def __init__(self, routes: dict[str, tuple[str, ...]] | None = None,
                 fail: BaseException | None = None) -> None:
        self.routes = dict(routes or {})
        self.fail = fail
        self.sent: list[Message] = []

    def route(self, audience: str) -> tuple[str, ...]:
        return tuple(self.routes.get(audience, ()))

    def send(self, message: Message) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append(message)
