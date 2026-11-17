"""Build an uninstalled experience candidate from the immutable accepted v4 payload."""
import argparse
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha, write_json
from mod_installation import MANIFEST, assert_closed, validate_package
from build_boss_profile_candidate import lua
from player_roster_expansion import CATALOG, QUEUE, plan as roster_plan

BASE='ahua-boss-workbench-v4-d2cb2593f6ea392e'
SOURCES=('tools/build_player_experience_candidate.py','tools/player_action_input.lua',
         'tools/player_target_lock.lua','tools/player_experience_bridge.lua',
         'tests/test_player_action_input.lua','tests/test_player_target_lock.lua',
         'tests/test_player_experience_candidate.py','tests/test_player_experience_runtime.lua',
         'tools/player_roster_expansion.py','tests/test_player_roster_expansion.py',
         'tools/player_boss_picker.lua','tests/test_player_boss_picker.lua',CATALOG,QUEUE)
SOURCES=(*SOURCES,'tests/test_player_experience_bridge.lua','tests/test_player_experience_catalog.lua')


def replace(source, before, after):
    assert source.count(before)==1, 'Exact immutable anchor required: '+before[:100]
    return source.replace(before,after)


def payload(root=ROOT):
    base=root/'releases'/BASE;manifest=validate_package(base)
    assert manifest['status']=='release' and manifest['runtime_acceptance_current']
    proof=root/manifest['acceptance_report']
    assert sha(proof)==manifest['acceptance_report_sha256'] and json.loads(proof.read_bytes())['passed']
    files={name:(base/name).read_bytes() for name in manifest['files']}
    prefix='PBZBossControl/Scripts/'
    def change(name, before, after):
        key=prefix+name
        files[key]=replace(files[key].decode('utf-8').replace('\r\n','\n'),before,after).encode('utf-8')
    for name in ('player_action_input','player_target_lock','player_experience_bridge','player_boss_picker'):
        files[prefix+name+'.lua']=(root/'tools'/(name+'.lua')).read_bytes()
    previews=roster_plan(root)['previews']
    change('workbench_catalog.lua','    return result\n',
           '    for _,entry in ipairs('+lua(previews)+')do\n'
           '        if not seen[entry.id]then result[#result+1]=entry;seen[entry.id]=true end\n'
           '    end\n    return result\n')
    workbench=files[prefix+'boss_workbench.lua'].decode('utf-8').replace('\r\n','\n')
    tail=workbench[workbench.index('function Workbench:text()'):]
    assert tail.endswith('return Workbench\n')
    files[prefix+'boss_workbench.lua']=replace(workbench,tail,
        "function Workbench:text()\n    return require('player_boss_picker').render(self.options.entries(),"
        "self.cursor,self.options.selected(),self.message,self.busy)\nend\nreturn Workbench\n").encode('utf-8')
    change('ue_host.lua','    local pending_releases={}\n',
           "    local pending_releases={}\n    local gameplay=require('player_action_input').new(g)\n")
    change('ue_host.lua','        release_keys = function()\n',
           '        bind_gameplay_key = function(key,fn) gameplay:bind(key,fn) end,\n'
           '        release_keys = function()\n            gameplay:close()\n')
    change('runtime.lua','    if self.config.controls.cycle_target then check_key(self.config.controls.cycle_target)end\n',
           '    if self.config.controls.cycle_target then check_key(self.config.controls.cycle_target)end\n'
           '    if self.config.controls.lock_target then check_key(self.config.controls.lock_target)end\n')
    change('runtime.lua','    if self.config.controls.cycle_target then\n        self.host.bind_key(self.config.controls.cycle_target,function()\n',
           '    local bind_gameplay=self.host.bind_gameplay_key or self.host.bind_key\n'
           '    if self.config.controls.lock_target then\n'
           '        bind_gameplay(self.config.controls.lock_target,function()\n'
           "            self:action('lock_target',function()\n"
           "                if self.session.state~='ACTIVE'or not self.session.receipt then return false,'not controlling a boss'end\n"
           "                if self.session:world_boundary()~='same'then return false,'world transition'end\n"
           '                return self.session.bridge:toggle_target_lock(self.session.receipt)\n'
           '            end)\n        end)\n    end\n'
           '    if self.config.controls.cycle_target then\n        bind_gameplay(self.config.controls.cycle_target,function()\n')
    change('runtime.lua','            self.host.bind_key(definition.key, function()\n'
           '                self:action(selected, function() return self.session:skill(selected) end)\n',
           '            bind_gameplay(definition.key, function()\n'
           '                self:action(selected, function()\n'
           "                    if self.session.state~='ACTIVE'then return false,'not controlling a boss'end\n"
           '                    local ready,why=self.session:poll()\n'
           '                    if not ready then return false,why end\n'
           '                    return self.session:skill(selected)\n'
           '                end)\n')
    change('input_driver.lua','        if length > 0 then\n',
           '        if length > 0 and not session.current_skill then\n')
    change('control_bridge.lua','return Bridge\n',
           "return require('player_experience_bridge').extend(Bridge)\n")
    change('boss_catalog.lua',"controls={enter='F6',exit='F10',menu_exit='ESCAPE',cycle_target='F7'},skills={}}",
           "controls={enter='F6',exit='F10',menu_exit='ESCAPE',cycle_target='F7',lock_target='MIDDLE_MOUSE_BUTTON'},skills={}}")
    change('owned_arena.lua','local api={now=os.time,attest=experiment_attest,find_all=FindAllOf,find_exact=StaticFindObject}',
           'local api={now=os.time,attest=experiment_attest,find_all=FindAllOf,find_exact=StaticFindObject,experience_log=log}')
    change('player_hud.lua',"    rows[#rows+1]='WASD 移动 | 鼠标转向 | Esc 先退出接管'",
           "    rows[#rows+1]='WASD 移动 | Shift+技能可用 | Esc 先退出接管'\n"
           "    if receipt and receipt.player_target_lock then\n"
           "        rows[#rows+1]='鼠标中键 锁敌开关 | 镜头：'..(receipt.player_target_lock.enabled and'锁定目标'or'自由')\n"
           "    end")
    files['PBZBossControl/README.md']+=('\n体验开发候选：中键切换镜头锁敌，F7切换目标；支持Shift+技能，'
        '出招期间不持续注入移动意图。尚未完成该候选实机验收，不替换当前正式v4。\n').encode('utf-8')
    return manifest,files


