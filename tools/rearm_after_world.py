"""旧World全量销毁后登记同进程重新装配；不借用F10恢复主角的旧证据。"""
import hashlib
from pathlib import Path
import time
import ahua_practice as practice
import official_validation as v
from control_action_evidence import world_retirement_result
def main():
    owner,state=practice.owned_session()
    if owner.get('phase')!='armed'or not owner.get('scene_transition_trial'):raise RuntimeError('Explicit active transition validation required')
    text=practice.log_path(state).read_text(encoding='utf-8',errors='replace')
    proof=world_retirement_result(text[owner['log_offset']:])
    if not proof['passed']:raise RuntimeError('Complete old-world disposal and owned cleanup required')
    tail=text[owner['log_offset']+proof['retirement_event_end']:]
    if 'SPAWN_ATTEMPT='in tail:raise RuntimeError('A new assembly already began; preserve it')
    if state['deadline_unix']-time.time()<180:raise RuntimeError('New assembly cleanup margin required')
    v.verify_build(state['ue4ss_loader_manifest'])
    if v.c.baseline.formal_files()!=state['formal_before']:raise RuntimeError('Formal files changed')
    work=Path(state['work']);stamp=str(time.time_ns())
    (work/('before-post-world-rearm-'+stamp+'.log')).write_text(text,encoding='utf-8')
    v.save(work/('post-world-rearm-'+stamp+'.json'),{'at':v.utc8(),'proof':proof,
        'log_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'no_game_restart':True})
    owner.update(phase='game_launched',world_retirement_rearm=True);practice.save_owner(owner)
    print('Disposed old World verified; same process can assemble after original game loading completes.')
if __name__=='__main__':main()
