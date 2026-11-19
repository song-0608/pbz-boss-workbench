"""Check the native helper ABI in the self-packaged headless UE58Lab, never PBZ."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from boss_adaptation_workflow import ROOT, sha
from build_boss_native_input import SOURCES
from mod_installation import unlinked_path
import pbz_ue4ss_baseline as loader
import research_storage


def run(build):
    build=unlinked_path(build)
    assert build.parent==unlinked_path(research_storage.PROJECT_STORAGE/'创作协作/原生输入模块')
    receipt=json.loads((build/'build.json').read_bytes())
    assert receipt['passed'] and sha(build/'main.dll')==receipt['dll_sha256']
    assert receipt['sources']=={name:sha(ROOT/name) for name in SOURCES},'Build source changed'
    _,verified=loader.verified_build_record()
    assert sha(verified)==receipt['loader_verification_sha256']
    binary=ROOT.parent/'build/ue4ss-ascii/Game__Shipping__Win64/bin'
    assert receipt['unchanged_loader']=={name:sha(binary/name) for name in receipt['unchanged_loader']}
    game=ROOT.parent/'build/UE58Lab-Development/Windows/UE58Lab/Binaries/Win64/UE58Lab.exe'
    proxy=game.parent/'dwmapi.dll'
    assert game.is_file() and not proxy.exists(),'Preserve any existing lab proxy'
    work=build/('smoke-'+datetime.now().strftime('%H%M%S-%f'));stage=work/'ue4ss'
    stage.mkdir(parents=True)
    shutil.copy2(binary/'UE4SS.dll',stage/'UE4SS.dll')
    settings=(ROOT.parent/'profiles/voyager-firststeps/UE4SS-settings.ini').read_text(encoding='utf-8-sig')
    for key,value in {'ConsoleEnabled':'0','GuiConsoleEnabled':'0','GuiConsoleVisible':'0',
        'UseCache':'0','SecondsToScanBeforeGivingUp':'30'}.items():
        settings=re.sub(r'(?m)^'+key+r'\s*=.*$',key+' = '+value,settings)
    (stage/'UE4SS-settings.ini').write_text(settings,encoding='utf-8')
    signatures=stage/'UE4SS_Signatures';signatures.mkdir()
    shutil.copy2(ROOT.parent/'lab/signatures/ue58-development-static-construct.lua',signatures/'StaticConstructObject.lua')
    mods=stage/'Mods';native=mods/'PBZNativeCombatInput/dlls';native.mkdir(parents=True)
    shutil.copy2(build/'main.dll',native/'main.dll')
    script=mods/'PBZNativeInputSmoke/Scripts';script.mkdir(parents=True)
    shutil.copy2(ROOT/'tools/boss_native_input/smoke.lua',script/'main.lua')
    (mods/'mods.txt').write_text('PBZNativeCombatInput : 1\nPBZNativeInputSmoke : 1\n',encoding='utf-8')
    process=None
    result=dict(schema=1,passed=False,headless_lab=True,pbz_started=False,gameplay_called=False,
        dll_sha256=receipt['dll_sha256'],build_sha256=sha(build/'build.json'),
        smoke_source_sha256=sha(__file__),native_key_runtime_verified=False,defense_runtime_verified=False)
    try:
        shutil.copy2(binary/'dwmapi.dll',proxy)
        process=subprocess.Popen([str(game),'/Engine/Maps/Entry','--ue4ss-path',str(stage/'UE4SS.dll'),
            '-nullrhi','-unattended','-nosound','-nosplash','-abslog='+str(work/'engine.log')],
            cwd=game.parent,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        result['pid']=process.pid
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            log=stage/'UE4SS.log'
            content=log.read_text(encoding='utf-8',errors='replace') if log.exists() else ''
            if 'PBZ_NATIVE_INPUT:PASS' in content:
                assert ('|PID='+str(process.pid)) in content,'Snapshot is from a different process'
                result.update(passed=process.poll() is None,background_rejected=True,monotonic_snapshot=True)
                break
            if process.poll() is not None or 'PBZ_NATIVE_INPUT:FAIL' in content:break
            time.sleep(.25)
    finally:
        if process and process.poll() is None:process.terminate();process.wait(timeout=10)
        if proxy.exists() and sha(proxy)==receipt['unchanged_loader']['dwmapi.dll']:proxy.unlink()
        result['temporary_proxy_removed']=not proxy.exists()
        result['passed']=result['passed'] and result['temporary_proxy_removed']
        (work/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(work/'result.json'),**result),ensure_ascii=False))
    assert result['passed'],'Native input lab smoke failed; keep logs for review'
    return work/'result.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('build',type=Path)
    run(parser.parse_args().build)
