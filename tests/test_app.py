from dataclasses import replace
from types import SimpleNamespace
import pytest
from PySide6.QtWidgets import QApplication
from oopz_overlay import app as module
from oopz_overlay.core.settings import AppSettings
from oopz_overlay.adapters.oopz import GatewayEvent, OutgoingMessage

@pytest.fixture
def controller(monkeypatch,tmp_path):
    qapp=QApplication.instance() or QApplication([])
    class Protector:
        def protect(self,data): return data[::-1]
        def unprotect(self,data): return data[::-1]
    class Runtime:
        generation=0
        def __init__(self,callbacks): self.callbacks=callbacks; self.sent=[]
        def connect(self,settings): self.generation+=1
        def disconnect(self): self.generation+=1
        def close(self): pass
        def check_session(self): pass
        def list_channels(self,*args,**kwargs): pass
        def send(self,text): self.sent.append(text)
    monkeypatch.setattr(module,'WindowsDpapiProtector',Protector)
    monkeypatch.setattr(module,'GatewayRuntime',Runtime)
    monkeypatch.setattr(module,'state_root',lambda:tmp_path)
    c=module.AppController(qapp)
    yield c
    c.shutdown()

def test_first_run_has_hud_and_no_settings(controller):
    assert controller.hud.isVisible()
    assert controller.settings_window is None
    controller.action('activate')
    assert controller.state.mode=='picker'

def test_send_returns_passive_and_failure_restores_scoped_draft(controller):
    c=controller
    c.state=replace(c.state,settings=AppSettings(person_uid='me',area_id='a',channel_id='c'),connected=True,mode='input')
    c.action('draft','hello'); c.action('send','hello')
    assert c.state.mode=='passive' and c.gateway.sent==['hello'] and c.state.draft==''
    outgoing=OutgoingMessage('hello','a','c','me','rejected')
    c.gateway_event(GatewayEvent(0,'send_failed',(outgoing,)))
    assert c.state.draft=='hello' and c.state.connected
    c.action('activate')
    assert c.hud.input.text()=='hello'

def test_settings_preview_does_not_pollute_real_history(controller):
    c=controller
    c.open_settings()
    assert c.settings_window.preview.hud.messages.timeline.items and not c.timeline.items
    assert c.hud.messages.timeline is c.timeline
    assert not c.hud.isVisible()
    c.settings_window.close()
    assert c.hud.messages.timeline is c.timeline and c.hud.isVisible()

def test_logout_discards_connection_and_stale_timeline(controller):
    c=controller
    c.session_checked(None)
    assert c.state.status=='login'
    c.gateway_event(GatewayEvent(-1,'status',('#old',True)))
    assert not c.state.connected

def test_legacy_local_socket_opens_existing_settings(qapp=None):
    import tempfile
    from pathlib import Path
    from PySide6.QtNetwork import QLocalSocket
    from PySide6.QtTest import QTest
    app=QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        instance=module.SingleInstance(Path(directory))
        opened=[]; instance.activated.connect(lambda:opened.append(True))
        try:
            assert instance.acquire()
            client=QLocalSocket(); client.connectToServer(instance.name)
            assert client.waitForConnected(1000)
            client.write(b'settings'); client.waitForBytesWritten(1000)
            QTest.qWait(30)
            assert opened==[True]
            client.disconnectFromServer()
        finally: instance.close()


def test_adjust_position_uses_samples_and_returns_to_settings(controller):
    c=controller; c.open_settings(); c.settings_window.edit_button.click()
    assert c.hud.state.mode == 'adjust'
    assert c.hud.messages.timeline.items and not c.timeline.items
    assert not c.hud.composer.isVisible()
    c.action('cancel')
    assert c.settings_window.isVisible() and c.state.mode == 'passive'
    assert c.hud.messages.timeline is c.timeline


def test_connection_display_preference_does_not_hide_active_input(controller):
    c=controller
    c.configure(replace(c.state.settings, always_visible=False, channel_id='c'))
    c.gateway_event(GatewayEvent(c.state.generation, 'status', ('connected', True)))
    assert not c.hud.isVisible()
    c.action('activate'); assert c.hud.isVisible()
    c.action('cancel'); assert not c.hud.isVisible()
    c.configure(replace(c.state.settings, always_visible=True))
    assert c.hud.isVisible()


def test_visibility_hotkey_can_show_messages_when_continuous_display_is_off(controller):
    c = controller
    c.configure(replace(c.state.settings, always_visible=False, channel_id='c'))
    c.gateway_event(GatewayEvent(c.state.generation, 'status', ('connected', True)))
    assert not c.hud.isVisible()
    c.action('toggle')
    assert c.hud.isVisible()
