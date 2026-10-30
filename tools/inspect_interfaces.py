"""Read current UHT function metadata; never access the running game."""
import hashlib
import argparse
import json
import struct
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_inspect import PEImage, DEFAULT_EXE

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe', type=Path, default=DEFAULT_EXE)
parser.add_argument('--names', nargs='+')
parser.add_argument('--output', type=Path, default=ROOT/'evidence/interfaces.json')
args = parser.parse_args()
exe = args.exe
p = PEImage(exe, exe.read_bytes())
b = p.data
def u64(va):
    return struct.unpack_from('<Q', b, p.va_to_off(va))[0]
def string(va):
    off = p.va_to_off(va)
    return b[off:b.index(b'\0', off)].decode('ascii')
def va_at(off):
    for s in p.sections:
        if s['raw_offset'] <= off < s['raw_offset'] + s['raw_size']:
            return p.image_base + s['virtual_address'] + off - s['raw_offset']
def hits(needle):
    start = 0
    while True:
        off = b.find(needle, start)
        if off < 0:
            break
        yield off
        start = off + 1

names = ['Multicast_TakeDamage', 'Multicast_InflictSuppression',
 'Multicast_InflictSuppression_NoLineOfSight', 'ScriptedFireAtActor',
 'ScriptedLookAtActor', 'StopScriptedFire', 'StopScriptedLook',
 'AddActivity', 'GetCombatActivity', 'EnterStrafeState', 'RequestMoveAsync',
 'AddKnownEnemy', 'SetLastTrackedTarget', 'AbortCover', 'AbortCoverLandmark',
 'DrawWeapon', 'GetCyberneticsController', 'GetEquippedWeapon',
 'IsSuspect', 'IsArrested', 'IsDeadOrUnconscious', 'GetGameTimeSinceCreation', 'IsMovingForRequest', 'AbortMove',
 'Multicast_SpawnImpactEffects', 'GetInstigator', 'GetOwner',
 'OnProjectileValidated', 'OnRespawnProjectile']
if args.names:
    names = args.names
rows = []
for name in names:
    for off in hits(name.encode() + b'\0'):
        if off and b[off - 1] != 0:
            continue
        nameva = va_at(off)
        if nameva is None:
            continue
        for ref in hits(struct.pack('<Q', nameva)):
            if ref < 16:
                continue
            rec = ref - 16
            owner = struct.unpack_from('<Q', b, rec)[0]
            count, size, rf, flags = struct.unpack_from('<HHII', b, rec + 48)
            if not (0x140001000 <= owner < 0x14640b600 and rf == 69 and count <= 40 and flags & 0x400):
                continue
            ptr = struct.unpack_from('<Q', b, rec + 40)[0]
            if count and p.va_to_off(ptr) is None:
                continue
            props = []
            for i in range(count):
                propva = u64(ptr + 8*i)
                pr = p.va_to_off(propva)
                props.append({'name': string(u64(propva)),
                  'generation_flags': hex(struct.unpack_from('<I', b, pr+24)[0]),
                  'flags': hex(u64(propva+16))})
            # UHT descriptors include enum backing properties. Only CPF_Parm
            # descriptors are runtime UFunction parameters (including returns).
            rows.append({'name': name, 'record': hex(va_at(rec)), 'owner_constructor': hex(owner),
                         'flags': hex(flags), 'params_size': size,
                         'parameters': [x for x in props if int(x['flags'],16) & 0x80],
                         'auxiliary_properties': [x for x in props if not int(x['flags'],16) & 0x80]})
result = {'exe': str(exe), 'exe_sha256': hashlib.sha256(b).hexdigest(),
          'classification': 'offline current-build UHT metadata, not live hook verification', 'functions': rows}
(ROOT/'evidence').mkdir(exist_ok=True)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
for r in rows:
    print(r['name'],r['owner_constructor'],[x['name'] for x in r['parameters']])
