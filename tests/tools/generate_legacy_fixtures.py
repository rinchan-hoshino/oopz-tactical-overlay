"""Run 0.12.0 serialization/protocol code; no network, credentials or executables.

The executable payload is synthetic. DPAPI ciphertext must be tested on Windows;
state-schema8.json is the exact plaintext passed to CryptProtectData.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from datetime import UTC, datetime

COMMIT = '55f7cd08c0ba744535fed96a28bb95e7bc493498'
OUT = Path(__file__).resolve().parents[1] / 'fixtures' / '0.12.0'

def source(path):
    return subprocess.check_output(['git', 'show', f'{COMMIT}:{path}'], text=True)

def module(name, path):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    exec(compile(source(path), path, 'exec'), mod.__dict__)
    return mod

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

OUT.mkdir(parents=True, exist_ok=True)
settings = module('legacy_settings', 'src/oopz_overlay/settings.py')
updater = module('legacy_updater', 'src/oopz_overlay/updater.py')
class Capture:
    def protect(self, data):
        (OUT / 'state-schema8.json').write_bytes(data)
        return data

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    settings.JsonSettingsStore(root / 'state.bin', Capture()).save(settings.AppSettings(
        area_id='area-012', area_name='猫尾服务器', channel_id='text-012',
        channel_name='战术交流', screen_name='DISPLAY2', hotkey='Ctrl+F8',
        visibility_hotkey='Alt+F9', position_x=.74, position_y=.66,
        overlay_width=412, overlay_height=188, font_size=18, text_opacity=72,
        backdrop_opacity=38, notification_sound='Windows Notify.wav', always_visible=False))
    payload = b'TypeSlip protocol fixture; not a Windows executable\n'
    target = root / 'OopzTacticalOverlay.exe'
    target.write_bytes(payload)
    # Execute the original build's manifest assignment, without running Nuitka.
    build = ast.parse(source('tools/build_windows.py'))
    assignment = next(n for n in ast.walk(build) if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'manifest' for t in n.targets))
    ns = dict(version='0.12.0', PUBLIC_BASE='https://acv.k-neco.com/tools/oopz-tactical-overlay',
              PRODUCT='OopzTacticalOverlay', digest=hashlib.sha256(payload).hexdigest(),
              target=target, datetime=datetime, UTC=UTC)
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), '<legacy build>', 'exec'), ns)
    save('latest.json', ns['manifest'])
    manifest = updater.parse_manifest(json.dumps(ns['manifest']).encode())
    updater.fetch_manifest = lambda: manifest
    def download(item, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    updater.download_verified = download
    updater.stage_update('0.11.0', root)
    pending = json.loads((root / 'pending-update.json').read_text())
    pending['path'] = pending['path'].replace(str(root), '{root}')
    save('pending-update.json', pending)
    updater.is_packaged = lambda: True
    updater._running_executable = lambda: target
    updater.tempfile.gettempdir = lambda: str(root)
    calls = []
    original_popen = subprocess.Popen
    updater.subprocess.Popen = lambda argv, **kw: calls.append(argv)
    updater.start_pending_update(root, '0.11.0')
    updater._running_executable = lambda: Path(calls[0][0])
    updater._launch_target(target)
    save('commands.json', [[arg.replace(str(root), '{root}') for arg in call] for call in calls])
    (OUT / 'payload.bin').write_bytes(payload)
    subprocess.Popen = original_popen

instance = ast.parse(source('src/oopz_overlay/instance.py'))
assignment = next(n for n in ast.walk(instance) if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Attribute) and t.attr == 'name' for t in n.targets))
obj = types.SimpleNamespace()
state_root = Path(r'C:\Users\Player\AppData\Local\RinChan\OopzTacticalOverlay')
exec(compile(ast.Module(body=[assignment], type_ignores=[]), '<legacy instance>', 'exec'),
     dict(self=obj, state_root=state_root, hashlib=hashlib))
save('instance.json', dict(state_root=str(state_root), name=obj.name))
save('provenance.json', dict(commit=COMMIT, version='0.12.0',
    note='Executed legacy settings store, updater and build manifest assignment; synthetic executable bytes; DPAPI plaintext only.'))
