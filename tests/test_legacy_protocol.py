import json
import time
from pathlib import Path
import pytest

FIX = Path(__file__).parent / 'fixtures' / '0.12.0'

def test_old_generated_manifest_is_accepted():
    from oopz_overlay.adapters.updater import parse_manifest
    m = parse_manifest((FIX / 'latest.json').read_bytes())
    assert (m.version, m.size, m.sha256) == ('0.12.0', 52, '84240ea7d8e3fc710d1a3b8fb12991a1341a8a91a2f3a92a9150387599815a01')

@pytest.mark.parametrize('field,value', [('url','https://acv.k-neco.com.evil.test/app.exe'), ('url','http://acv.k-neco.com/app.exe'), ('sha256','x'*64), ('size',0)])
def test_rejects_invalid_manifest(field,value):
    from oopz_overlay.adapters.updater import parse_manifest
    raw = json.loads((FIX / 'latest.json').read_bytes()); raw[field] = value
    with pytest.raises(ValueError): parse_manifest(json.dumps(raw).encode())

def test_old_apply_command_stages_on_target_volume(tmp_path, monkeypatch):
    from oopz_overlay.adapters import updater
    commands = json.loads((FIX / 'commands.json').read_text())
    args = [a.replace('{root}', str(tmp_path)) for a in commands[0][1:]]
    target, source, pending = Path(args[1]), Path(args[2]), Path(args[4])
    target.write_bytes(b'old')
    source.parent.mkdir(); source.write_bytes((FIX / 'payload.bin').read_bytes())
    pending.write_text((FIX / 'pending-update.json').read_text())
    launches = []
    monkeypatch.setattr(updater, '_launch_target', launches.append)
    monkeypatch.setattr(updater, '_wait_for_process', lambda _: None)
    real_replace = updater.os.replace
    def same_volume_only(src,dst):
        assert Path(src).parent.parent == target.parent
        real_replace(src,dst)
    monkeypatch.setattr(updater.os, 'replace', same_volume_only)
    assert updater.handle_update_arguments(args) == 0
    assert target.read_bytes() == (FIX / 'payload.bin').read_bytes()
    assert not pending.exists() and not source.exists()
    assert launches == [target]

def test_old_cleanup_command_removes_helper_without_exiting_app(tmp_path):
    from oopz_overlay.adapters.updater import handle_update_arguments
    command = json.loads((FIX / 'commands.json').read_text())[1]
    args = [a.replace('{root}',str(tmp_path)) for a in command[1:]]
    helper = Path(args[1]); helper.write_bytes(b'helper')
    assert handle_update_arguments(args) is None
    deadline = time.monotonic() + 2
    while helper.exists() and time.monotonic() < deadline: time.sleep(.01)
    assert not helper.exists()

def test_instance_name_matches_012_generated_name():
    from oopz_overlay.adapters.win32 import instance_name
    sample = json.loads((FIX / 'instance.json').read_text())
    assert instance_name(Path(sample['state_root'])) == sample['name']

@pytest.mark.parametrize('args',[['--apply-update'],['--cleanup-updater']])
def test_incomplete_helper_arguments_fail_without_mutating_files(args):
    from oopz_overlay.adapters.updater import handle_update_arguments
    assert handle_update_arguments(args) == 2
