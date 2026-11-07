import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / 'fixtures' / '0.12.0'

def test_core_available():
    assert importlib.util.find_spec('oopz_overlay.core'), 'pure core package is missing'

def test_schema8_migrates_losslessly_and_never_persists_credentials(tmp_path):
    from oopz_overlay.core.settings import AppSettings, JsonSettingsStore
    class Protector:
        def protect(self, data): return data[::-1]
        def unprotect(self, data): return data[::-1]
    raw = (FIXTURES / 'state-schema8.json').read_bytes()
    path = tmp_path / 'state.bin'
    path.write_bytes(raw[::-1])
    store = JsonSettingsStore(path, Protector())
    settings = store.load()
    for key, value in json.loads(raw).items():
        if key != 'schema_version':
            assert getattr(settings, key) == value
    assert settings.schema_version == 10
    assert settings.opacity == (38, 72)
    store.save(replace(settings, jwt_token='secret', device_id='device', person_uid='person'))
    assert 'secret' not in path.read_bytes()[::-1].decode()
    assert store.load() == settings
    assert not path.with_suffix('.bin.tmp').exists()

@pytest.mark.parametrize('raw', [{'position_x': float('nan')}, {'font_size': 99}, {'overlay_width': -5}])
def test_settings_clamp_external_values(raw):
    from oopz_overlay.core.settings import AppSettings
    s = AppSettings.from_dict(raw)
    assert 0 <= s.position_x <= 1 and 9 <= s.font_size <= 20 and s.overlay_width >= 0

def test_schema9_strength_migrates_effective_opacities_once():
    from oopz_overlay.core.settings import AppSettings
    s = AppSettings.from_dict({'schema_version':9, 'strength':70,
                               'text_opacity':72, 'backdrop_opacity':38})
    assert (s.backdrop_opacity, s.text_opacity) == (58, 88)
    assert 'strength' not in s.to_dict()
    assert AppSettings.from_dict(s.to_dict()) == s

def test_timeline_backfill_never_sounds_or_rehighlights_duplicates():
    from oopz_overlay.core.timeline import ChatMessage, Timeline
    t = Timeline(limit=3)
    def msg(key, stamp, mine=False): return ChatMessage(key, stamp, 'a', 'Alice', key, mine)
    assert not t.merge([msg('b', 2)], now=0, live=False)
    assert t.merge([msg('c', 3), msg('c', 3), msg('self', 4, True)], now=2, live=True) == ('c',)
    assert t.unread == 1
    assert t.merge([msg('b', 2), msg('c', 3)], now=3, live=True) == ()
    t.mark_read()
    assert t.unread == 0
    t.merge([msg('a', 1)], now=20, live=False)
    assert [m.message_id for m in t.items] == ['b', 'c', 'self']

def test_reducer_scopes_failed_drafts_and_ignores_stale_events():
    from oopz_overlay.core.state import AppState, reduce
    from oopz_overlay.core.settings import AppSettings
    s = AppState(settings=AppSettings(person_uid='a', area_id='s', channel_id='c'))
    s = reduce(s, 'draft', 'hello')
    s = reduce(s, 'submit')
    assert s.mode == 'passive' and s.draft == ''
    s = reduce(s, 'send_failed', (('a','s','c'), 'hello'))
    assert s.draft == 'hello'
    s = reduce(s, 'settings', replace(s.settings, channel_id='d'))
    assert s.draft == ''
    s = reduce(s, 'send_failed', (('a','s','c'), 'late'))
    assert s.draft == ''
    assert reduce(s, 'connected', True, generation=-1) == s
    s = reduce(s, 'settings', replace(s.settings, channel_id='c'))
    assert 'late' in s.draft and 'hello' in s.draft

def test_first_activation_picks_channel_and_visibility_is_independent():
    from oopz_overlay.core.state import AppState, reduce
    s = reduce(AppState(), 'activate')
    assert s.mode == 'picker'
    s = reduce(s, 'cancel')
    assert s.mode == 'passive'
    assert not reduce(s, 'toggle').visible

def test_core_imports_without_qt():
    import subprocess, sys
    code = "import sys; from oopz_overlay.core import settings,state,timeline; assert not any(k.startswith('PySide6') for k in sys.modules)"
    subprocess.run([sys.executable, '-c', code], check=True)

@pytest.mark.parametrize('raw', [{'channel_id': 42}, {'hotkey': []}, {'notification_sound': None}])
def test_settings_reject_invalid_external_strings(raw):
    from oopz_overlay.core.settings import AppSettings
    with pytest.raises(ValueError): AppSettings.from_dict(raw)

