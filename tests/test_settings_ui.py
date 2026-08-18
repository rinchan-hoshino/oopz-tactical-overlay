from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

from oopz_overlay import __version__
from oopz_overlay.gateway import Destination, LoginResult
from oopz_overlay.settings import AppSettings
from oopz_overlay.widgets import SetupDialog


def test_channel_refresh_preserves_selection_and_changes_apply_immediately() -> None:
    app = QApplication.instance() or QApplication([])
    current = AppSettings(
        device_id="d",
        person_uid="p",
        jwt_token="j",
        area_id="owned",
        area_name="猫尾黑夜的西瓜田",
        channel_id="general",
        channel_name="综合文字",
    )
    dialog = SetupDialog(current)
    observed: list[AppSettings] = []
    dialog.settings_changed.connect(observed.append)
    dialog.show()
    app.processEvents()

    dialog.apply_login_result(
        LoginResult(
            current,
            (
                Destination("owned", "猫尾黑夜的西瓜田", "home", "主页"),
                Destination("owned", "猫尾黑夜的西瓜田", "general", "综合文字"),
            ),
            current_area_id="owned",
            current_area_name="猫尾黑夜的西瓜田",
            detected_live=True,
        )
    )
    selected = dialog.destination.currentData()

    assert isinstance(selected, Destination)
    assert (selected.area_id, selected.channel_id) == ("owned", "general")
    assert dialog.server.text() == "猫尾黑夜的西瓜田"
    assert dialog.sync_button.property("action") is True
    assert dialog.drag_button.property("action") is True
    assert dialog.font_size.currentData() == 12
    assert not hasattr(dialog, "process")
    assert dialog.version.text() == f"v{__version__}"
    assert dialog.update_status.text() == "更新 // 等待自动检查"
    dialog.set_update_status("更新 // 正在下载 v9.9.9 · 42%")
    assert dialog.update_status.text().endswith("42%")
    dialog.always_visible.setChecked(False)
    dialog.font_size.setCurrentIndex(dialog.font_size.findData(18))
    app.processEvents()
    assert observed[-1].always_visible is False
    assert observed[-1].font_size == 18
    assert observed[-1].channel_id == "general"
    assert dialog.isVisible()
    assert not any(
        button.text() in {"取消", "使用此频道"}
        for button in dialog.findChildren(QPushButton)
    )

    dialog.close()
