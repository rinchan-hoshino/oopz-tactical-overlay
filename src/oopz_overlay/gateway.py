from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from typing import Any

from oopz_sdk import OopzConfig
from oopz_sdk.client.rest import OopzRESTClient
from oopz_sdk.client.ws import OopzWSClient
from oopz_sdk.events.parser import EventParser
from oopz_sdk.models import JoinedAreaInfo, MessageEvent

from .chat import ChatMessage
from .gateway_mapping import choose_current_area, map_message, merge_area_payloads
from .settings import AppSettings

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Destination:
    area_id: str
    area_name: str
    channel_id: str
    channel_name: str

    @property
    def label(self) -> str:
        return f"#{self.channel_name}"


@dataclass(frozen=True, slots=True)
class LoginResult:
    settings: AppSettings
    destinations: tuple[Destination, ...]
    current_area_id: str = ""
    current_area_name: str = ""
    detected_live: bool = False


@dataclass(slots=True)
class GatewayCallbacks:
    timeline: Callable[[list[ChatMessage]], None]
    status: Callable[[str, bool], None]
    error: Callable[[str], None]


class GatewayRuntime:
    """Own the asyncio Oopz clients on one background thread."""

    def __init__(self, callbacks: GatewayCallbacks) -> None:
        self.callbacks = callbacks
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="oopz-gateway",
            daemon=True,
        )
        self._thread.start()
        self._rest: OopzRESTClient | None = None
        self._ws: OopzWSClient | None = None
        self._ws_task: asyncio.Task | None = None
        self._settings = AppSettings()
        self._names: dict[str, str] = {}
        self._parser = EventParser()
        self._closed = False

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(
        self,
        coroutine: Coroutine[Any, Any, Any],
        *,
        success: Callable[[Any], None] | None = None,
    ) -> None:
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)

        def done(result_future) -> None:
            try:
                value = result_future.result()
            except Exception as exc:  # noqa: BLE001 - third-party coroutine boundary
                self.callbacks.error(self._friendly_error(exc))
                return
            if success is not None:
                success(value)

        future.add_done_callback(done)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        lowered = text.casefold()
        if "expired" in lowered or "authentication" in lowered or "鉴权" in text:
            return "Oopz 登录态已失效，请先打开 Oopz 刷新后重新读取。"
        return f"Oopz：{text}"

    def inspect_session(
        self,
        settings: AppSettings,
        *,
        success: Callable[[LoginResult], None],
    ) -> None:
        self._submit(self._inspect_session(settings), success=success)

    @staticmethod
    def _config(settings: AppSettings) -> OopzConfig:
        return OopzConfig(
            device_id=settings.device_id,
            person_uid=settings.person_uid,
            jwt_token=settings.jwt_token,
            app_version=settings.app_version or "69514",
            auto_subscribe_joined_areas=False,
        )

    async def _inspect_session(self, settings: AppSettings) -> LoginResult:
        config = self._config(settings)
        rest = OopzRESTClient(config)
        await rest.start()
        try:
            payloads: list[list[dict[str, Any]]] = []
            failures: list[Exception] = []
            for endpoint in (
                "/userSubscribeArea/v1/list",
                "/client/v1/area/v1/home/v1/subscribed",
            ):
                try:
                    payload = await rest.areas._request_data("GET", endpoint)
                    if isinstance(payload, list):
                        payloads.append(payload)
                except Exception as exc:  # noqa: BLE001 - alternate Oopz endpoint
                    failures.append(exc)
            if not payloads and failures:
                raise failures[0]

            areas = [
                JoinedAreaInfo.from_api(item) for item in merge_area_payloads(*payloads)
            ]
            area_by_id = {area.area_id: area for area in areas}

            async def voice_channel(area_id: str) -> tuple[str, str | None]:
                try:
                    channel_id = await rest.channels.get_voice_channel_for_user(
                        area_id,
                        config.person_uid,
                    )
                except Exception as exc:
                    LOGGER.debug("Oopz voice presence lookup failed", exc_info=exc)
                    channel_id = None
                return area_id, channel_id

            voice_pairs = await asyncio.gather(
                *(voice_channel(area.area_id) for area in areas)
            )
            voice_by_area = dict(voice_pairs)
            current_area_id, detected_live = choose_current_area(
                list(area_by_id),
                voice_by_area,
                settings.area_id,
            )
            current_area = area_by_id.get(current_area_id)
            destinations: list[Destination] = []
            if current_area is not None:
                groups = await rest.areas.get_area_channels(current_area.area_id)
                for group in groups:
                    for channel in group.channels:
                        if channel.channel_type.upper() != "TEXT":
                            continue
                        destinations.append(
                            Destination(
                                area_id=current_area.area_id,
                                area_name=current_area.name,
                                channel_id=channel.channel_id,
                                channel_name=channel.name,
                            )
                        )
        finally:
            await rest.close()

        destinations.sort(
            key=lambda item: (
                item.area_id != settings.area_id,
                item.area_name.casefold(),
                item.channel_name.casefold(),
            )
        )
        current_area_name = current_area.name if current_area is not None else ""
        area_changed = bool(current_area_id and current_area_id != settings.area_id)
        base = replace(
            settings,
            app_version=config.app_version,
            area_id=current_area_id,
            area_name=current_area_name,
            channel_id="" if area_changed else settings.channel_id,
            channel_name="" if area_changed else settings.channel_name,
        )
        return LoginResult(
            base,
            tuple(destinations),
            current_area_id=current_area_id,
            current_area_name=current_area_name,
            detected_live=detected_live,
        )

    def connect(self, settings: AppSettings) -> None:
        self._submit(self._connect(settings))

    def disconnect(self) -> None:
        self._submit(self._disconnect())

    async def _connect(self, settings: AppSettings) -> None:
        await self._disconnect()
        self._settings = settings
        self._names.clear()
        config = self._config(settings)
        self._rest = OopzRESTClient(config)
        await self._rest.start()

        history = await self._rest.messages.get_channel_messages(
            settings.area_id,
            settings.channel_id,
            size=60,
        )
        await self._resolve_names(history)
        self.callbacks.timeline(
            [
                map_message(item, names=self._names, own_uid=settings.person_uid)
                for item in history
            ]
        )

        ready = asyncio.Event()

        async def on_open() -> None:
            if self._ws is not None:
                await self._ws.send_subscribe_area_events([settings.area_id])
            ready.set()

        async def on_raw(raw: str) -> None:
            await self._handle_ws_message(raw)

        async def on_error(error: object) -> None:
            self.callbacks.status("正在重连…", False)

        self._ws = OopzWSClient(
            config,
            on_open=on_open,
            on_message=on_raw,
            on_error=on_error,
        )
        self._ws_task = asyncio.create_task(self._ws.start())
        await asyncio.wait_for(ready.wait(), timeout=20)
        self.callbacks.status(f"#{settings.channel_name}", True)

    async def _resolve_names(self, messages: list[Any]) -> None:
        if self._rest is None:
            return
        missing = (
            {str(getattr(message, "sender_id", "") or "") for message in messages}
            - self._names.keys()
            - {""}
        )
        if not missing:
            return
        try:
            users = await self._rest.person.get_person_infos_batch(sorted(missing))
            self._names.update({user.uid: user.name for user in users if user.name})
        except Exception as exc:
            # A message remains usable with its short UID if profile lookup fails.
            LOGGER.debug("Oopz person name lookup failed", exc_info=exc)

    async def _handle_ws_message(self, raw: str) -> None:
        try:
            event = self._parser.parse(raw)
        except Exception as exc:
            LOGGER.debug("Ignored malformed Oopz websocket event", exc_info=exc)
            return
        if not isinstance(event, MessageEvent):
            return
        message = event.message
        if (
            message.area != self._settings.area_id
            or message.channel != self._settings.channel_id
        ):
            return
        await self._resolve_names([message])
        self.callbacks.timeline(
            [
                map_message(
                    message,
                    names=self._names,
                    own_uid=self._settings.person_uid,
                )
            ]
        )

    def send(self, text: str) -> None:
        self._submit(self._send(text))

    async def _send(self, text: str) -> None:
        if self._rest is None:
            raise RuntimeError("尚未连接 Oopz")
        await self._rest.messages.send_message(
            text,
            area=self._settings.area_id,
            channel=self._settings.channel_id,
        )

    async def _disconnect(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.stop()
            except Exception as exc:
                LOGGER.debug("Oopz websocket stop failed", exc_info=exc)
            self._ws = None
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                LOGGER.debug("Oopz websocket task ended with an error", exc_info=exc)
            self._ws_task = None
        if self._rest is not None:
            await self._rest.close()
            self._rest = None

    async def _shutdown(self) -> None:
        current = asyncio.current_task()
        pending = [
            task
            for task in asyncio.all_tasks(self._loop)
            if task is not current and not task.done()
        ]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await self._disconnect()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        try:
            future.result(timeout=5)
        except Exception as exc:
            LOGGER.debug("Oopz gateway shutdown timed out", exc_info=exc)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
