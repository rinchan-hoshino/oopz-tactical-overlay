from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatMessage:
    message_id: str
    timestamp_us: int
    sender_id: str
    sender_name: str
    text: str
    mine: bool
    pending: bool = False
    failed: bool = False


class ChatTimeline:
    def __init__(self, limit: int = 80) -> None:
        if limit < 1:
            raise ValueError("limit must be positive")
        self.limit = limit
        self._by_id: dict[str, ChatMessage] = {}

    @property
    def items(self) -> tuple[ChatMessage, ...]:
        ordered = sorted(
            self._by_id.values(),
            key=lambda item: (item.timestamp_us, item.message_id),
        )
        return tuple(ordered[-self.limit :])

    def merge(self, messages: list[ChatMessage] | tuple[ChatMessage, ...]) -> bool:
        changed = False
        for message in messages:
            if not message.message_id:
                continue
            if self._by_id.get(message.message_id) != message:
                self._by_id[message.message_id] = message
                changed = True

        ordered = sorted(
            self._by_id.values(),
            key=lambda item: (item.timestamp_us, item.message_id),
        )
        retained = ordered[-self.limit :]
        retained_ids = {item.message_id for item in retained}
        removed = set(self._by_id) - retained_ids
        if removed:
            changed = True
            for message_id in removed:
                del self._by_id[message_id]
        return changed
