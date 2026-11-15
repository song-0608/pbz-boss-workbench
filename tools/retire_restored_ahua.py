"""用途：F10已核实恢复后，在同一离线游戏清理本工具生成的角色，允许集中修复后热重载。"""
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import ahua_practice as practice
import official_validation as v
import research_game_menu as menu


def owned_references(segment,names):
    """用途：死亡后不能再从Pawn反查AI；只使用同轮日志中成对登记的完整身份。"""
    rows=re.findall(r'OWNED_RETIRE_REFERENCE=(actor|controller)\|([^\r\n|]+)\|address=(\d+)\|class=([^\r\n]+)',segment)
    if len(rows)!=2*len(names):raise RuntimeError('Complete paired owned references required')
    pairs=[];seen=set()
    expected={'actor':'BlueprintGeneratedClass /PBZCombatAsset/ActorData/Mobs/042_AHua/BP_Monster_AHua_GuiTouDao.BP_Monster_AHua_GuiTouDao_C',
              'controller':'BlueprintGeneratedClass /PBZCombatAsset/Prototypes/AI/BP_PBZAIController.BP_PBZAIController_C'}
    for index,name in enumerate(names):
        pair={}
        for offset,kind in enumerate(('actor','controller')):
            actual,full,address,cls=rows[2*index+offset]
            if actual!=kind or cls!=expected[kind]or(kind=='actor'and full!=name):
                raise RuntimeError('Owned reference order/class/name mismatch')
            if full in seen or int(address)<=0:raise RuntimeError('Duplicate or invalid owned identity')
            seen.add(full);pair[kind]={'name':full,'address':int(address),'class':cls}
        pairs.append(pair)
    return pairs


def retirement_script(references,deadline):
    def literal(ref):
        return '{name='+json.dumps(ref['name'])+',address='+str(ref['address'])+',class='+json.dumps(ref['class'])+'}'
    rows='{'+','.join('{actor='+literal(p['actor'])+',ai='+literal(p['controller'])+'}'for p in references)+'}'
    return '''
ExecuteInGameThread(function()
 local ok,why=pcall(function()
  assert(os.time()<DEADLINE,'retirement lease expired')
  local lifecycle=require('object_lifecycle').new(_G,{binding_verified=true})
  local calls=require('ue_calls').new({find_exact=StaticFindObject,usable=function(o)return lifecycle:usable(o)end})
  local pc
  for _,p in ipairs(FindAllOf('PBZPlayerController')or{})do
   if lifecycle:usable(p)and lifecycle:usable(p.Pawn)and p:GetFullName():find(':PersistentLevel.',1,true)then assert(not pc,'ambiguous player');pc=p end
  end
  assert(pc and pc.Pawn.AttributeSetBase.Health.CurrentValue>0,'living restored player required')
  assert(not pc:IsMoveInputIgnored()and not pc:IsLookInputIgnored(),'control was re-entered after restoration proof')
  local world=calls:world(pc)
  local pending={}
  for _,entry in ipairs(REFERENCES)do
   local actor,ai=calls:optional(entry.actor),calls:optional(entry.ai)
   for _,object in ipairs({actor or false,ai or false})do
    if object then
     local w=calls:world(object)
     assert(w.name==world.name and w.address==world.address,'owned world changed')
     assert(not calls:same(object,pc)and not calls:same(object,pc.Pawn),'restored player rejected')
    end
   end
   if actor then
    assert(ai and calls:same(actor:GetController(),ai)and calls:same(ai:K2_GetPawn(),actor),'owned AI changed')
   elseif ai then
    local pawn=ai:K2_GetPawn()
    if pawn and pawn:IsValid()then
     assert(pawn:GetFullName()==entry.actor.name and pawn:GetAddress()==entry.actor.address
      and pawn:GetClass():GetFullName()==entry.actor.class,'owned AI repurposed')
    end
   end
   pending[#pending+1]={actor=actor,ai=ai,reference=entry}
  end
  for _,entry in ipairs(pending)do
   if entry.actor then entry.actor:K2_DestroyActor()end
   if lifecycle:usable(entry.ai)then entry.ai:K2_DestroyActor()end
   assert(not calls:optional(entry.reference.actor)and not calls:optional(entry.reference.ai),'owned disposal not verified')
  end
  print('PBZ_REARM_RETIRE:PASS='..#pending..' owned actors/controllers engine-unusable; GC not claimed\\n')
  print('PBZ_CONTROL_LIFECYCLE:END=restored owned actors retired for same-process rearm\\n')
 end)
 if not ok then print('PBZ_REARM_RETIRE:REJECTED='..tostring(why)..'\\n')end
end)
'''.replace('DEADLINE',str(deadline)).replace('REFERENCES',rows)


