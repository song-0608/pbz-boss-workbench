"""用途：复用本机公开更新包缓存；解压前后均按刚下载的Valve官方SHA-256清单校验。"""
from pathlib import Path
import hashlib
import json
import lzma
import struct
import sys
import zlib
from datetime import datetime, timezone, timedelta
from fetch_client_update import keyvalues, CACHE

ROOT = Path(__file__).resolve().parent.parent
from research_storage import container_path
SOURCE = container_path() / 'drive/E/PBZSteamLabClient/package'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def decode_vzip(data):
    """用途：按SteamKit的公开VZip帧布局读取LZMA；只处理官方客户端压缩包。"""
    if len(data) < 22 or data[:3] != b'VZa' or data[-2:] != b'zv':
        raise ValueError('Unsupported VZip frame')
    expected_crc, size = struct.unpack_from('<II', data, len(data) - 10)
    if size > 512 * 1024 * 1024:
        raise ValueError('Unexpected decompressed package size')
    prop = data[7]
    lc, remainder = prop % 9, prop // 9
    lp, pb = remainder % 5, remainder // 5
    dictionary = struct.unpack_from('<I', data, 8)[0]
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
        'id': lzma.FILTER_LZMA1, 'dict_size': dictionary, 'lc': lc, 'lp': lp, 'pb': pb}])
    result = decoder.decompress(data[12:-10], max_length=size + 1)
    if len(result) != size or zlib.crc32(result) & 0xffffffff != expected_crc:
        raise ValueError('VZip decompression size/CRC mismatch')
    return result


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    manifest = keyvalues((CACHE / 'steam_client_win64').read_text(encoding='utf-8-sig'))['win64']
    rows = []
    for name, package in manifest.items():
        if not isinstance(package, dict):
            continue
        target = CACHE / package['file']
        expected = package['sha2'].lower()
        if target.is_file() and digest(target) == expected:
            rows.append({'name': name, 'source': 'verified_download', 'file': target.name, 'sha256': expected})
            continue
        normal = SOURCE / package['file']
        if normal.is_file() and digest(normal) == expected:
            payload = normal.read_bytes(); source = 'existing_official_zip'
        elif 'zipvz' in package:
            compressed = SOURCE / package['zipvz']
            if not compressed.is_file() or digest(compressed) != package['sha2vz'].lower():
                raise RuntimeError('No official verified cache: ' + name)
            payload = decode_vzip(compressed.read_bytes()); source = 'existing_official_vzip'
            # VZip内层通常是未压缩ZIP，与普通下载ZIP的压缩布局不同；不得套用普通ZIP的哈希。
            # 其信任链是官方sha2vz -> VZip CRC/长度 -> 解码ZIP的独立SHA-256。
            target = CACHE / (package['file'] + '.from-vzip.zip')
        else:
            raise RuntimeError('No official cache available: ' + name)
        decoded_hash = hashlib.sha256(payload).hexdigest()
        if source != 'existing_official_vzip' and (len(payload) != int(package['size']) or decoded_hash != expected):
            raise ValueError('Official uncompressed archive SHA-256 mismatch')
        temporary = target.with_name(target.name + '.verified')
        temporary.write_bytes(payload); temporary.replace(target)
        rows.append({'name': name, 'source': source, 'file': target.name, 'sha256': decoded_hash,
                     'official_vzip_sha256': package.get('sha2vz') if source == 'existing_official_vzip' else None})
        print('Verified reusable official package: ' + name, flush=True)
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'version': manifest.get('version'),
              'packages_verified': len(rows), 'packages': rows, 'client_launched': False, 'game_launched': False}
    (ROOT / 'evidence/offline-steam/official-packages-verified.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'packages'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
