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


def test_temporary_messages_allow_input_and_respect_manual_visibility(controller):
    c=controller
    c.configure(replace(c.state.settings, always_visible=False, channel_id='c'))
    c.gateway_event(GatewayEvent(c.state.generation, 'status', ('connected', True)))
    # The empty transparent window stays available to receive new messages.
    assert c.hud.isVisible()
    c.action('activate'); assert c.hud.isVisible()
    c.action('cancel'); assert c.hud.isVisible()
    c.action('toggle'); assert not c.hud.isVisible()
    c.configure(replace(c.state.settings, always_visible=True))
    assert not c.hud.isVisible()


def test_visibility_hotkey_can_show_messages_when_continuous_display_is_off(controller):
    c = controller
    c.configure(replace(c.state.settings, always_visible=False, channel_id='c'))
    c.gateway_event(GatewayEvent(c.state.generation, 'status', ('connected', True)))
    c.action('toggle')
    assert not c.hud.isVisible()
    c.action('toggle')
    assert c.hud.isVisible()


@pytest.mark.parametrize('selected', [False, True])
def test_activation_hotkey_toggles_and_returns_to_original_window(controller, monkeypatch, selected):
    c = controller
    c.state = replace(c.state, settings=AppSettings(channel_id='c' if selected else ''))
    foreground = [900]
    restored = []
    monkeypatch.setattr(module.win32, 'foreground_window', lambda: foreground[0])
    monkeypatch.setattr(module.win32, 'focus_window', lambda *args: True)
    monkeypatch.setattr(module.win32, 'restore_window', lambda handle, **kwargs: restored.append(handle))
    c.action('activate')
    assert c.state.mode == ('input' if selected else 'picker')
    c.action('draft', 'keep draft')
    foreground[0] = int(c.hud.winId())
    c.action('activate')
    assert c.state.mode == 'passive'
    assert c.state.draft == 'keep draft'
    assert restored == [900]


def test_blur_does_not_restore_focus_to_game(controller, monkeypatch):
    c = controller
    monkeypatch.setattr(module.win32, 'foreground_window', lambda: 900)
    restored = []
    monkeypatch.setattr(module.win32, 'restore_window', lambda *args, **kwargs: restored.append(args))
    c.action('activate')
    c.action('blur')
    assert c.state.mode == 'passive' and restored == []


def test_f9_exits_input_restores_focus_and_preserves_draft(controller, monkeypatch):
    c = controller
    c.state = replace(c.state, mode='input', settings=AppSettings(channel_id='c'))
    c._return_window = 900
    restored = []
    monkeypatch.setattr(module.win32, 'restore_window', lambda handle, **kwargs: restored.append(handle))
    c.action('draft', 'keep')
    c.action('toggle')
    assert c.state.mode == 'passive' and not c.hud.isVisible()
    assert c.state.draft == 'keep' and restored == [900]
    c.action('toggle')
    assert c.hud.isVisible() and c.state.mode == 'passive'


def test_incoming_burst_bounds_retained_messages_before_gui_catches_up(controller):
    import gc
    import weakref
    from oopz_overlay.core.timeline import ChatMessage

    class TrackedMessage(ChatMessage):
        pass

    c = controller
    c.poll.stop(); c.startup.stop(); c.update_timer.stop()
    retained = []

    def produce():
        for i in range(1000):
            message = TrackedMessage(str(i), i, 'u', 'Alice', 'long body ' + str(i), False)
            retained.append(weakref.ref(message))
            c.gateway.callbacks.event(GatewayEvent(0, 'live_timeline', ([message],)))

    import threading
    worker = threading.Thread(target=produce)
    worker.start(); worker.join(timeout=3)
    assert not worker.is_alive()
    gc.collect()
    assert sum(ref() is not None for ref in retained) <= 80
    c.application.processEvents()
    c.application.processEvents()
    assert [m.message_id for m in c.timeline.items] == [str(i) for i in range(920, 1000)]


def test_batched_history_live_and_stale_messages_keep_generation_and_notifications(controller, monkeypatch):
    from oopz_overlay.core.timeline import ChatMessage
    c = controller
    c.poll.stop(); c.startup.stop(); c.update_timer.stop()
    c.state = replace(c.state, generation=2)
    sounds = []
    monkeypatch.setattr(module.win32, 'play_sound', sounds.append)
    for generation, kind, message_id in [(1, 'live_timeline', 'stale'),
                                         (2, 'timeline', 'history'),
                                         (2, 'live_timeline', 'live')]:
        c.gateway.callbacks.event(GatewayEvent(generation, kind, ([
            ChatMessage(message_id, generation, 'u', 'Alice', message_id, False)],)))
    c.application.processEvents(); c.application.processEvents()
    assert {m.message_id for m in c.timeline.items} == {'history', 'live'}
    assert c.timeline.unread == 1
    assert len(sounds) == 1


def test_delayed_history_cannot_evict_newer_live_messages_from_pending_batch(controller):
    from oopz_overlay.core.timeline import ChatMessage
    c = controller
    c.poll.stop(); c.startup.stop(); c.update_timer.stop()
    post = c.gateway.callbacks.event
    post(GatewayEvent(0, 'live_timeline', ([ChatMessage('new', 1000, 'u', 'Alice', 'new', False)],)))
    post(GatewayEvent(0, 'timeline', ([ChatMessage(str(i), i, 'u', 'Alice', 'old', False)
                                      for i in range(80)],)))
    c.application.processEvents(); c.application.processEvents()
    assert len(c.timeline.items) == 80
    assert c.timeline.items[-1].message_id == 'new'
    assert c.timeline.unread == 1
