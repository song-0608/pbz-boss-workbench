"""用途：只读解析Steam小型转储的异常和模块地址；不输出内存内容或登录资料。"""
from pathlib import Path
import struct
import json
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent


def inspect(path):
    data = path.read_bytes()
    if data[:4] != b'MDMP':
        raise ValueError('Not a Windows minidump')
    count, directory = struct.unpack_from('<II', data, 8)
    if count > 4096 or directory + count * 12 > len(data):
        raise ValueError('Invalid directory')
    streams = {}
    for i in range(count):
        kind, size, rva = struct.unpack_from('<III', data, directory + i * 12)
        if rva + size > len(data):
            raise ValueError('Invalid stream bounds')
        streams[kind] = (rva, size)
    modules = []
    if 4 in streams:
        rva, size = streams[4]
        module_count = struct.unpack_from('<I', data, rva)[0]
        if 4 + module_count * 108 > size:
            raise ValueError('Invalid module list')
        for i in range(module_count):
            base, image_size, checksum, timestamp, name_rva = struct.unpack_from('<QIIII', data, rva + 4 + i * 108)
            length = struct.unpack_from('<I', data, name_rva)[0]
            name = data[name_rva + 4:name_rva + 4 + length].decode('utf-16le', errors='replace').replace('\\', '/').split('/')[-1]
            modules.append({'name': name, 'base': base, 'size': image_size})

    def locate(address):
        for m in modules:
            if m['base'] <= address < m['base'] + m['size']:
                return m['name'] + '+0x' + format(address - m['base'], 'x')
        return 'unmapped'

    report = {'dump_file': str(path), 'dump_bytes': len(data), 'module_names': [m['name'] for m in modules],
              'scope': 'Structured diagnostic comments, exception metadata and address candidates only; no arbitrary memory strings or credentials exported.'}
    # 用途：只导出显式CommentStreamA中的启动错误行，丢弃其他元数据和潜在身份字段。
    if 10 in streams:
        crva, csize = streams[10]
        comment = data[crva:crva + csize].decode('utf-8', errors='replace').rstrip('\0')
        report['diagnostic_comment_lines'] = [line[:300] for line in comment.splitlines()
            if any(word in line.casefold() for word in ('error', 'fatal', 'fail', 'assert', 'unable'))
            and not any(word in line.casefold() for word in ('token', 'password', 'secret', 'cookie', 'login', 'account'))]
    # 用途：按Breakpad官方MDRawAssertionInfo结构读取明确的断言元数据，避免盲扫内存字符串。
    if 0x47670002 in streams:
        arva, asize = streams[0x47670002]
        if asize >= 776:
            fields = [data[arva + i * 256:arva + (i + 1) * 256].decode('utf-16le', errors='replace').split('\0')[0] for i in range(3)]
            line, kind = struct.unpack_from('<II', data, arva + 768)
            report['assertion'] = {'expression': fields[0], 'function': fields[1],
                                    'source_file_basename': fields[2].replace('\\', '/').split('/')[-1], 'line': line, 'type': kind}
    if 7 in streams:
        report['processor_architecture'] = struct.unpack_from('<H', data, streams[7][0])[0]
    if 6 in streams:
        rva, size = streams[6]
        if size < 168:
            raise ValueError('Invalid exception stream')
        thread_id, = struct.unpack_from('<I', data, rva)
        code, flags, record, address, parameters = struct.unpack_from('<IIQQI', data, rva + 8)
        report['exception'] = {'code': f'0x{code:08x}', 'flags': flags, 'thread_id': thread_id,
                               'address': hex(address), 'module_location': locate(address)}
        # 用途：候选返回地址仅用于定位，不将没有展开验证的地址冒充调用栈。
        if 3 in streams:
            trva, tsize = streams[3]
            n, = struct.unpack_from('<I', data, trva)
            for i in range(n):
                off = trva + 4 + i * 48
                tid, = struct.unpack_from('<I', data, off)
                if tid != thread_id:
                    continue
                stack_base, stack_size, stack_rva = struct.unpack_from('<QII', data, off + 24)
                pointer_size = 8 if report.get('processor_architecture') == 9 else 4
                candidates = []
                if stack_rva + stack_size > len(data):
                    raise ValueError('Invalid stack descriptor')
                for offset in range(0, min(stack_size, 4096) - pointer_size + 1, pointer_size):
                    word = int.from_bytes(data[stack_rva + offset:stack_rva + offset + pointer_size], 'little')
                    location = locate(word)
                    if location != 'unmapped':
                        candidates.append({'stack_offset': offset, 'location': location})
                report['stack_address_candidates_not_unwound_frames'] = candidates[:35]
    return report


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    dump_root = ROOT / 'sandbox/PBZSteamLab/drive/D/mod文档/PBZ-Boss操控研究/runtime/SteamOffline/dumps'
    dumps = sorted(dump_root.glob('crash_steam.exe_*.dmp'))
    reports = [inspect(path) for path in dumps]
    result = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'dumps': reports,
              'raw_dumps_private': True, 'private_memory_not_exported': True}
    target = ROOT / 'evidence/offline-steam/client-dump-summary.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(target), 'results': [{'file': Path(r['dump_file']).name, 'exception': r.get('exception'),
                        'diagnostic_comment_lines': r.get('diagnostic_comment_lines')} for r in reports]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
