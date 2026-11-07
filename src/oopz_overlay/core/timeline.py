"""Deterministic history/live merge and notification decisions, with no UI clock."""
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class ChatMessage:
    message_id: str
    timestamp_us: int
    sender_id: str
    sender_name: str
    text: str
    mine: bool

@dataclass
class Timeline:
    limit: int = 80
    unread: int = 0
    _messages: dict[str, ChatMessage] = field(default_factory=dict)
    _seen: set[str] = field(default_factory=set)
    _arrivals: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if self.limit < 1:
            raise ValueError('limit must be positive')

    def opacity(self, message_id: str, *, now: float) -> float:
        return max(0.0, min(1.0, (10 - (now - self._arrivals.get(message_id, now - 12))) / 2))

    @property
    def items(self) -> tuple[ChatMessage, ...]:
        return tuple(sorted(self._messages.values(), key=lambda m: (m.timestamp_us, m.message_id)))

    def merge(self, messages, *, now: float, live: bool, reading: bool=False) -> tuple[str, ...]:
        notify = []
        for message in messages:
            key = message.message_id
            if not key:
                continue
            if key not in self._seen:
                self._seen.add(key)
                self._arrivals[key] = now if live else now - 12
                if live and (not message.mine):
                    notify.append(key)
            self._messages[key] = message
        self._messages = {m.message_id: m for m in self.items[-self.limit:]}
        self._seen.intersection_update(self._messages)
        self._arrivals = {k: t for k, t in self._arrivals.items() if k in self._messages}
        notify = [key for key in notify if key in self._messages]
        if not reading:
            self.unread += len(notify)
        return tuple(notify)

    def mark_read(self) -> None:
        self.unread = 0
