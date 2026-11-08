from __future__ import annotations

import asyncio
from types import SimpleNamespace

from oopz_overlay.adapters.oopz import GatewayRuntime


class FakePersonService:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def get_person_infos_batch(self, user_ids: list[str]):
        self.calls.append(user_ids)
        return [
            SimpleNamespace(uid=user_id, name=f"name-{user_id}") for user_id in user_ids
        ]


class FakeRest:
    def __init__(self) -> None:
        self.person = FakePersonService()


def test_sender_profiles_are_batched_and_cached() -> None:
    runtime = object.__new__(GatewayRuntime)
    runtime._rest = FakeRest()
    runtime._names = {}

    asyncio.run(
        runtime._resolve_names(
            [SimpleNamespace(sender_id="u2"), SimpleNamespace(sender_id="u1")]
        )
    )
    asyncio.run(
        runtime._resolve_names(
            [SimpleNamespace(sender_id="u2"), SimpleNamespace(sender_id="u3")]
        )
    )

    assert runtime._rest.person.calls == [["u1", "u2"], ["u3"]]
    assert runtime._names == {"u1": "name-u1", "u2": "name-u2", "u3": "name-u3"}


def test_sender_cache_evicts_old_profiles_and_reuses_recent_ones() -> None:
    runtime = object.__new__(GatewayRuntime)
    runtime._rest = FakeRest()
    runtime._names = {}

    async def visit():
        for start in range(0, 800, 80):
            await runtime._resolve_names([SimpleNamespace(sender_id=f'u{i}')
                                          for i in range(start, start + 80)])
        assert len(runtime._names) <= 256
        calls = len(runtime._rest.person.calls)
        await runtime._resolve_names([SimpleNamespace(sender_id='u799')])
        assert len(runtime._rest.person.calls) == calls
        await runtime._resolve_names([SimpleNamespace(sender_id='u0')])
        assert runtime._rest.person.calls[-1] == ['u0']

    asyncio.run(visit())


def test_resolving_new_profiles_keeps_cached_senders_from_the_same_batch() -> None:
    from oopz_overlay.adapters.oopz import map_message
    runtime = object.__new__(GatewayRuntime)
    runtime._rest = FakeRest()
    runtime._names = {f'u{i}': f'name-u{i}' for i in range(256)}
    current = [SimpleNamespace(sender_id='u0', message_id='old', timestamp='1', plain_text='old'),
               SimpleNamespace(sender_id='new', message_id='new', timestamp='2', plain_text='new')]
    asyncio.run(runtime._resolve_names(current))
    assert [map_message(m, names=runtime._names, own_uid='me').sender_name for m in current] == ['name-u0', 'name-new']
    assert len(runtime._names) <= 256
