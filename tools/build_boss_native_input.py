"""Build a separate read-only C++ input mod against the unchanged verified loader.

Only helper targets are built. The existing loader is hashed before and after.
No PBZ process, window, save or installation is opened by this command.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess

from boss_adaptation_workflow import ROOT, sha
import pbz_ue4ss_baseline as loader
from mod_installation import unlinked_path
import research_storage

SOURCES = ('tools/build_boss_native_input.py', 'tools/boss_native_input/CMakeLists.txt',
    'tools/boss_native_input/add_to_ue4ss.cmake', 'tools/boss_native_input/native_input.cpp',
    'tools/boss_native_input/policy.hpp', 'tools/boss_native_input/smoke.lua',
    'tests/test_boss_native_input.cpp', 'tools/boss_native_input.lua', 'tests/test_boss_native_input.lua')


def build(cmake, build_root):
    cmake, build_root = Path(cmake).absolute(), Path(build_root).absolute()
    # This existing compiler tree uses an ASCII junction; it is not a Mod package.
    assert cmake.is_file() and (build_root/'CMakeCache.txt').is_file()
    cache = (build_root/'CMakeCache.txt').read_text(encoding='utf-8')
    source = next(line.split('=', 1)[1] for line in cache.splitlines()
                  if line.startswith('CMAKE_HOME_DIRECTORY:INTERNAL='))
    assert 'CMAKE_PROJECT_INCLUDE:' not in cache or ('CMAKE_PROJECT_INCLUDE:UNINITIALIZED='+
        str(ROOT/'tools/boss_native_input/add_to_ue4ss.cmake').replace('\\','/')) in cache, \
        'Preserve an unrelated CMake project include'
    _, verification = loader.verified_build_record()
    binaries = {name: sha(build_root/'Game__Shipping__Win64/bin'/name) for name in ('UE4SS.dll','dwmapi.dll')}
    sources = {name: sha(ROOT/name) for name in SOURCES}
    destination = unlinked_path(research_storage.PROJECT_STORAGE/'创作协作/原生输入模块'/
        datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    destination.mkdir(parents=True)
    record = dict(schema=1, sources=sources, loader_verification_sha256=sha(verification),
        unchanged_loader=binaries, passed=False, game_started=False, installed=False,
        native_key_runtime_verified=False, defense_runtime_verified=False)
    def run(name, command):
        result=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace',timeout=180)
        (destination/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        assert result.returncode==0, 'Native helper '+name+' failed; inspect '+str(destination)
    try:
        include=(ROOT/'tools/boss_native_input/add_to_ue4ss.cmake').as_posix()
        run('configure',[str(cmake),'-S',source,'-B',str(build_root),'-DCMAKE_PROJECT_INCLUDE='+include])
        run('compile',[str(cmake),'--build',str(build_root),'--config','Game__Shipping__Win64',
            '--target','PBZNativeCombatInput','PBZNativeCombatInputPolicyTest','--parallel','2','--',
            '/p:BuildProjectReferences=false'])
        output=build_root/'pbz-native-input/Game__Shipping__Win64'
        run('policy',[str(output/'PBZNativeCombatInputPolicyTest.exe')])
        run('lua-abi',[str(ROOT.parent/'build/lua-harness/Release/lua-lab.exe'),
            'tests/test_boss_native_input.lua','.'])
        assert sources=={name:sha(ROOT/name) for name in SOURCES},'Helper source changed during build'
        assert binaries=={name:sha(build_root/'Game__Shipping__Win64/bin'/name) for name in binaries}
        loader.verified_build_record()
        shutil.copy2(output/'main.dll',destination/'main.dll')
        record.update(passed=True,dll_sha256=sha(destination/'main.dll'),policy_cases=9)
    finally:
        # Do not leave the existing upstream build configured with a chat-specific include.
        run('restore-build-config',[str(cmake),'-S',source,'-B',str(build_root),'-U','CMAKE_PROJECT_INCLUDE'])
        (destination/'build.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cmake',type=Path,required=True);parser.add_argument('--build-root',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(dict(build=str(build(args.cmake,args.build_root))),ensure_ascii=False))