def retire():
    owner, state = practice.owned_session()
    path = practice.log_path(state)
    text = path.read_text(encoding='utf-8', errors='replace')
    segment = text[text.rfind('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR='):]
    from control_action_evidence import restoration_result
    events = re.findall(r'\[PBZBossControl\] (enter|exit|menu_exit|auto_exit) success=true state=(ACTIVE|OFF)', segment)
    if not events or events[-1] not in (('exit', 'OFF'),('menu_exit','OFF'),('auto_exit','OFF')):
        raise RuntimeError('Player restoration must already be verified; preserve current session')
    if not restoration_result(segment, events[-1][0])['passed']:
        raise RuntimeError('Complete player and camera restoration evidence required; preserve current session')
    restored = segment[max(segment.rfind('[PBZBossControl] '+label+' success=true')
                           for label in ('exit','menu_exit','auto_exit')):]
    for token in ('ORIGINAL_PLAYER_POSITION_DELTA=0.0', 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0'):
        if token not in restored:
            raise RuntimeError('Missing original-player restoration evidence: ' + token)
    names = list(dict.fromkeys(re.findall(r'PBZ_CONTROL_LIFECYCLE:(?:SPAWNED|TRAINING_TARGET(?:_[12])?)=([^\r\n]+)', segment)))
    if not 2 <= len(names) <= 3 or any(not name.startswith('BP_Monster_AHua_GuiTouDao_C ') for name in names):
        raise RuntimeError('Exact bounded owned-character names required')
    v.verify_build(state['ue4ss_loader_manifest'])
    if v.c.baseline.formal_files() != state['formal_before']:
        raise RuntimeError('Formal files changed; preserve session')
    # 用途：窗口无法取得焦点时，不能先覆盖载体或将监督器切进retiring。
    menu.click(0, 0, 2560, 1600, 'control_focus')
    # 用途：这里没有跨进程写内存；通过已在游戏线程验证的接口销毁明确属于本轮的临时角色。
    references=owned_references(segment,names)
    script=retirement_script(references,min(int(time.time())+35,int(state['deadline_unix'])-15))
    row = next(r for r in state['ue4ss_loader_manifest'] if r['physical_path'].replace('\\', '/').endswith('/Mods/PBZObserveAI/Scripts/main.lua'))
    carrier = Path(row['physical_path'])
    work = Path(state['work'])
    stamp=str(time.time_ns())
    (work / ('before-same-process-retirement-'+stamp+'.lua')).write_bytes(carrier.read_bytes())
    (work / 'before-same-process-retirement.lua').write_bytes(carrier.read_bytes())
    data = script.encode('utf-8')
    row['sha256'] = hashlib.sha256(data).hexdigest()
    v.save(v.state_path(), state)
    # 用途：F10恢复证据已通过；进入明确的清理阶段，旧按键监督器停止读取下一次装配的日志。
    owner['phase']='retiring'
    practice.save_owner(owner)
    carrier.write_bytes(data)
    menu.click(0, 0, 2560, 1600, 'control_reload')
    practice.wait_tokens(path, ['PBZ_REARM_RETIRE:PASS='], timeout=8, offset=len(text))
    owner.update(phase='game_launched', retired_names=names)
    practice.save_owner(owner)
    report={'names': names, 'references':references,'restoration_preceded_cleanup': True,
           'destroy_requested': True, 'engine_disposal_verified':True,'garbage_collection_verified': False, 'game_restarted': False}
    v.save(work / ('same-process-retirement-'+stamp+'.json'),report)
    v.save(work / 'same-process-retirement.json',report)
    print('Owned training actors retired after verified restoration; same game process ready for rearm.')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    retire()
