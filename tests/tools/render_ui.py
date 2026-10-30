"""Render the real widgets offscreen; never enters the application/network runtime."""
import argparse
import os
from dataclasses import replace
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['LC_ALL'] = 'zh_CN.UTF-8'
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from oopz_overlay.core.settings import AppSettings
from oopz_overlay.core.state import AppState
from oopz_overlay.core.timeline import Timeline, ChatMessage
from oopz_overlay.ui.hud import Hud
from oopz_overlay.ui.settings_window import SettingsWindow
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=Path('/Users/rin/.rin/work/typeslip/shots'))
options = parser.parse_args()
options.output.mkdir(parents=True, exist_ok=True)
app = QApplication([])
settings = AppSettings(area_id='a', channel_id='c', channel_name='战术交流', font_size=13)
state = AppState(settings=settings, connected=True, status='connected')
now = monotonic()
timeline = Timeline()
timeline.merge([ChatMessage('old', 1775000000000000, 'one', 'Lin', '二楼窗口一个', False)], now=now - 15, live=True)
timeline.merge([ChatMessage('new1', 1775000005000000, 'two', 'Mika', '收到，我绕右侧', True), ChatMessage('new2', 1775000009000000, 'one', 'Lin', '等一下，楼梯有脚步', False)], now=now, live=True)
channels = [SimpleNamespace(area_id='a', area_name='猫尾服务器', channel_id=str(i), channel_name=name) for i, name in enumerate(('战术交流', '综合文字', '组队大厅'))]
hud = Hud()
hud.resize(420, 190)
hud.show()
for mode in ('passive', 'input', 'picker'):
    view = replace(state, mode=mode, drafts={state.key: '收到，正在靠近'} if mode == 'input' else {})
    hud.render(view, timeline, channels)
    app.processEvents()
    assert hud.grab().save(str(options.output / f'hud-{mode}.png'))
for name, status in (('first-run', 'starting'), ('login', 'login')):
    hud.render(AppState(status=status), Timeline(), ())
    app.processEvents()
    assert hud.grab().save(str(options.output / f'hud-{name}.png'))
# Offscreen has no OS appearance notifications; exercise native palette roles
# with Fusion, which also avoids platform-specific decoration in these captures.
app.setStyle('Fusion')
light_palette = app.palette()
dark_palette = QPalette(light_palette)
for role, color in {
    QPalette.ColorRole.Window: '#242424',
    QPalette.ColorRole.WindowText: '#eeeeee',
    QPalette.ColorRole.Base: '#191919',
    QPalette.ColorRole.AlternateBase: '#303030',
    QPalette.ColorRole.Text: '#eeeeee',
    QPalette.ColorRole.Button: '#343434',
    QPalette.ColorRole.ButtonText: '#eeeeee',
    QPalette.ColorRole.Highlight: '#528bcc',
    QPalette.ColorRole.HighlightedText: '#ffffff',
}.items():
    dark_palette.setColor(role, QColor(color))
window = SettingsWindow(settings)
window.set_update_status('已是最新版本')
window.show()
for name, palette in (('light', light_palette), ('dark', dark_palette)):
    app.setPalette(palette)
    app.processEvents()
    assert window.grab().save(str(options.output / f'settings-{name}.png'))
window.close()
hud.close()
print(options.output)
