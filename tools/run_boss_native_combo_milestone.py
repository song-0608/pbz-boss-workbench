"""Check the generated native-combo bundle and protected workflow without a game."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from boss_adaptation_workflow import ROOT,sha,write_json
from build_boss_profile_candidate import lua
import boss_native_combo_candidate as candidate
import prepare_boss_native_combo_workflow as workflow

SOURCES=('tools/run_boss_native_combo_milestone.py',)


def run():
    bundle=candidate.build('044_pengmeng')
    record=candidate.read(bundle/'manifest.json')
    flow=workflow.build(bundle)
    bundle_sha=sha(bundle/'manifest.json');flow_sha=sha(flow/'manifest.json')
    source_files=dict(record['source_files'])
    source_files.update(workflow.source_hashes())
    source_files.update({name:sha(ROOT/name) for name in SOURCES})
    checks=[]
    def invoke(name,command):
        result=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace',timeout=120)
        checks.append(dict(name=name,passed=result.returncode==0,output=(result.stdout+result.stderr).strip()))
        print(name+': '+('PASS' if result.returncode==0 else 'FAIL'),flush=True)
    invoke('Exact identity graph and workflow regressions',[sys.executable,'-B','-X','utf8','-m','unittest',
        'tests.test_boss_combo_dependencies','tests.test_boss_native_combo_candidate','tests.test_boss_native_combo_workflow'])
    fixture=ROOT/'runtime'/('native-combo-fixture-'+sha(bundle/'manifest.json')[:16]+'.lua')
    raw=('return '+lua(record['definition'])+'\n').encode('utf-8')
    if fixture.exists():assert fixture.read_bytes()==raw
    else:fixture.write_bytes(raw)
    executable=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
    invoke('Generated native parent repeated natural and cancel lifecycle',[str(executable),
        'tests/test_boss_native_combo_candidate.lua','.',bundle.relative_to(ROOT).as_posix(),fixture.relative_to(ROOT).as_posix()])
    syntax=ROOT/'runtime'/('native-combo-syntax-'+bundle_sha[:16]+'-'+sha(ROOT/SOURCES[0])[:8]+'.lua')
    raw=('local files='+lua([(bundle/name).relative_to(ROOT).as_posix() for name in record['overrides']])+
        "\nfor _,path in ipairs(files)do assert(loadfile(path))end\nprint('PASS native combo payload syntax')\n").encode('utf-8')
    if syntax.exists():assert syntax.read_bytes()==raw
    else:syntax.write_bytes(raw)
    invoke('All generated Lua overrides compile',[str(executable),str(syntax)])
    invoke('Frozen generated controller verifies its actual bundle',[sys.executable,'-B','-X','utf8',
        str(flow/'combo_ui_controller.py'),'verify',str(flow)])
    assert all(sha(ROOT/name)==digest for name,digest in source_files.items()),'sources changed during milestone'
    assert sha(bundle/'manifest.json')==bundle_sha and sha(flow/'manifest.json')==flow_sha,'candidate or workflow changed'
    report=dict(schema=1,kind='boss_native_combo_offline_milestone',source_sha256=source_files,
        candidate=bundle.relative_to(ROOT).as_posix(),candidate_manifest_sha256=sha(bundle/'manifest.json'),
        workflow=flow.relative_to(ROOT).as_posix(),workflow_manifest_sha256=sha(flow/'manifest.json'),
        checks=checks,passed=all(r['passed'] for r in checks),
        native_execution_order_preserved=True,manual_ability_grants=False,
        game_started=False,ui_input_sent=False,installed=False,runtime_acceptance_current=False,
        playable=False,all_boss_skills_complete=False)
    fingerprint=hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()[:16]
    target=ROOT/'evidence/adaptation'/('boss-native-combo-offline-'+fingerprint+'-'+str(time.time_ns())+'.json')
    write_json(target,report)
    print(json.dumps(dict(report=str(target),passed=report['passed'],candidate=str(bundle),workflow=str(flow),
        game_started=False,playable=False),ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(run())
