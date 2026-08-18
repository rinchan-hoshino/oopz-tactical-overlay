from oopz_overlay.intent import OverlayAction, OverlayIntent


def test_enter_opens_only_while_tarkov_is_foreground() -> None:
    assert (
        OverlayIntent.enter(hidden=True, target_active=True, draft="").action
        is OverlayAction.SHOW
    )
    assert (
        OverlayIntent.enter(hidden=True, target_active=False, draft="").action
        is OverlayAction.NONE
    )


def test_enter_sends_trimmed_text_then_hides() -> None:
    decision = OverlayIntent.enter(
        hidden=False, target_active=True, draft="  二楼窗口一个  "
    )

    assert decision.action is OverlayAction.SEND_AND_HIDE
    assert decision.text == "二楼窗口一个"


def test_empty_enter_and_escape_hide_the_overlay() -> None:
    assert (
        OverlayIntent.enter(hidden=False, target_active=True, draft="   ").action
        is OverlayAction.HIDE
    )
    assert OverlayIntent.escape(hidden=False).action is OverlayAction.HIDE
    assert OverlayIntent.escape(hidden=True).action is OverlayAction.NONE
