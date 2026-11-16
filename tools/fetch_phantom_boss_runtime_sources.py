"""Fetch the fixed upstream mod/native sources through GitHub's blob API; never execute."""
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess

from build_phantom_boss_candidate import COMMIT, ROOT, canonical, safe_file, sha, verify_upstream

REPOSITORY = 'yhsharaf/PhantomPact'


def github(path):
    result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/{path}'],
                            capture_output=True, timeout=35, check=True)
    return json.loads(result.stdout)


def fetch():
    reviewed = ROOT / 'runtime/integration-research/PhantomPact' / COMMIT
    pins = verify_upstream(reviewed)
    tree = github(f'git/trees/{COMMIT}?recursive=1')
    assert tree['truncated'] is False
    rows = [r for r in tree['tree'] if r['type'] == 'blob'
            and (r['path'].startswith('native/') or r['path'].startswith('mod/PBZCoop/Scripts/')
                 or r['path'] == 'mod/PBZCoop/PhantomPact.ini')]
    assert 20 <= len(rows) <= 256, 'Unexpected upstream runtime tree'
    assert all(r['mode'] == '100644' and 0 <= r['size'] <= 2_000_000 for r in rows)
    target = reviewed / 'runtime-sources'
    target.mkdir(exist_ok=True)

    def one(row):
        path = safe_file(target, row['path'])
        data = path.read_bytes() if path.is_file() else None
        if data is None or hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != row['sha']:
            blob = github('git/blobs/' + row['sha'])
            assert blob['encoding'] == 'base64' and blob['sha'] == row['sha']
            data = base64.b64decode(blob['content'], validate=False)
        assert len(data) == row['size']
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == row['sha']
        if row['path'] in pins:
            assert sha(data) == pins[row['path']], 'Runtime differs from reviewed source: ' + row['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
        return row['path'], dict(git_blob=row['sha'], sha256=sha(data), bytes=len(data))

    files = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, row) for row in rows]
        for future in as_completed(futures):
            name, receipt = future.result()
            files[name] = receipt
            print(f'Verified source {len(files)}/{len(rows)}: {name}', flush=True)
    assert all(name in files for name in pins if name.startswith(('mod/', 'native/')))
    receipt = dict(schema=1, repository='https://github.com/' + REPOSITORY, commit=COMMIT,
                   files=dict(sorted(files.items())), official_release_downloaded=False,
                   executed=False, installed=False, game_started=False, native_relay_executed=False,
                   source_tool_sha256=sha(Path(__file__).read_bytes()))
    (target / 'source-receipt.json').write_bytes(canonical(receipt) + b'\n')
    print(json.dumps(dict(source_directory=str(target), verified_files=len(files),
                          executed=False, installed=False), ensure_ascii=False))
    return target


if __name__ == '__main__':
    fetch()
