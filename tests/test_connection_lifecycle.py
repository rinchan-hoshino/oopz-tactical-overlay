import asyncio
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from oopz_overlay.gateway import GatewayCallbacks, GatewayRuntime
from oopz_overlay.settings import AppSettings


@pytest.fixture
def transport(monkeypatch):
    events = []
    state = SimpleNamespace(
        clients=[],
        sockets=[],
        history=[],
        sent=[],
        slow_started=threading.Event(),
        slow_cancelled=threading.Event(),
        reject=False,
    )

    class Rest:
        def __init__(self, config):
            self.config = config
            self.messages = self
            self.person = self
            self.closed = False
            state.clients.append(self)

        async def start(self):
            pass

        async def close(self):
            self.closed = True

        async def get_channel_messages(self, area, channel, *, size):
            state.history.append(channel)
            if channel == "slow":
                state.slow_started.set()
                try:
                    await asyncio.Future()
                finally:
                    state.slow_cancelled.set()
            if channel == "history-error":
                raise OSError("history unavailable")
            return [
                SimpleNamespace(
                    message_id=channel,
                    sender_id="peer",
                    timestamp="1",
                    plain_text=channel,
                )
            ]

        async def get_person_infos_batch(self, ids):
            return [SimpleNamespace(uid=value, name=value) for value in ids]

        async def send_message(self, text, *, area, channel):
            state.sent.append((text, area, channel))
            if state.reject:
                raise ValueError("message rejected")

    class Socket:
        def __init__(self, config, **callbacks):
            self.callbacks = callbacks
            self.stopped = asyncio.Event()
            state.sockets.append(self)

        async def start(self):
            await self.callbacks["on_open"]()
            await self.stopped.wait()

        async def send_subscribe_area_events(self, areas):
            pass

        async def stop(self):
            self.stopped.set()

    monkeypatch.setattr("oopz_overlay.gateway.OopzRESTClient", Rest)
    monkeypatch.setattr("oopz_overlay.gateway.OopzWSClient", Socket)
    runtime = GatewayRuntime(
        GatewayCallbacks(
            timeline=lambda *_: None,
            live_timeline=lambda *_: None,
            status=lambda *_: None,
            error=lambda *_: None,
            send_error=lambda *_: None,
            event=events.append,
        )
    )
    settings = AppSettings(
        device_id="d",
        person_uid="self",
        jwt_token="test-session",
        area_id="area",
        channel_id="first",
        channel_name="first",
    )
    try:
        yield runtime, settings, state, events
    finally:
        runtime.close()
        assert not runtime._thread.is_alive()
        assert all(client.closed for client in state.clients)


def wait_for(predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "background operation did not complete"


def test_switch_cancels_old_history_and_keeps_only_the_final_channel(transport):
    runtime, settings, state, events = transport
    runtime.connect(replace(settings, channel_id="slow"))
    assert state.slow_started.wait(2)
    runtime.connect(replace(settings, channel_id="second"))
    runtime.connect(replace(settings, channel_id="last"))
    wait_for(
        lambda: any(
            e.kind == "timeline" and e.values[0][0].text == "last" for e in events
        )
    )
    assert state.slow_cancelled.is_set()
    assert not any(
        e.kind == "timeline" and e.values[0][0].text == "slow" for e in events
    )
    runtime.send("destination check")
    wait_for(lambda: bool(state.sent))
    assert state.sent == [("destination check", "area", "last")]
    assert sum(not client.closed for client in state.clients) == 1


def test_reconnect_restores_ready_state_and_backfills_history(transport):
    runtime, settings, state, events = transport
    runtime.connect(settings)
    wait_for(lambda: any(e.kind == "timeline" for e in events))

    async def reconnect():
        await state.sockets[-1].callbacks["on_error"](OSError("offline"))
        await state.sockets[-1].callbacks["on_open"]()

    asyncio.run_coroutine_threadsafe(reconnect(), runtime._loop).result(2)
    wait_for(lambda: len(state.history) == 2)
    assert [e.values[1] for e in events if e.kind == "status"] == [True, False, True]
    assert runtime._ready


def test_history_failure_does_not_disable_send_or_disconnect(transport):
    runtime, settings, state, events = transport
    runtime.connect(replace(settings, channel_id="history-error"))
    wait_for(lambda: any(e.kind == "history_error" for e in events))
    runtime.send("still connected")
    wait_for(lambda: any(e.kind == "sent" for e in events))
    assert runtime._ready
    assert not any(e.kind == "error" for e in events)


def test_rejected_message_preserves_draft_and_destination_without_retrying(transport):
    runtime, settings, state, events = transport
    runtime.connect(settings)
    wait_for(lambda: any(e.kind == "timeline" for e in events))
    state.reject = True
    runtime.send("keep this draft")
    wait_for(lambda: any(e.kind == "send_failed" for e in events))
    failed = next(e.values[0] for e in events if e.kind == "send_failed")
    assert (failed.text, failed.area_id, failed.channel_id, failed.person_uid) == (
        "keep this draft",
        "area",
        "first",
        "self",
    )
    assert len(state.sent) == 1
    assert runtime._ready