def test_bad_store_cannot_replace_existing_state(tmp_path):
    from oopz_overlay.core.settings import AppSettings, JsonSettingsStore
    class Protector:
        def protect(self,data): raise OSError('DPAPI refused')
        def unprotect(self,data): return data
    p=tmp_path/'state.bin'; p.write_bytes(b'[]')
    store=JsonSettingsStore(p,Protector())
    with pytest.raises(TypeError):store.load()
    with pytest.raises(OSError):store.save(AppSettings())
    assert p.read_bytes()==b'[]'

def test_reducer_connection_logout_and_nonmutating_drafts():
    from oopz_overlay.core.settings import AppSettings
    from oopz_overlay.core.state import AppState, reduce
    original=AppState(settings=AppSettings(person_uid='p',jwt_token='t',device_id='d',area_id='a',channel_id='c'))
    s=reduce(original,'draft','saved')
    assert original.draft==''
    s=reduce(s,'connection',3)
    assert s.generation==3 and not s.connected
    s=reduce(s,'connected',True,generation=3)
    assert s.connected and s.status=='connected'
    assert reduce(s,'connected',False).status=='reconnecting'
    assert reduce(s,'picker').mode=='picker'
    assert reduce(s,'input').mode=='input'
    assert reduce(s,'activate').mode=='input'
    assert reduce(s,'status','history_failed').status=='history_failed'
    s=reduce(s,'logout',4)
    assert not s.settings.has_credentials and s.generation==4 and s.draft==''
    assert s.drafts[('p','a','c')]=='saved'
    with pytest.raises(ValueError):reduce(s,'typo')

def test_timeline_ignores_empty_ids_sorts_ties_and_updates_existing_text():
    from oopz_overlay.core.timeline import ChatMessage, Timeline
    t=Timeline()
    a=ChatMessage('a',1,'x','X','old',False)
    t.merge([replace(a,message_id='b'),a,replace(a,message_id='')],now=0,live=True,reading=True)
    assert t.unread==0 and [m.message_id for m in t.items]==['a','b']
    assert not t.merge([replace(a,text='edited')],now=5,live=True)
    assert t.items[0].text=='edited'

def test_no_qt_in_translation_and_english_preserves_user_content(monkeypatch):
    from oopz_overlay.i18n import tr,language,ZH,EN
    monkeypatch.setenv('LC_ALL','en_US.UTF-8')
    assert language()=='en' and 'Ctrl+F8' in tr('choose',hotkey='Ctrl+F8')
    assert tr('#中文频道')=='#中文频道' and tr('[图片]')=='[Image]'
    assert ZH.keys()==EN.keys()

def test_timeline_requires_a_positive_history_limit():
    from oopz_overlay.core.timeline import Timeline
    with pytest.raises(ValueError): Timeline(limit=0)

def test_timeline_fades_after_reading_time_without_revealing_backfill_or_duplicates():
    from oopz_overlay.core.timeline import ChatMessage, Timeline
    t = Timeline()
    message = ChatMessage('new', 1, 'p', 'P', 'new', False)
    t.merge([message], now=20, live=True)
    assert t.opacity('new', now=27) == 1
    assert t.opacity('new', now=29) == .5
    assert t.opacity('new', now=30) == 0
    t.merge([message], now=31, live=True)
    assert t.opacity('new', now=31) == 0
    t.merge([replace(message, message_id='history')], now=31, live=False)
    assert t.opacity('history', now=31) == 0

def test_connection_readiness_requires_account_and_destination():
    from oopz_overlay.core.settings import AppSettings
    assert not AppSettings().is_ready
    s=AppSettings(person_uid='p',jwt_token='t',device_id='d')
    assert s.has_credentials and not s.is_ready
    assert replace(s,area_id='a',channel_id='c').is_ready


def test_timeline_discards_evicted_ids_without_renotifying_old_replays():
    from oopz_overlay.core.timeline import ChatMessage, Timeline
    timeline = Timeline(limit=3)
    for i in range(20):
        timeline.merge([ChatMessage(str(i), i, 'a', 'Alice', str(i), False)],
                       now=i, live=True)
    assert [m.message_id for m in timeline.items] == ['17', '18', '19']
    assert len(timeline._seen) <= 3
    assert len(timeline._arrivals) <= 3
    assert not timeline.merge([ChatMessage('0', 0, 'a', 'Alice', 'old', False)],
                              now=30, live=True)
    assert [m.message_id for m in timeline.items] == ['17', '18', '19']
    assert not timeline.merge([ChatMessage('19', 19, 'a', 'Alice', 'edited', False)],
                              now=31, live=True)
    assert timeline.items[-1].text == 'edited'
