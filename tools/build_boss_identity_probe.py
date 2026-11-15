"""Generate an inert read-only identity probe for a frozen candidate batch, never deploy it."""
import argparse
import json
from pathlib import Path
import re

from boss_adaptation_workflow import OUT, BUILD, sha, write_json

PACKAGE=re.compile(r'^/PBZCombatAsset/ActorData/Mobs/[A-Za-z0-9_]+/[A-Za-z0-9_/]+$')


def requests(candidate):
    folder=candidate['resource_folder']
    prefix='/PBZCombatAsset/ActorData/Mobs/'+folder+'/'
    rows=[]
    if len(candidate['class_candidates'])!=1 or len(candidate['config_candidates'])!=1:
        raise ValueError('First batch requires one character and one config candidate; ambiguous pairs stay offline')
    for role,package in [('character',candidate['class_candidates'][0]['package']),
                         ('config',candidate['config_candidates'][0])]:
        if not PACKAGE.fullmatch(package) or not package.startswith(prefix):
            raise ValueError('Only observed same-folder Mobs packages are allowed')
        leaf=package.rsplit('/',1)[-1]
        rows.append({'id':candidate['id'],'role':role,'package':package,
            'lookup_path':package+'.'+leaf+('_C' if role=='character' else ''),
            'lookup_path_derivation':'Conventional Unreal object suffix; request only, not verified identity.',
            'expected_config':candidate['config_candidates'][0]})
    return rows


def render(rows):
    encoded='\n'.join(' {id='+json.dumps(r['id'])+',role='+json.dumps(r['role'])+
        ',path='+json.dumps(r['lookup_path'])+',config='+json.dumps(r['expected_config'])+'},' for r in rows)
    return '''-- Generated offline. Read-only asset metadata only; not a playable profile.
-- Must run only in the existing protected, idle, fixed-build research carrier.
local requests={
ROWS
}
local deadline=os.time()+90
local next_item,busy=1,false
local function emit(event,value) print('PBZ_MULTI_ID:'..event..'='..tostring(value)..'\\n') end
emit('START','read-only metadata; no spawning, possession or ability activation')
LoopAsync(100,function()
 if os.time()>=deadline then emit('STOP','deadline');return true end
 if busy then return false end
 if next_item>#requests then emit('END','all requests processed; unverified outcomes remain blocked');return true end
 busy=true
 local row=requests[next_item];next_item=next_item+1
 ExecuteInGameThread(function()
  local ok,why=pcall(function()
   assert(os.time()<deadline,'probe expired before game-thread execution')
   local asset=LoadAsset(row.path)
   assert(asset and asset:IsValid(),'asset unavailable: '..row.path)
   local full=asset:GetFullName()
   assert(full:match('^[^ ]+ (.+)$')==row.path,'loaded asset differs from requested identity')
   emit('ASSET',row.id..'|'..row.role..'|'..full)
   if row.role=='character' then
    assert(asset:IsA('/Script/CoreUObject.Class'),'class metadata required')
    local cls,depth=asset,0
    while cls and cls:IsValid() and depth<16 do
     emit('LINEAGE',row.id..'|'..depth..'|'..cls:GetFullName())
     cls=cls:GetSuperStruct();depth=depth+1
    end
    assert(not(cls and cls:IsValid()),'class lineage exceeds bound')
    local defaults=asset:GetCDO()
    assert(defaults and defaults:IsValid(),'class default object unavailable')
    -- This is a CDO property observation, not a live actor/granted-ability proof.
    local config=defaults['Actor Config']
    assert(config and config:IsValid(),'Actor Config default reference unavailable')
    local actual=config:GetFullName()
    emit('CDO_CONFIG',row.id..'|'..actual)
    local object_path=assert(actual:match('^[^ ]+ (.+)$'),'config path format unavailable')
    assert(object_path:match('^([^%.]+)')==row.config,'default config differs from candidate')
    emit('DEFAULT_CONFIG_MATCH',row.id)
   else
    assert(asset:IsA('/Script/Engine.PrimaryDataAsset'),'config must be a primary data asset')
    emit('NAME',row.id..'|'..asset:GetCharacterName():ToString())
   end
  end)
  if not ok then emit('REJECTED',row.id..'|'..row.role..'|'..tostring(why)) end
  busy=false
 end)
 return false
end)
'''.replace('ROWS',encoded)


def build(batch):
    manifest=json.loads((batch/'manifest.json').read_text(encoding='utf-8'))
    if manifest['target_build_sha256']!=BUILD:
        raise ValueError('Registered build required')
    rows=[]
    for identifier in manifest['next_batch']['candidate_ids']:
        if not re.fullmatch(r'[a-z0-9_]{1,80}',identifier):
            raise ValueError('Invalid candidate identifier')
        relative='candidates/'+identifier+'.json'
        path=batch/relative
        if sha(path)!=manifest['candidate_files'][relative]:
            raise ValueError('Frozen candidate changed; rebuild offline batch')
        candidate=json.loads(path.read_text(encoding='utf-8'))
        rows.extend(requests(candidate))
    if not 1<=len(rows)<=6:
        raise ValueError('Batch allows at most three character/config pairs')
    target=batch/'identity-probe.lua'
    raw=render(rows).encode('utf-8')
    if target.exists() and target.read_bytes()!=raw:
        raise ValueError('Existing frozen probe differs; preserve it and build a new batch')
    target.write_bytes(raw)
    write_json(batch/'identity-probe-manifest.json',{'schema_version':1,'target_build_sha256':BUILD,
        'batch_manifest_sha256':sha(batch/'manifest.json'),'script_sha256':sha(target),
        'requests':rows,'auto_deploy':False,'runtime_verified':False,
        'runtime_preconditions':['Existing protected strictly offline research session, fixed build and active lease.',
            'Idle carrier only; never replace ACTIVE gameplay scripts.',
            'Keep ordinary identity, isolation, input and restoration guards.'],
        'scope':'Six metadata lookups maximum, one scheduled request at a time; no actor creation or gameplay input.'})
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path)
    args=parser.parse_args()
    batch=args.batch or Path(json.loads((OUT/'batches/latest.json').read_text(encoding='utf-8'))['directory'])
    print(json.dumps({'probe':str(build(batch)),'deployed':False},ensure_ascii=False))
