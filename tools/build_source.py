"""Bundle the development source, without downloaded binaries or game assets."""
import hashlib
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root/'output'
out.mkdir(exist_ok=True)
files = [root/n for n in ['README.md','SOURCE-中文.md','SPEC.md','requirements-dev.txt','VERSION','.gitignore']]
files += sorted(p for p in (root/'package').rglob('*') if p.is_file())
files += sorted((root/'tools').glob('*.py'))
files += [root/'tools/Capture-Hang.ps1']
files += [root/'evidence'/n for n in ['interfaces.json','offline-tests.json','package-review.json']]
files += [root/'evidence/r1-live-failure/diagnosis.md', root/'evidence/r2-installation.json']
files += [root/'evidence/r2-startup-crash/diagnosis.md', root/'evidence/r3-installation.json',
          root/'evidence/r4-installation.json', root/'evidence/r4-live/diagnosis.md',
          root/'evidence/r5-installation.json', root/'evidence/r5-live/diagnosis.md',
          root/'evidence/r6-installation.json', root/'evidence/r7-installation.json',
          root/'evidence/r7-live/diagnosis.md', root/'evidence/r8-installation.json',
          root/'evidence/r8-live/diagnosis.md', root/'evidence/r9-installation.json',
          root/'evidence/r9-live/diagnosis.md', root/'evidence/r9-live/crash-summary.json',
          root/'evidence/r10-installation.json', root/'evidence/r10-live/diagnosis.md',
          root/'evidence/r11-static/shot-interfaces.json', root/'evidence/r11-installation.json',
          root/'evidence/r11-live/diagnosis.md', root/'evidence/r12-change.json',
          root/'evidence/r12-installation.json', root/'evidence/r12-live/diagnosis.md',
          root/'evidence/r12-live/verification.json', root/'evidence/r12-live/multiplayer-feedback.json']
assert all(p.is_file() for p in files)
version = (root/'VERSION').read_text(encoding='utf-8').strip()
archive_path = out/f'ReactiveSuspects-{version}-Source.zip'
prefix = f'ReactiveSuspects-{version}-Source'
with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, prefix+'/'+p.relative_to(root).as_posix())
with zipfile.ZipFile(archive_path) as z:
    assert z.testzip() is None
    assert len(z.namelist()) == len(files)
    for p in files:
        assert z.read(prefix+'/'+p.relative_to(root).as_posix()) == p.read_bytes()
digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
(out/'Source-SHA256.txt').write_text(digest+'  '+archive_path.name+'\n',encoding='ascii')
print(archive_path)
print('Entries:',len(files),'Bytes:',archive_path.stat().st_size)
print('SHA256:',digest)
