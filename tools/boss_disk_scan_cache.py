"""Validate immutable parsed scans; callers must still hash every declaration."""
from collections import Counter
import json
from pathlib import Path

import boss_disk_declarations as disk

# 4154db0's parser has the same per-package semantics as the incremental parser.
# No other legacy parser is silently trusted across a source change.
LEGACY_PARSER = '4fa91af81a18a90b1f6a93670e3dee1eedb9e19050f1a4a3e9e8d6a1fd27aaf8'


def load(path, index_sha256, mapping_sha256, current_sources, script_sources,
         declarations, native_package):
    path=Path(path).resolve()
    raw=path.read_bytes()
    report=json.loads(raw)
    if (report.get('schema')!=1 or report.get('kind')!='offline_native_dependency_scan'
            or report.get('declaration_contents_verified') is not True
            or report.get('index_sha256')!=index_sha256
            or report.get('mapping_sha256')!=mapping_sha256):
        raise ValueError('Exact verified scan cache is required')
    prior=report['sources']
    parser='boss_disk_dependencies.py';helper='boss_disk_scan_cache.py'
    legacy=prior.get(parser)==LEGACY_PARSER and helper not in prior
    expected=set(current_sources)-({helper} if legacy else set())
    if (set(prior)!=expected or (not legacy and prior.get(parser)!=current_sources[parser])
            or any(prior[name]!=sha for name,sha in current_sources.items()
                   if name not in (parser,helper))
            or (not legacy and prior.get(helper)!=current_sources[helper])):
        raise ValueError('Scan cache parser sources are incompatible')
    current_scripts={(str(Path(r['path']).resolve()),r['plan_sha256']) for r in script_sources}
    if any((str(Path(r['path']).resolve()),r['plan_sha256']) not in current_scripts
           for r in report['script_sources']):
        raise ValueError('Scan cache script sources cannot be removed or changed')
    rows={}
    for row in report['packages']:
        key=native_package(row['package']).casefold()
        item=declarations.get(key)
        if (key in rows or item is None or row['package'].casefold()!=item['package'].casefold()
                or row['declaration_sha256']!=item['declaration_sha256']
                or row['declaration_bytes']!=item['declaration_bytes']):
            raise ValueError('Scan cache must join exact unchanged declaration identities')
        rows[key]=row
    if len(rows)!=report['extracted_packages']:
        raise ValueError('Scan cache package coverage mismatch')
    if any(type(n) is not int or n<0 for n in report['export_types'].values()):
        raise ValueError('Scan cache export counts are invalid')
    return rows,Counter(report['export_types']),dict(path=str(path),sha256=disk.digest(path),
        legacy_parser_migration=legacy,contents_still_require_sha256=True)
