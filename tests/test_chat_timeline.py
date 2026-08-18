from oopz_overlay.chat import ChatMessage, ChatTimeline


def message(message_id: str, timestamp_us: int, text: str = "收到") -> ChatMessage:
    return ChatMessage(
        message_id=message_id,
        timestamp_us=timestamp_us,
        sender_id="u1",
        sender_name="黑夜",
        text=text,
        mine=False,
    )


def test_history_is_ordered_deduplicated_and_bounded() -> None:
    timeline = ChatTimeline(limit=3)

    changed = timeline.merge(
        [
            message("m2", 2),
            message("m1", 1),
            message("m2", 2, "重复事件"),
            message("m4", 4),
            message("m3", 3),
        ]
    )

    assert changed is True
    assert [item.message_id for item in timeline.items] == ["m2", "m3", "m4"]
    assert timeline.items[0].text == "重复事件"


def test_merge_reports_no_change_for_identical_replay() -> None:
    timeline = ChatTimeline(limit=10)
    item = message("m1", 1)

    assert timeline.merge([item]) is True
    assert timeline.merge([item]) is False
