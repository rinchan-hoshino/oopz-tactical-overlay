from __future__ import annotations

import os
from threading import Event

import pytest

from oopz_overlay.chat import ChatMessage
from oopz_overlay.gateway import (
    GatewayCallbacks,
    GatewayRuntime,
    WindowsOopzBackend,
    messages_from_accessible_rows,
)


@pytest.mark.skipif(os.name != "nt", reason="Windows UI Automation backend")
def test_windows_backend_initializes_required_win32_types() -> None:
    backend = WindowsOopzBackend()

    assert backend.wintypes.DWORD


def _message(message_id: str, text: str) -> ChatMessage:
    return ChatMessage(
        message_id=message_id,
        timestamp_us=1_787_000_000_000_000,
        sender_id="user-a",
        sender_name="玩家",
        text=text,
        mine=True,
    )


def test_accessible_rows_reconstruct_wrapped_messages() -> None:
    rows = [
        ("GroupControl", "2026年08月19日\n队友A\n10:15\n第一行", 100),
        ("TextControl", "第二行", 120),
        ("GroupControl", "2026年08月19日\n玩家\n10:16\n收到", 160),
    ]

    messages = messages_from_accessible_rows(rows)

    assert [(item.sender_name, item.text) for item in messages] == [
        ("队友A", "第一行\n第二行"),
        ("玩家", "收到"),
    ]
    assert messages[0].message_id != messages[1].message_id


class FakeBackend:
    def __init__(self) -> None:
        self.current = "综合文字"
        self.messages = [_message("m1", "hello")]
        self.sent: list[str] = []
        self.released = False
        self.fail_poll = False

    def prepare(self) -> None:
        return

    def current_channel(self) -> str:
        return self.current

    def visible_messages(self) -> list[ChatMessage]:
        if self.fail_poll:
            raise RuntimeError("window unavailable")
        return list(self.messages)

    def send_message(self, text: str) -> None:
        self.sent.append(text)

    def release(self) -> None:
        self.released = True


def test_runtime_follows_oopz_current_channel_without_selecting_it() -> None:
    backend = FakeBackend()
    statuses: list[tuple[str, bool]] = []
    timelines: list[list[ChatMessage]] = []
    channels: list[str] = []
    errors: list[str] = []
    first_timeline = Event()
    changed_timeline = Event()

    def on_timeline(items: list[ChatMessage]) -> None:
        timelines.append(items)
        if len(timelines) == 1:
            first_timeline.set()
        else:
            changed_timeline.set()

    runtime = GatewayRuntime(
        GatewayCallbacks(
            timeline=on_timeline,
            status=lambda text, connected: statuses.append((text, connected)),
            error=errors.append,
            channel=channels.append,
        ),
        backend_factory=lambda: backend,
    )
    try:
        runtime.connect()
        assert first_timeline.wait(2)
        assert channels == ["综合文字"]
        assert timelines[0][0].text == "hello"

        backend.current = "主页"
        backend.messages = [_message("m2", "new channel")]
        assert changed_timeline.wait(2)
        assert channels[-1] == "主页"
        assert timelines[-1][0].text == "new channel"

        runtime.send("战术消息")
        for _ in range(20):
            if backend.sent:
                break
            Event().wait(0.05)
        assert backend.sent == ["战术消息"]
        assert any(connected for _text, connected in statuses)
        assert errors == []
    finally:
        runtime.close()

    assert backend.released is True


def test_runtime_reports_one_disconnect_and_recovers_on_next_oopz_poll() -> None:
    backend = FakeBackend()
    statuses: list[tuple[str, bool]] = []
    errors: list[str] = []
    connected = Event()
    disconnected = Event()
    recovered = Event()

    def on_status(text: str, value: bool) -> None:
        statuses.append((text, value))
        if value and not connected.is_set():
            connected.set()
        elif not value:
            disconnected.set()
        elif value:
            recovered.set()

    runtime = GatewayRuntime(
        GatewayCallbacks(
            timeline=lambda _items: None,
            status=on_status,
            error=errors.append,
            channel=lambda _name: None,
        ),
        backend_factory=lambda: backend,
    )
    try:
        runtime.connect()
        assert connected.wait(2)
        backend.fail_poll = True
        assert disconnected.wait(2)
        Event().wait(0.8)
        assert len(errors) == 1

        backend.fail_poll = False
        assert recovered.wait(2)
        assert statuses[-1][1] is True
    finally:
        runtime.close()
