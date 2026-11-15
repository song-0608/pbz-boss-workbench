"""用途：只读核对 PBZ 磁盘程序，寻找指定字串交叉引用并反汇编；不启动游戏。"""
from pathlib import Path
from datetime import datetime
import argparse
import bisect
import hashlib
import json
import mmap
import re
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / 'workbench/python-libs'))
sys.path.insert(0, str(ROOT.parent / 'tools'))
from aob_lab import PE
import capstone

EXE = Path(r'E:\SteamLibrary\steamapps\common\PBZ\platform\steam\PBZ.exe')
EXPECTED = '4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423'


class Analysis:
    def __init__(self):
        # 用途：只接受已经登记过的原版文件，防止把另一版本的地址沿用到当前实验。
        self.stream = EXE.open('rb')
        self.sha256 = hashlib.file_digest(self.stream, 'sha256').hexdigest()
        if self.sha256 != EXPECTED:
            raise RuntimeError('PBZ version changed: stop and review hashes')
        self.data = mmap.mmap(self.stream.fileno(), 0, access=mmap.ACCESS_READ)
        self.pe = PE(self.data)
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        # 用途：异常表由 PE 数据目录给出，不依赖可能被链接器合并/改名的 .pdata 区段名称。
        pe_header=struct.unpack_from('<I',self.data,0x3c)[0]
        exception_rva,exception_size=struct.unpack_from('<II',self.data,pe_header+24+112+3*8)
        exception_offset=self.pe.rva_to_file(exception_rva)
        self.functions = sorted(struct.iter_unpack('<III', self.data[exception_offset:exception_offset+exception_size-(exception_size%12)]))
        self.starts = [row[0] for row in self.functions]

    def function(self, rva):
        # 用途：利用 Windows x64 异常表定位所属函数范围；分离的冷代码块仍可能是独立条目。
        index = bisect.bisect_right(self.starts, rva)-1
        if index >= 0:
            start, end, unwind = self.functions[index]
            if start <= rva < end:
                return {'start_rva':hex(start), 'end_rva':hex(end), 'unwind_rva':hex(unwind)}
        return None

    def disasm(self, rva, length):
        position = self.pe.rva_to_file(rva)
        result=[]
        for ins in self.md.disasm(self.data[position:position+length], self.pe.image_base+rva):
            row={'rva':hex(ins.address-self.pe.image_base), 'bytes':ins.bytes.hex(' '), 'instruction':ins.mnemonic+' '+ins.op_str}
            targets=[]
            for operand in ins.operands:
                if operand.type == capstone.x86.X86_OP_MEM and operand.mem.base == capstone.x86.X86_REG_RIP:
                    target=ins.address+ins.size+operand.mem.disp-self.pe.image_base
                    targets.append(hex(target))
            if targets:row['rip_target_rvas']=targets
            result.append(row)
        return result

    def xrefs(self, rvas):
        # 用途：先用 RIP 相对寻址的字节形状筛选，再由反汇编器核对完整指令和目标。
        wanted=set(rvas);found=[]
        rx=re.compile(rb'[\x48\x4c][\x8d\x8b\x89][\x05\x0d\x15\x1d\x25\x2d\x35\x3d][\s\S]{4}')
        for section in self.pe.sections:
            if not section['executable']:continue
            start=section['raw_offset'];end=start+section['raw_size']
            for match in rx.finditer(self.data,start,end):
                pos=match.start();rva=self.pe.file_to_rva(pos)
                target=rva+7+struct.unpack_from('<i',self.data,pos+3)[0]
                if target not in wanted:continue
                instructions=self.disasm(rva,7)
                if len(instructions)!=1 or instructions[0].get('rip_target_rvas') != [hex(target)]:continue
                found.append({'instruction_rva':hex(rva),'target_rva':hex(target),'function':self.function(rva), **instructions[0]})
        return found

    def strings(self, text):
        found=[]
        for encoding in ('utf-16le','ascii'):
            token=text.encode(encoding);start=0
            while True:
                pos=self.data.find(token,start)
                if pos<0:break
                try:rva=self.pe.file_to_rva(pos)
                except ValueError:start=pos+1;continue
                found.append({'encoding':encoding,'rva':hex(rva),'file_offset':hex(pos)})
                start=pos+1
        return {'text':text,'matches':found,'xrefs':self.xrefs(int(row['rva'],16) for row in found)}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--string',action='append',default=[])
    parser.add_argument('--rva',action='append',default=[])
    parser.add_argument('--xref',action='append',default=[])
    parser.add_argument('--length',type=lambda s:int(s,0),default=0x180)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if not 0<args.length<=0x10000:raise ValueError('Bounded disassembly length required')
    if not args.output.resolve().is_relative_to((ROOT/'evidence').resolve()):raise ValueError('Keep reports in this project evidence')
    a=Analysis()
    report={'at':datetime.now().astimezone().isoformat(),'exe_sha256':a.sha256,'scope':'read-only on-disk PE; preferred image addresses, not verified live objects',
            'image_base':hex(a.pe.image_base),'strings':[a.strings(s) for s in args.string],
            'disassembly':[{'rva':r,'function':a.function(int(r,0)),'instructions':a.disasm(int(r,0),args.length)} for r in args.rva],
            'xrefs':a.xrefs(int(r,0) for r in args.xref) if args.xref else []}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
