"""研究窗口真实F6、F8和F12；仅显式开发装配允许活动对象销毁。"""
import json
from pathlib import Path
import time
import ahua_practice as practice
import research_game_menu as menu
from test_player_skill_batch import wait_for
from collect_active_disposal import proof


def main():
    owner,state=practice.owned_session()
    assert owner['phase']=='armed'and owner.get('active_skill_disposal_trial')
    assert min(state['deadline_unix'],state['control_probe_expires_at']-20)-time.time()>85
    path=practice.log_path(state);offset=len(path.read_text(encoding='utf-8',errors='replace'))
    menu.click(0,0,2560,1600,'control_enter')
    tail=wait_for(path,offset,lambda t:'[PBZBossControl] enter success=true state=ACTIVE'in t,8,True)
    assert '[PBZBossControl] enter success=true state=ACTIVE'in tail
    menu.click(0,0,2560,1600,'control_death_skill08')
    tail=wait_for(path,offset,lambda t:proof(t)['passed'],30)
    result=proof(tail)
    work=Path(state['work']);deploy=max(work.glob('control-lifecycle-deployment-*.json'),key=lambda p:p.stat().st_mtime_ns)
    row={'at':time.time(),'state_file':state['state_file'],'log_offset':offset,'log_end':offset+len(tail),
         'deployment_file':deploy.name,'proof':result}
    target=work/('active-disposal-actions-'+str(time.time_ns())+'.json')
    target.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (work/'active-disposal-actions.json').write_bytes(target.read_bytes())
    print(json.dumps({'passed':result['passed'],'proof':result},ensure_ascii=False))
    return 0 if result['passed']else 1


if __name__=='__main__':raise SystemExit(main())
