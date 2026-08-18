from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class OverlayAction(Enum):
    NONE = auto()
    SHOW = auto()
    HIDE = auto()
    SEND_AND_HIDE = auto()


@dataclass(frozen=True, slots=True)
class OverlayDecision:
    action: OverlayAction
    text: str = ""


class OverlayIntent:
    @staticmethod
    def enter(*, hidden: bool, target_active: bool, draft: str) -> OverlayDecision:
        if hidden:
            return OverlayDecision(
                OverlayAction.SHOW if target_active else OverlayAction.NONE
            )

        text = draft.strip()
        if not text:
            return OverlayDecision(OverlayAction.HIDE)
        return OverlayDecision(OverlayAction.SEND_AND_HIDE, text)

    @staticmethod
    def escape(*, hidden: bool) -> OverlayDecision:
        return OverlayDecision(OverlayAction.NONE if hidden else OverlayAction.HIDE)
