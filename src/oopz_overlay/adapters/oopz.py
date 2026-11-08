from __future__ import annotations
from ..i18n import tr

import asyncio
import logging
import re
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from typing import Any

from oopz_sdk import OopzConfig
from oopz_sdk.client.rest import OopzRESTClient
from oopz_sdk.client.ws import OopzWSClient
from oopz_sdk.events.parser import EventParser
from oopz_sdk.models import JoinedAreaInfo, MessageEvent

from ..core.timeline import ChatMessage
from ..core.settings import AppSettings

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
    live_timeline: Callable[[list[ChatMessage]], None]
    status: Callable[[str, bool], None]
    error: Callable[[str], None]
    send_error: Callable[[str], None]
    event: Callable[[GatewayEvent], None] | None = None


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    generation: int
    kind: str
    values: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    text: str
    area_id: str
    channel_id: str
    person_uid: str = ""
    error: str = ""


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
        self._rest: OopzRESTClient | None = None
        self._ws: OopzWSClient | None = None
        self._ws_task: asyncio.Task | None = None
        self._settings = AppSettings()
        self._names: dict[str, str] = {}
        self._parser = EventParser()
        self._closed = False
        self._generation = 0
        self._inspection = 0
        self._inspection_future = None
        self._switch_lock = asyncio.Lock()
        self._connect_task: asyncio.Task | None = None
        self._history_tasks: set[asyncio.Task] = set()
        self._ready = False
        self._thread.start()

    @property
    def generation(self) -> int:
        return self._generation

    def _emit(self, kind: str, *values: Any, generation: int | None = None) -> None:
        generation = self._generation if generation is None else generation
        if self._closed or (
            generation != self._generation and kind not in {"sent", "send_failed"}
        ):
            return
        event = GatewayEvent(generation, kind, values)
        if self.callbacks.event is not None:
            self.callbacks.event(event)
        else:
            if kind == "send_failed":
                self.callbacks.send_error(values[0].error)
                return
            callback = getattr(self.callbacks, kind, None)
            if callback is not None:
                callback(*values)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(
        self,
        coroutine: Coroutine[Any, Any, Any],
        *,
        success: Callable[[Any], None] | None = None,
        error: Callable[[str], None] | None = None,
    ):
        if self._closed:
            coroutine.close()
            return
        generation = self._generation
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)

        def done(result_future) -> None:
            if result_future.cancelled() or self._closed:
                return
            try:
                value = result_future.result()
            except Exception as exc:  # noqa: BLE001 - third-party coroutine boundary
                if error is not None:
                    error(self._friendly_error(exc))
                else:
                    self._emit(
                        "error", self._friendly_error(exc), generation=generation
                    )
                return
            if success is not None:
                success(value)

        future.add_done_callback(done)
        return future

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        text = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", "[已隐藏登录凭据]", text)
        lowered = text.casefold()
        if "expired" in lowered or "authentication" in lowered or "鉴权" in text:
            return "Oopz 登录态已失效，请先打开 Oopz 刷新后重新读取。"
        return f"Oopz：{text[:300]}"

    def list_channels(
        self,
        settings: AppSettings,
        *,
        success: Callable[[LoginResult], None],
    ) -> None:
        self._inspection += 1
        inspection = self._inspection
        if self._inspection_future is not None:
            self._inspection_future.cancel()
        self._inspection_future = self._submit(
            self._inspect_session(settings),
            success=lambda result: (
                success(result) if inspection == self._inspection else None
            ),
            error=lambda text: (
                self._emit("inspection_error", text)
                if inspection == self._inspection
                else None
            ),
        )

    def check_session(self) -> None:
        async def read():
            from .session import load_oopz_local_session, LocalSessionError
            try:
                return load_oopz_local_session()
            except (OSError, ValueError, LocalSessionError):
                return None
        self._submit(read(), success=lambda session: self._emit('session', session))

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
        self._generation += 1
        self._ready = False
        self._submit(self._replace_connection(settings, self._generation))

    def disconnect(self) -> None:
        self._inspection += 1
        if self._inspection_future is not None:
            self._inspection_future.cancel()
        self._generation += 1
        self._ready = False
        self._submit(self._replace_connection(None, self._generation))

    async def _replace_connection(
        self, settings: AppSettings | None, generation: int
    ) -> None:
        async with self._switch_lock:
            if generation != self._generation:
                return
            if self._connect_task is not None:
                self._connect_task.cancel()
                await asyncio.gather(self._connect_task, return_exceptions=True)
                self._connect_task = None
            await self._disconnect()
            if settings is None or generation != self._generation:
                return
            self._connect_task = asyncio.create_task(
                self._connect(settings, generation)
            )

            def finished(task: asyncio.Task) -> None:
                if not task.cancelled():
                    if generation == self._generation:
                        self._ready = False
                    error = task.exception() or RuntimeError(
                        "连接已结束，正在重新连接。"
                    )
                    self._emit(
                        "error", self._friendly_error(error), generation=generation
                    )

            self._connect_task.add_done_callback(finished)

    async def _connect(
        self, settings: AppSettings, generation: int | None = None
    ) -> None:
        generation = self._generation if generation is None else generation
        self._settings = settings
        self._names = {}
        names = self._names
        config = self._config(settings)
        self._rest = OopzRESTClient(config)
        rest = self._rest
        await rest.start()

        async def history() -> None:
            try:
                messages = await rest.messages.get_channel_messages(
                    settings.area_id,
                    settings.channel_id,
                    size=80,
                )
                await self._resolve_names(messages, rest=rest, names=names)
                self._emit(
                    "timeline",
                    [
                        map_message(item, names=names, own_uid=settings.person_uid)
                        for item in messages
                    ],
                    generation=generation,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._emit(
                    "history_error",
                    tr("历史消息暂时无法读取，实时消息仍会继续接收。"),
                    generation=generation,
                )
                LOGGER.debug("History request failed: %s", type(exc).__name__)

        async def on_open() -> None:
            if generation != self._generation:
                return
            await self._cancel_history()
            await ws.send_subscribe_area_events([settings.area_id])
            if generation != self._generation:
                return
            self._ready = True
            self._emit(
                "status", f"#{settings.channel_name}", True, generation=generation
            )
            task = asyncio.create_task(history())
            self._history_tasks.add(task)
            task.add_done_callback(self._history_tasks.discard)

        async def on_raw(raw: str) -> None:
            await self._handle_ws_message(
                raw, generation=generation, settings=settings, rest=rest, names=names
            )

        async def on_error(error: object) -> None:
            if generation == self._generation:
                self._ready = False
                self._emit(
                    "status", tr("连接中断，正在重连…"), False, generation=generation
                )

        async def on_close(_info: object) -> None:
            await on_error(None)

        async def on_reconnect() -> None:
            await on_error(None)

        ws = OopzWSClient(
            config,
            on_open=on_open,
            on_message=on_raw,
            on_error=on_error,
            on_close=on_close,
            on_reconnect=on_reconnect,
        )
        self._ws = ws
        self._ws_task = asyncio.create_task(ws.start())
        try:
            await self._ws_task
        finally:
            if generation == self._generation:
                self._ready = False

    async def _resolve_names(
        self, messages: list[Any], *, rest=None, names=None
    ) -> None:
        rest = self._rest if rest is None else rest
        names = self._names if names is None else names
        if rest is None:
            return
        missing = (
            {str(getattr(message, "sender_id", "") or "") for message in messages}
            - names.keys()
            - {""}
        )
        if not missing:
            return
        try:
            users = await rest.person.get_person_infos_batch(sorted(missing))
            names.update({user.uid: user.name for user in users if user.name})
            while len(names) > 256:
                del names[next(iter(names))]
        except Exception as exc:
            # A message remains usable with its short UID if profile lookup fails.
            LOGGER.debug("Oopz person name lookup failed", exc_info=exc)

    async def _handle_ws_message(
        self, raw: str, *, generation=None, settings=None, rest=None, names=None
    ) -> None:
        generation = self._generation if generation is None else generation
        if generation != self._generation:
            return
        settings = settings or self._settings
        names = self._names if names is None else names
        try:
            event = self._parser.parse(raw)
        except Exception as exc:
            LOGGER.debug("Ignored malformed Oopz websocket event", exc_info=exc)
            return
        if not isinstance(event, MessageEvent):
            return
        message = event.message
        if message.area != settings.area_id or message.channel != settings.channel_id:
            return
        await self._resolve_names([message], rest=rest, names=names)
        self._emit(
            "live_timeline",
            [
                map_message(
                    message,
                    names=names,
                    own_uid=settings.person_uid,
                )
            ],
            generation=generation,
        )

    def send(self, text: str) -> None:
        generation = self._generation
        settings = self._settings
        outgoing = OutgoingMessage(
            text, settings.area_id, settings.channel_id, person_uid=settings.person_uid
        )
        self._submit(
            self._send(text, generation=generation),
            success=lambda _: self._emit("sent", outgoing, generation=generation),
            error=lambda error: self._emit(
                "send_failed", replace(outgoing, error=error), generation=generation
            ),
        )

    async def _send(self, text: str, *, generation: int | None = None) -> None:
        if (
            self._rest is None
            or not self._ready
            or (generation is not None and generation != self._generation)
        ):
            raise RuntimeError("尚未连接 Oopz")
        await self._rest.messages.send_message(
            text,
            area=self._settings.area_id,
            channel=self._settings.channel_id,
        )

    async def _cancel_history(self) -> None:
        tasks = tuple(self._history_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._history_tasks.clear()

    async def _disconnect(self) -> None:
        self._ready = False
        await self._cancel_history()
        if self._ws is not None:
            try:
                await asyncio.wait_for(self._ws.stop(), timeout=3)
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
            rest = self._rest
            self._rest = None
            try:
                await asyncio.wait_for(rest.close(), timeout=3)
            except Exception as exc:
                LOGGER.debug("REST cleanup failed: %s", type(exc).__name__)

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
        if not self._thread.is_alive():
            self._loop.close()


from ..i18n import tr

from collections.abc import Mapping
from typing import Any

from ..core.timeline import ChatMessage


def _clean_text(value: str) -> str:
    return value.translate(
        str.maketrans("", "", "\u200e\u200f\u2066\u2067\u2068\u2069")
    )


def _text(source: Any) -> str:
    plain_text = getattr(source, "plain_text", "")
    if isinstance(plain_text, str) and plain_text:
        return _clean_text(plain_text)

    attachments = list(getattr(source, "attachments", None) or [])
    attachment_types = {
        str(getattr(attachment, "attachment_type", "") or "").upper()
        for attachment in attachments
    }
    if "IMAGE" in attachment_types:
        return tr("[图片]")
    if "VIDEO" in attachment_types:
        return tr("[视频]")
    if "AUDIO" in attachment_types:
        return tr("[语音]")
    if attachment_types:
        return tr("[文件]")

    message_type = str(getattr(source, "message_type", "") or getattr(source, "type", "") or "").upper()
    if message_type == "STICKER":
        return tr("[表情]")
    if message_type == "IMAGE":
        return tr("[图片]")

    for field in ("text", "content"):
        value = getattr(source, field, "")
        if isinstance(value, str) and value:
            if value.startswith("![IMAGE"):
                return tr("[图片]")
            return _clean_text(value)
    return tr("[非文字消息]")


def choose_current_area(
    area_ids: list[str],
    voice_channel_by_area: Mapping[str, str | None],
    previous_area_id: str,
) -> tuple[str, bool]:
    for area_id in area_ids:
        if voice_channel_by_area.get(area_id):
            return area_id, True
    if previous_area_id in area_ids:
        return previous_area_id, False
    return "", False


def merge_area_payloads(*payloads: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for item in payload:
            area_id = str(item.get("id") or item.get("area") or "")
            if not area_id:
                continue
            current = merged.setdefault(area_id, {})
            current.update(
                {key: value for key, value in item.items() if value is not None}
            )
            current.setdefault("id", area_id)
    return list(merged.values())


def map_message(
    source: Any,
    *,
    names: Mapping[str, str],
    own_uid: str,
) -> ChatMessage:
    sender_id = str(getattr(source, "sender_id", "") or "")
    timestamp = str(getattr(source, "timestamp", "") or "0")
    try:
        timestamp_us = int(timestamp)
    except ValueError:
        timestamp_us = 0
    return ChatMessage(
        message_id=str(getattr(source, "message_id", "") or ""),
        timestamp_us=timestamp_us,
        sender_id=sender_id,
        sender_name=names.get(sender_id)
        or (tr("我") if sender_id == own_uid else sender_id[-6:] or tr("未知")),
        text=_text(source),
        mine=sender_id == own_uid,
    )
