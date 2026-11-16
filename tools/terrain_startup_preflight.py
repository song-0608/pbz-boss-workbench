"""Stage one exact, read-only terrain preflight before the timed assembly."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from mod_installation import ROOT, MANIFEST, digest
from build_yanqiansui_centered_candidate import expected, verify
from boss_adaptation_workflow import BUILD

MODULES = ('arena_layout', 'yanqiansui_clearance_core', 'yanqiansui_arena_clearance',
           'ue_arena_layout', 'boss_selection_preflight', 'boss_catalog',
           'profiles.ahua', 'profiles.yanqiansui')


def render(candidate, expires, token):
    manifest = verify(candidate)
    assert isinstance(expires, int) and time.time() < expires <= time.time() + 1200
    assert token.isdigit()
    lines = ["-- One-shot unarmed preflight; no spawned actors, input hooks or repeating loops."]
    for name in MODULES:
        path = 'PBZBossControl/Scripts/' + name.replace('.', '/') + '.lua'
        assert digest(candidate / path) == manifest['files'][path]
        source = (candidate / path).read_text(encoding='utf-8')
        lines.append("package.preload[" + json.dumps(name) + "]=function(...)\n" + source + "\nend")
    lines.append("""
ExecuteInGameThread(function()
    local ok,err=pcall(function()
        assert(os.time()<{{EXPIRES}},'startup preflight expired')
        local function valid(o)return o and o.IsValid and o:IsValid()end
        local pc
        for _,o in ipairs(FindAllOf('PBZPlayerController')or{})do
            if valid(o)and valid(o.Pawn)and o:GetFullName():find(':PersistentLevel.',1,true)then
                assert(not pc,'ambiguous restored player');pc=o
            end
        end
        assert(pc,'restored gameplay player missing')
        local player=pc.Pawn
        local before=player:K2_GetActorLocation()
        local pass,reason=require('boss_selection_preflight').verify(_G,
            {binding_verified=true},pc,player,'073_yanqiansui',valid,{{BUILD}})
        local after=player:K2_GetActorLocation()
        assert(pc.Pawn:GetAddress()==player:GetAddress(),'player identity changed')
        assert(before.X==after.X and before.Y==after.Y and before.Z==after.Z,'player moved during readonly preflight')
        print('PBZ_STARTUP_TERRAIN:TOKEN={{TOKEN}}|accepted='..tostring(pass)..'|position_unchanged=true|reason='..tostring(reason)..'\\n')
    end)
    if not ok then print('PBZ_STARTUP_TERRAIN:ERROR={{TOKEN}}|'..tostring(err)..'\\n')end
end)
""".replace('{{EXPIRES}}', str(expires)).replace('{{BUILD}}', json.dumps(BUILD)).replace('{{TOKEN}}', token))
    return '\n'.join(lines).encode('utf-8')


def stage():
    import ahua_practice as practice
    import official_validation as validation
    import research_game_menu as menu
    import arena_contract
    owner, state = practice.owned_session()
    log = practice.log_path(state)
    text = log.read_text(encoding='utf-8', errors='replace')
    menu.validate_startup_positioning(owner, state, text)
    assert not state.get('boss_lifecycle_experiment'), 'Only before the first assembly'
    assert time.time() < state['deadline_unix'] - 360
    validation.verify_build(state['ue4ss_loader_manifest'])
    validation.c.isolation.select_box('PBZSteamLab')
    dll = validation.c.isolation.api()
    validation.c.isolation.check_policy(dll, allow_offline_validation=True)
    assert not validation.c.host_steam_pids(dll)
    assert validation.c.baseline.formal_files() == state['formal_before']
    pids = {p['ProcessId'] for p in validation.c.box_processes(dll) if p['Name'].lower() == 'pbz.exe'}
    work = Path(state['work'])
    arena_contract.validate(practice.read(work / 'arena-native-contract.json'), pids)
    candidate = ROOT / 'runtime/release-candidates' / expected()[-1]
    token = str(time.time_ns())
    payload = render(candidate, min(int(time.time()) + 120, int(state['deadline_unix']) - 330), token)
    row = next(r for r in state['ue4ss_loader_manifest'] if r['physical_path'].replace('\\', '/').endswith('/PBZObserveAI/Scripts/main.lua'))
    target = Path(row['physical_path'])
    before = target.read_bytes()
    old_hash = row['sha256']
    (work / ('startup-preflight-before-' + token + '.lua')).write_bytes(before)
    try:
        target.write_bytes(payload)
        row['sha256'] = hashlib.sha256(payload).hexdigest()
        validation.save(validation.state_path(), state)
        validation.verify_build(state['ue4ss_loader_manifest'])
    except BaseException:
        target.write_bytes(before)
        row['sha256'] = old_hash
        validation.save(validation.state_path(), state)
        raise
    receipt = {'token': token, 'state_file': state['state_file'], 'log_offset': len(text),
               'candidate': candidate.name, 'candidate_manifest_sha256': digest(candidate / MANIFEST),
               'payload_sha256': row['sha256'], 'probe_source_sha256': digest(Path(__file__)),
               'input_sent': False, 'assembly_started': False, 'acceptance_claimed': False}
    validation.save(work / ('startup-terrain-' + token + '.json'), receipt)
    return dict(receipt, next_step='Reload this staged one-shot probe with Ctrl+R in the verified research window')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('stage', 'render-test'))
    args = parser.parse_args()
    if args.action == 'stage':
        print(json.dumps(stage(), ensure_ascii=False))
    else:
        path = ROOT / 'runtime/startup-terrain-preflight-test.lua'
        path.write_bytes(render(ROOT / 'runtime/release-candidates' / expected()[-1], int(time.time()) + 120, '123'))
        print(path)
