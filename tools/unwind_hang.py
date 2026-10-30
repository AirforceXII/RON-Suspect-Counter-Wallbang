"""Bounded x64 .pdata unwind of game frames in saved local minidumps.

Stops at other modules/unsupported operations; not a complete debugger.
Reference: https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64
"""
import bisect
import json
import struct
from pathlib import Path
from native_inspect import PEImage, DEFAULT_EXE

ROOT = Path(__file__).resolve().parents[1]
image = PEImage(DEFAULT_EXE, DEFAULT_EXE.read_bytes())
for path in sorted((ROOT/'evidence/r8-live').glob('*.dmp')):
    b = path.read_bytes()
    def u32(o): return struct.unpack_from('<I', b, o)[0]
    def u64(o): return struct.unpack_from('<Q', b, o)[0]
    dirs = {u32(o):u32(o+8) for o in range(u32(12),u32(12)+12*u32(8),12)}
    scan = json.loads(path.with_suffix('.scan.json').read_text())
    mod = next(m for m in scan['modules'] if Path(m['path']).name == DEFAULT_EXE.name)
    results = []
    for i in range(u32(dirs[3])):
        off = dirs[3]+4+48*i
        ctx = u32(off+44)
        rip = u64(ctx+248)
        if not mod['base'] <= rip < mod['base']+mod['size']: continue
        start, size, raw = struct.unpack_from('<QII',b,off+24)
        def mem(address):
            if not start <= address <= start+size-8: raise ValueError('outside saved stack')
            return u64(raw+address-start)
        regs = [u64(ctx+120+j*8) for j in range(16)]
        frames = []
        reason = 'frame_limit'
        try:
            for depth in range(48):
                rva = rip-mod['base']
                if not 0 <= rva < mod['size']:
                    reason = 'left game module'; break
                index = bisect.bisect_right(image.runtime_starts,rva-(depth>0))-1
                fn = image.runtime_functions[index] if index >= 0 else None
                if fn is not None and not fn['begin_rva'] <= rva-(depth>0) < fn['end_rva']: fn=None
                frames.append({'rip':hex(rip),'rva':hex(rva),'rsp':hex(regs[4]),
                               'function_rva':hex(fn['begin_rva']) if fn else 'leaf'})
                if fn:
                    uw = fn['unwind_rva']
                    for chain in range(12):
                        pos = image.rva_to_off(uw)
                        vflags, prolog, count, fp = struct.unpack_from('<BBBB',image.data,pos)
                        if vflags&7 != 1: raise ValueError('unsupported unwind version')
                        framereg, frameoff = fp&15, fp>>4
                        fixed = regs[framereg]-frameoff*16 if framereg else regs[4]
                        j=0
                        while j<count:
                            delta, code = struct.unpack_from('<BB',image.data,pos+4+2*j)
                            op, info = code&15, code>>4
                            length={0:1,1:2 if info==0 else 3,2:1,3:1,4:2,5:3,8:2,9:3}.get(op)
                            if length is None: raise ValueError('unsupported unwind opcode '+str(op))
                            extra = pos+6+2*j
                            if rva-fn['begin_rva'] >= delta:
                                if op==0: regs[info]=mem(regs[4]); regs[4]+=8
                                elif op==1: regs[4]+=struct.unpack_from('<H' if info==0 else '<I',image.data,extra)[0]*(8 if info==0 else 1)
                                elif op==2: regs[4]+=info*8+8
                                elif op==3: regs[4]=regs[framereg]-frameoff*16
                                elif op in (4,5): regs[info]=mem(fixed+struct.unpack_from('<H' if op==4 else '<I',image.data,extra)[0]*(8 if op==4 else 1))
                            j+=length
                        if not (vflags>>3)&4: break
                        begin,end,uw = struct.unpack_from('<III',image.data,pos+4+2*((count+1)&~1))
                    else: raise ValueError('unwind chain limit')
                oldsp=regs[4]
                rip=mem(oldsp); regs[4]+=8
                if regs[4] <= int(frames[-1]['rsp'],16): raise ValueError('non-increasing stack')
        except (ValueError,struct.error) as e: reason=str(e)
        results.append({'tid':u32(off),'frames':frames,'stop_reason':reason})
        print(path.name,'thread',u32(off),'stop:',reason)
        print(' -> '.join(f["rva"]+' ['+f['function_rva']+']' for f in frames[:20]))
    path.with_suffix('.unwind.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
