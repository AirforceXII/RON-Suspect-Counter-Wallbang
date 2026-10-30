"""Read local x64 minidumps; stack words are candidates, not unwound frames."""
import collections
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def inspect(path):
    data = path.read_bytes()
    def u32(at): return struct.unpack_from('<I', data, at)[0]
    def u64(at): return struct.unpack_from('<Q', data, at)[0]
    assert data[:4] == b'MDMP'
    streams = {u32(at): (u32(at+4), u32(at+8))
               for at in range(u32(12), u32(12)+12*u32(8), 12)}
    modules = []
    _, at = streams[4]
    for i in range(u32(at)):
        off = at+4+i*108
        name_at = u32(off+20)
        name = data[name_at+4:name_at+4+u32(name_at)].decode('utf-16le')
        modules.append({'base':u64(off), 'size':u32(off+8), 'path':name})
    def label(ptr):
        for m in modules:
            if m['base'] <= ptr < m['base']+m['size']:
                return Path(m['path']).name+'+0x'+format(ptr-m['base'], 'x')
        return hex(ptr)
    threads = []
    _, at = streams[3]
    for i in range(u32(at)):
        off = at+4+i*48
        size, ctx = struct.unpack_from('<II',data,off+40)
        if size < 256: continue
        rip, rsp = u64(ctx+248), u64(ctx+152)
        start, length, stack_at = struct.unpack_from('<QII',data,off+24)
        words = []
        first = max(start,rsp)
        for address in range(first, min(start+length, first+8192), 8):
            ptr = u64(stack_at+address-start)
            text = label(ptr)
            if '+' in text:
                words.append({'stack_offset':hex(address-rsp), 'value':hex(ptr), 'module':text})
        threads.append({'tid':u32(off),'rip':hex(rip),'location':label(rip),'rsp':hex(rsp),
                        'registers':{r:hex(u64(ctx+pos)) for r,pos in
                                     [('rax',120),('rcx',128),('rdx',136),('rbx',144),
                                      ('rbp',160),('rsi',168),('rdi',176),('r8',184),('r9',192)]},
                        'stack_pointer_candidates_not_frames':words})
    report={'dump':str(path),'classification':'context registers and raw stack scan, not stack unwind',
            'modules':modules,'threads':threads}
    path.with_suffix('.scan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(path.name, 'threads:',len(threads))
    print('RIP groups:',collections.Counter(t['location'] for t in threads).most_common(12))
    for t in threads:
        own = [w for w in t['stack_pointer_candidates_not_frames'] if 'UE4SS' in w['module']]
        if own:
            print('UE4SS thread', t['tid'],t['location'],t['registers'])
            print(json.dumps(t['stack_pointer_candidates_not_frames'][:35]))
    return report

if __name__ == '__main__':
    for p in sorted((ROOT/'evidence/r8-live').glob('*.dmp')): inspect(p)
