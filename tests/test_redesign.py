from PySide6.QtWidgets import QApplication
from oopz_overlay.chat import ChatMessage
from oopz_overlay.message_widgets import MessageRow
from oopz_overlay.settings import AppSettings
from oopz_overlay.widgets import OverlayWindow


def test_passive_hud_empty_area_stays_transparent():
    app = QApplication.instance() or QApplication([])
    hud = OverlayWindow()
    hud.configure(AppSettings(backdrop_opacity=85))
    hud.set_connection_status('#test', True)
    hud.merge_messages([ChatMessage('one', 0, 'u', 'Player', 'Hello', False)])
    hud.show_passive()
    app.processEvents()
    image = hud.grab().toImage()
    assert image.pixelColor(hud.width() // 2, hud.height() - 20).alpha() == 0
    hud.hide()


def test_short_messages_have_fitted_backing_and_opacity_updates():
    app = QApplication.instance() or QApplication([])
    message = ChatMessage('one', 0, 'u', 'Player', 'Hello', False)
    alphas = []
    for opacity in (0, 32, 85):
        row = MessageRow(message, backdrop_opacity=opacity)
        row.resize(380, row.sizeHint().height())
        row.show()
        app.processEvents()
        image = row.grab().toImage()
        alphas.append(image.pixelColor(1, row.height() // 2).alpha())
        assert image.pixelColor(row.width() - 2, row.height() // 2).alpha() == 0
        row.close()
    assert alphas[0] == 0 < alphas[1] < alphas[2]


def test_english_interface_preserves_channel_names_and_message_content(monkeypatch):
    from PySide6.QtWidgets import QLabel
    from oopz_overlay.settings_dialog import SetupDialog
    for variable in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        monkeypatch.setenv(variable, 'en_US.UTF-8')
    app = QApplication.instance() or QApplication([])
    settings = AppSettings(area_id='server', area_name='中文服务器', channel_id='channel', channel_name='中文频道')
    dialog = SetupDialog(settings)
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert dialog.windowTitle() == 'TypeSlip'
    assert 'Preview' in labels
    assert dialog.server.text() == '中文服务器'
    assert '中文频道' in dialog.destination.currentText()
    row = MessageRow(ChatMessage('one', 0, 'u', '中文昵称', '中文消息', False))
    assert '中文消息' in [label.text() for label in row.findChildren(QLabel)]
    dialog.close()
    app.processEvents()


def test_preview_scene_comparison_changes_backdrop_and_preserves_draft():
    from oopz_overlay.settings_dialog import SetupDialog
    app = QApplication.instance() or QApplication([])
    dialog = SetupDialog(AppSettings())
    dialog.show()
    dialog.preview.set_mode('input')
    dialog.preview.composer.edit.setText('保留这条草稿')
    lightness = []
    for button in reversed(dialog.scene_buttons.buttons()):
        button.click()
        app.processEvents()
        preview = dialog.preview
        image = preview.grab().toImage()
        lightness.append(image.pixelColor(preview.width() // 2, 10).lightnessF())
        assert preview.composer.edit.text() == '保留这条草稿'
        assert len(preview._messages) == 3
    assert lightness[0] - lightness[1] > 0.35
    dialog.close()
