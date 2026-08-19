from oopz_overlay.gateway import Destination, GatewayRuntime
from oopz_overlay.settings import AppSettings


def test_sdk_configuration_uses_the_local_oopz_session() -> None:
    settings = AppSettings(
        device_id="device",
        person_uid="person",
        jwt_token="token",
        app_version="70000",
        area_id="area",
        channel_id="channel",
    )

    config = GatewayRuntime._config(settings)

    assert config.device_id == "device"
    assert config.person_uid == "person"
    assert config.jwt_token == "token"
    assert config.app_version == "70000"
    assert config.auto_subscribe_joined_areas is False


def test_destination_label_is_the_manually_selectable_channel_name() -> None:
    destination = Destination("area", "猫尾服务器", "channel", "综合文字")

    assert destination.label == "#综合文字"