def expected(root=ROOT):
    base,files=payload(root)
    sources={name:sha(root/name) for name in SOURCES}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    identity=dict(files=hashes,sources=sources,base_manifest_sha256=sha(root/'releases'/BASE/MANIFEST))
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    manifest=dict(base,release_id='ahua-player-experience-dev-'+fingerprint,status='development',
        complete_mod=False,runtime_acceptance_current=False,integration_only=True,files=hashes,
        experience_base_release=BASE,experience_base_manifest_sha256=identity['base_manifest_sha256'],
        experience_sources=sources,pending=['camera lock and Shift/movement casting native acceptance',
        'native menu World and focus/cleanup regression'],experience_runtime_verified=False)
    manifest.pop('acceptance_report',None);manifest.pop('acceptance_report_sha256',None)
    return manifest,files


def verify(directory,root=ROOT):
    manifest,files=expected(root)
    assert directory.parent==(root/'runtime/release-candidates').resolve()
    assert directory.name==manifest['release_id'] and validate_package(directory)==manifest
    assert all((directory/name).read_bytes()==data for name,data in files.items())
    return manifest


def build(root=ROOT):
    assert_closed(root);manifest,files=expected(root)
    target=root/'runtime/release-candidates'/manifest['release_id']
    if not target.exists():
        target.mkdir(parents=True)
        for name,data in files.items():
            path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        write_json(target/MANIFEST,manifest)
    verify(target,root);return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',type=Path);args=parser.parse_args()
    directory=args.verify.resolve() if args.verify else build()
    manifest=verify(directory)
    print(json.dumps(dict(candidate=str(directory),installed=False,game_started=False,
                         runtime_verified=manifest['experience_runtime_verified']),ensure_ascii=False))
