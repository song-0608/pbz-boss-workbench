"""离线检查旧靶场AOB能否直接在当前PBZ文件匹配；不代表PBZ适配或实机地址验证。"""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import mmap
import re
import sys


def main():
    """用途：扫描实际可执行区段，明确旧靶场签名的适用范围，不把旧签名部署到游戏。"""
    sys.stdout.reconfigure(encoding="utf-8")
    home = Path(__file__).resolve().parent.parent
    sys.path.insert(0,str(home.parent/"tools"))
    from aob_lab import PE, parse_aob, find_matches
    source = home.parent / "lab/signatures/ue58-development-static-construct.lua"
    reference = re.search(r'return\s+"([0-9A-Fa-f? ]+)"',source.read_text(encoding="utf-8-sig"))
    if not reference:
        raise RuntimeError("未找到旧靶场的实际签名，停止，不能编造模式。")
    pattern = parse_aob(reference[1])
    preflight = json.loads((home/"evidence/latest-preflight.json").read_text(encoding="utf-8"))
    exe = Path(preflight["runtime_candidate"])
    with exe.open("rb") as stream:
        exe_hash = hashlib.file_digest(stream,"sha256").hexdigest()
    if exe_hash != next(p["sha256"] for p in preflight["program_candidates"] if p["path"]==str(exe)):
        raise RuntimeError("PBZ文件在前置检查后变化，需要重新做版本检查。")
    sections = []
    with exe.open("rb") as stream,mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
        pe=PE(data)
        for section in pe.sections:
            if not section["executable"] or not section["raw_size"]:
                continue
            examples=[]
            count=0
            for offset in find_matches(data,pattern,section["raw_offset"],section["raw_offset"]+section["raw_size"]):
                count+=1
                if len(examples)<20:
                    examples.append({"file_offset":offset,"rva":section["rva"]+offset-section["raw_offset"]})
            sections.append({"section":section["name"],"scanned_raw_bytes":section["raw_size"],"match_count":count,"first_matches":examples})
        token="Unreal Engine 5.7.4".encode("utf-16le")
        position=data.find(token)
    report={"checked_at":datetime.now().astimezone().isoformat(),"executable":str(exe),"sha256":exe_hash,
            "reference_signature_source":str(source),"reference_scope":"仅在自建UE5.8.1 Development靶场经PDB验证的对象构造函数签名，不是通用UE4SS全部内建签名",
            "pattern":reference[1],"pattern_bytes":len(pattern),"executable_sections":sections,
            "total_matches":sum(s["match_count"] for s in sections),
            "engine_string_evidence":{"text":"Unreal Engine 5.7.4","encoding":"utf-16le","file_offset":position if position>=0 else None,"meaning":"存在引擎版本字串，与先前线索一致；不证明自定义分支、布局或可执行代码全部未变化"},
            "runtime_addresses_verified":False,"ue4ss_loaded":False,"deployed":False,
            "limitations":["磁盘文件扫描不是运行内存扫描", "零匹配不能据此断言符号不存在或通用UE4SS一定失败", "唯一匹配也不能代替函数/全局变量语义和对象有效性验证", "不推断保护机制，不做解包或授权绕过"]}
    output=home/"evidence/reference-signature-check.json"
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
