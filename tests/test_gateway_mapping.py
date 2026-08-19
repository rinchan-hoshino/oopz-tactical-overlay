from types import SimpleNamespace

from oopz_sdk.models.message import Message

from oopz_overlay.gateway_mapping import (
    choose_current_area,
    map_message,
    merge_area_payloads,
)


def test_map_message_prefers_plain_text_and_marks_own_message() -> None:
    source = SimpleNamespace(
        message_id="42",
        timestamp="1718285266584264",
        sender_id="me",
        plain_text="左边一个",
        text="ignored",
        content="ignored",
    )

    result = map_message(source, names={"me": "澪子"}, own_uid="me")

    assert result.message_id == "42"
    assert result.timestamp_us == 1718285266584264
    assert result.sender_name == "澪子"
    assert result.text == "左边一个"
    assert result.mine is True


def test_area_sources_merge_owned_domain_without_duplicate_subscription() -> None:
    joined = [{"id": "area-a", "name": "猫鱼贴贴"}]
    home = [
        {"id": "area-a", "name": "猫鱼贴贴", "top": True},
        {"id": "area-owned", "name": "猫尾黑夜的西瓜田"},
    ]

    merged = merge_area_payloads(joined, home)

    assert [item["id"] for item in merged] == ["area-a", "area-owned"]
    assert merged[0]["top"] is True


def test_current_voice_server_wins_and_previous_server_is_only_a_fallback() -> None:
    area_ids = ["area-a", "area-b"]

    assert choose_current_area(area_ids, {"area-b": "voice-1"}, "area-a") == (
        "area-b",
        True,
    )
    assert choose_current_area(area_ids, {}, "area-a") == ("area-a", False)
    assert choose_current_area(area_ids, {}, "missing") == ("", False)


def test_non_text_messages_get_readable_placeholders_and_controls_are_removed() -> None:
    image = SimpleNamespace(
        message_id="img",
        timestamp="1",
        sender_id="user",
        plain_text="",
        text="![IMAGEw240h240](/im/a.webp)",
        content="![IMAGEw240h240](/im/a.webp)",
        attachments=[SimpleNamespace(attachment_type="IMAGE")],
        type="TEXT",
    )
    bidi = SimpleNamespace(
        message_id="text",
        timestamp="2",
        sender_id="user",
        plain_text="\u2066九十九\u2069#\u206681385\u2069",
        text="",
        content="",
        attachments=[],
        type="TEXT",
    )

    assert map_message(image, names={"user": "风屿"}, own_uid="me").text == "[图片]"
    assert (
        map_message(bidi, names={"user": "风屿"}, own_uid="me").text == "九十九#81385"
    )


def test_mapping_accepts_the_pinned_sdk_message_model() -> None:
    message = Message.model_validate(
        {
            "messageId": "m-sdk",
            "timestamp": "1775000000000000",
            "person": "u-sdk",
            "area": "a-1",
            "channel": "c-1",
            "content": "楼梯有人",
        }
    )

    mapped = map_message(message, names={"u-sdk": "队友"}, own_uid="owner")

    assert mapped.message_id == "m-sdk"
    assert mapped.timestamp_us == 1_775_000_000_000_000
    assert mapped.sender_name == "队友"
    assert mapped.text == "楼梯有人"
