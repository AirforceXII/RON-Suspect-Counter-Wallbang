import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root/'package'
out = root/'output'
out.mkdir(exist_ok=True)
version = (root/'VERSION').read_text(encoding='utf-8').strip()
target = out/f'ReactiveSuspects-{version}-HostOnly-UE4SS.zip'
files = sorted(p for p in source.rglob('*') if p.is_file())
with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.relative_to(source).as_posix())
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert set(archive.namelist()) == {p.relative_to(source).as_posix() for p in files}
    for path in files:
        assert archive.read(path.relative_to(source).as_posix()) == path.read_bytes()
main_hash = hashlib.sha256((source/'Mods/ReactiveSuspects/Scripts/main.lua').read_bytes()).hexdigest()
test_path = root/'evidence/offline-tests.json'
test_report = json.loads(test_path.read_text(encoding='utf-8')) if test_path.exists() else {}
test_matches = test_report.get('main_lua_sha256') == main_hash
cases = test_report.get('checks', [])
test_status = (len(cases) if test_matches and cases and all(c.get('pass') is True for c in cases)
               else 'NOT_TESTED_FOR_THIS_SOURCE')
report = {'archive': str(target), 'bytes': target.stat().st_size,
          'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'entries': [{'path':p.relative_to(source).as_posix(), 'bytes':p.stat().st_size,
                      'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
          'archive_roundtrip':'PASS', 'lua54_offline_cases':test_status,
          'installer_copy_and_backup':'not executed by this packaging command',
          'game_installation':'NOT_PERFORMED', 'gameplay':'NOT_TESTED',
          'unmodified_client_multiplayer':'NOT_TESTED'}
(root/'evidence/package-review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(out/'SHA256.txt').write_text(report['sha256']+'  '+target.name+'\n',encoding='ascii')
print(json.dumps(report,indent=2))
