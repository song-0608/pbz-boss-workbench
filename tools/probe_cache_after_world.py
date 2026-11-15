"""Read-only cache identity check after a restored scene retires and bounded layout attempts end."""
import hashlib
import json
from pathlib import Path
import time
import ahua_practice as practice
import official_validation as v
import research_game_menu as menu
from control_action_evidence import control_identity,restoration_result


def main():
    owner,state=practice.owned_session();path=practice.log_path(state)
    text=path.read_text(encoding='utf-8',errors='replace');identity=control_identity(text)
    retired=text.rfind('IDLE_WORLD_OBJECTS_RETIRED=')
    assert retired>0 and restoration_result(text[:retired])['passed']
    tail=text[retired:]
    assert 'PREREQUISITE_RETRY_SAFE=true'in tail and 'END=initialization rejected before takeover; original player restoration verified'in tail
    assert '[PBZBossControl] enter success=true'not in tail and 'state=FAULTED'not in text
    assert v.c.baseline.formal_files()==state['formal_before']
    v.verify_build(state['ue4ss_loader_manifest']);menu.click(0,0,2560,1600,'control_focus')
    old_world=identity['world_id'].split('|');old_name=old_world[-2];old_address=int(old_world[-1])
    deadline=min(int(time.time())+30,int(state['deadline_unix'])-15)
    assert deadline>time.time()+10
    script='''ExecuteInGameThread(function()
 local ok,why=pcall(function()
  assert(os.time()<DEADLINE,'cache probe expired')
  local lifecycle=require('object_lifecycle').new(_G,{binding_verified=true})
  local calls=require('ue_calls').new({find_exact=StaticFindObject,find_all=FindAllOf,usable=function(o)return lifecycle:usable(o)end})
  local pc
  for _,p in ipairs(FindAllOf('PBZPlayerController')or{})do
   if lifecycle:usable(p)and lifecycle:usable(p.Pawn)and p:GetFullName():find(':PersistentLevel.',1,true)then assert(not pc,'ambiguous player');pc=p end
  end
  assert(pc and pc.Pawn.AttributeSetBase.Health.CurrentValue>0,'living gameplay player required')
  assert(not pc:IsMoveInputIgnored()and not pc:IsLookInputIgnored(),'player input not restored')
  local world=pc:GetWorld();local ref=calls:reference(world)
  assert(ref.name==OLD_NAME and ref.address~=OLD_ADDRESS,'new World identity required')
  local path=assert(ref.name:match('^[^ ]+ (.+)$'))
  for i=1,25 do assert(calls:same(calls:resolve(ref),world),'cache returned stale World')end
  local old={name=OLD_NAME,address=OLD_ADDRESS,class=ref.class}
  local retired=calls:retirement_optional(old)
  -- 地址在已确认退役后可被其他World复用；复用不等于原完整身份复活。
  assert(retired==nil or retired.retirement_ambiguous==true,'exact old World remains registered')
  assert(not pcall(calls.resolve,calls,old),'old World receipt must reject replacement')
  print('PBZ_CACHE_WORLD:PASS=old='..(OLD_ADDRESS)..'|new='..ref.address..'|queries=25|input_restored=true|old_receipt_rejected=true|old_address_reused='..tostring(retired~=nil)..'\\n')
 end)
 if not ok then print('PBZ_CACHE_WORLD:REJECTED='..tostring(why)..'\\n')end
end)
'''.replace('DEADLINE',str(deadline)).replace('OLD_NAME',json.dumps(old_name)).replace('OLD_ADDRESS',str(old_address))
    row=next(r for r in state['ue4ss_loader_manifest']if r['physical_path'].replace('\\','/').endswith('/Mods/PBZObserveAI/Scripts/main.lua'))
    carrier=Path(row['physical_path']);work=Path(state['work'])
    (work/'before-cache-world-probe.lua').write_bytes(carrier.read_bytes())
    raw=script.encode('utf-8');(work/'cache-world-probe.lua').write_bytes(raw)
    row['sha256']=hashlib.sha256(raw).hexdigest();v.save(v.state_path(),state);carrier.write_bytes(raw)
    menu.click(0,0,2560,1600,'control_reload')
    result=practice.wait_tokens(path,['PBZ_CACHE_WORLD:PASS='],timeout=8,offset=len(text))
    v.save(work/'cache-world-probe.json',{'passed':True,'at':v.utc8(),'state_file':state['state_file'],
        'old_identity':identity,'script_sha256':hashlib.sha256(raw).hexdigest(),
        'log_offset':len(text),'log_end':len(text)+len(result),'read_only':True,'reassembly_blocked_by_visibility':True})
    print('New World cache identity, 25 repeated queries, old receipt rejection and restored input passed')


if __name__=='__main__':main()
