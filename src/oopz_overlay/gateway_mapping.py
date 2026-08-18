from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .chat import ChatMessage


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
        return "[图片]"
    if "VIDEO" in attachment_types:
        return "[视频]"
    if "AUDIO" in attachment_types:
        return "[语音]"
    if attachment_types:
        return "[文件]"

    message_type = str(getattr(source, "type", "") or "").upper()
    if message_type == "STICKER":
        return "[表情]"
    if message_type == "IMAGE":
        return "[图片]"

    for field in ("text", "content"):
        value = getattr(source, field, "")
        if isinstance(value, str) and value:
            if value.startswith("![IMAGE"):
                return "[图片]"
            return _clean_text(value)
    return "[非文字消息]"


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
        or ("我" if sender_id == own_uid else sender_id[-6:] or "未知"),
        text=_text(source),
        mine=sender_id == own_uid,
    )
