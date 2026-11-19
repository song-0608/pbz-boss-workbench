"""Accept only a source-matched helper build and its own headless-lab smoke."""
import json
from pathlib import Path
from boss_adaptation_workflow import ROOT, sha
from build_boss_native_input import SOURCES
from mod_installation import unlinked_path
import research_storage


def verify(smoke_path):
    smoke_path=unlinked_path(smoke_path)
    work=smoke_path.parent;build=work.parent
    assert build.parent==unlinked_path(research_storage.PROJECT_STORAGE/'创作协作/原生输入模块')
    assert smoke_path.name=='result.json' and work.name.startswith('smoke-')
    smoke=json.loads(smoke_path.read_bytes());record=json.loads((build/'build.json').read_bytes())
    assert record['passed'] is True and smoke['passed'] is True
    assert record['sources']=={name:sha(ROOT/name) for name in SOURCES},'native helper build source changed'
    assert sha(build/'main.dll')==record['dll_sha256']==smoke['dll_sha256']
    assert smoke['build_sha256']==sha(build/'build.json')
    assert smoke['smoke_source_sha256']==sha(ROOT/'tools/smoke_boss_native_input.py')
    for key in ('headless_lab','background_rejected','monotonic_snapshot','temporary_proxy_removed'):
        assert smoke[key] is True,key
    for key in ('pbz_started','gameplay_called','native_key_runtime_verified','defense_runtime_verified'):
        assert smoke[key] is False,key
    return build/'main.dll',dict(build_sha256=sha(build/'build.json'),smoke_sha256=sha(smoke_path),
        dll_sha256=record['dll_sha256'],native_key_runtime_verified=False,defense_runtime_verified=False)
