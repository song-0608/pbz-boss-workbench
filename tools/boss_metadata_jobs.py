"""Shared bounded character/ability metadata jobs; never grants or activates skills."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from build_boss_identity_probe import PACKAGE

SOURCES=('tools/boss_metadata_jobs.py','tools/run_boss_identity_batch.py',
    'tools/collect_boss_metadata_jobs.py','tests/test_boss_metadata_jobs.py',
    'tests/test_boss_metadata_jobs.lua')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')


def catalog_jobs(jobs,root):
    path=root/'research/boss-adaptation/catalog.json';catalog=json.loads(path.read_bytes())
    assert catalog['target_build_sha256']==BUILD
    for source in catalog['sources']:
        origin=(root/source['path']).resolve()
        assert origin.is_relative_to((root/'evidence').resolve()) and sha(origin)==source['sha256']
    requested={j['id'] for j in jobs}
    candidates=[c for c in catalog['candidates'] if c['id'] in requested and not c.get('reference_only')]
    assert {c['id'] for c in candidates}==requested,'Observed non-reference candidates required'
    expected={j['key']:j for c in candidates for j in jobs_for(c)}
    assert all(expected.get(j['key'])==j for j in jobs),'Job differs from observed catalog'
    return sha(path)


def jobs_for(candidate):
    identifier,folder=candidate['id'],candidate['resource_folder']
    if not re.fullmatch(r'[a-z0-9_]{1,80}',identifier):
        raise ValueError('Exact resource identifier required')
    prefix='/PBZCombatAsset/ActorData/Mobs/'+folder+'/'
    jobs=[]
    configs=[]
    for asset in candidate['assets']:
        package=asset['package']
        if not PACKAGE.fullmatch(package) or not package.startswith(prefix):
            raise ValueError('Same-folder observed resource required')
        if asset['role']=='actor_config_clue':
            configs.append(package+'.'+package.rsplit('/',1)[-1])
    for asset in candidate['assets']:
        role={'character_blueprint_clue':'character','ability_clue':'ability',
            'ability_dependency_clue':'ability'}.get(asset['role'])
        if role is None:
            continue
        package=asset['package'];leaf=package.rsplit('/',1)[-1]
        job=dict(id=identifier,role=role,package=package,lookup_path=package+'.'+leaf+'_C',
            lookup_path_derivation='Conventional Unreal class suffix; request only, not verified identity.',
            config_candidates=sorted(set(configs)) if role=='character' else [])
        job['key']=hashlib.sha256(canonical(job)).hexdigest()[:20]
        jobs.append(job)
    if len({job['key'] for job in jobs})!=len(jobs):
        raise ValueError('Duplicate observed metadata job')
    return jobs


def batches(candidates,job_keys=None):
    grouped=[jobs_for(candidate) for candidate in candidates]
    if job_keys is not None:
        selected=set(job_keys)
        assert selected<={job['key'] for group in grouped for job in group},'Observed retry job keys required'
        grouped=[[job for job in group if job['key'] in selected] for group in grouped]
    result=[];current=[];identifiers=set()
    for candidate,candidate_jobs in zip(candidates,grouped):
        if not candidate_jobs:
            continue
        if current and len(candidate_jobs)<=64 and (len(current)+len(candidate_jobs)>64
                or candidate['id'] not in identifiers and len(identifiers)==3):
            result.append(current);current=[];identifiers=set()
        for job in candidate_jobs:
            if current and (len(current)==64 or job['id'] not in identifiers and len(identifiers)==3):
                result.append(current);current=[];identifiers=set()
            current.append(job);identifiers.add(job['id'])
    if current:
        result.append(current)
    return result


def render(jobs,fingerprint):
    assert 1<=len(jobs)<=64 and len({j['id'] for j in jobs})<=3
    assert re.fullmatch(r'[0-9a-f]{20}',fingerprint)
    encoded='\n'.join(' {key='+json.dumps(j['key'])+',role='+json.dumps(j['role'])
        +',path='+json.dumps(j['lookup_path'])+'},' for j in jobs)
    return '''-- Frozen read-only metadata. No Actors, grants, possession or activation.
local jobs={
ROWS
}
local fingerprint='FINGERPRINT'
local deadline=os.time()+90
local index,busy,stopped,polls=1,false,false,0
local function emit(event,value)print('PBZ_ADAPTER_META:'..event..'='..value..'\\n')end
local function clean(value)return tostring(value):gsub('[%c|]',' '):sub(1,1024)end
local function path(object)
 assert(object and object:IsValid(),'metadata object unavailable')
 local value=assert(object:GetFullName():match('^[^ ]+ (/.+)$'),'metadata path unavailable')
 assert(#value<=1024 and value:match('^/[A-Za-z0-9_/%.]+$'),'metadata path changed')
 return value
end
local function stop(reason)
 if not stopped then stopped=true;emit('STOP',reason)end
 return true
end
emit('START',fingerprint)
LoopAsync(100,function()
 if stopped then return true end
 polls=polls+1
 if os.time()>=deadline or polls>900 then return stop('deadline or polling budget')end
 if busy then return false end
 if index>#jobs then stopped=true;emit('END',fingerprint);return true end
 local job=jobs[index];index=index+1;busy=true
 ExecuteInGameThread(function()
  if stopped then return end
  if os.time()>=deadline then stop('queued job expired');busy=false;return end
  local ok,why=pcall(function()
   local asset=LoadAsset(job.path)
   assert(path(asset)==job.path and asset:IsA('/Script/CoreUObject.Class'),'exact class required')
   local defaults=asset:GetCDO();assert(defaults and defaults:IsValid(),'metadata CDO unavailable')
   if job.role=='ability' then
    assert(defaults:IsA('/Script/GameplayAbilities.GameplayAbility'),'not a gameplay ability')
    local kind=defaults:IsA('/Script/SGameAI.RunSubtreeAbility')and'subtree'or'leaf'
    emit('OUTCOME',job.key..'|ability|'..job.path..'|'..kind)
   else
    local lineage,seen,npc={}, {},false
    local cls=asset
    while cls and cls:IsValid()and #lineage<16 do
     local name=path(cls);assert(not seen[name],'cyclic class lineage');seen[name]=true
     lineage[#lineage+1]=name;npc=npc or name=='/Script/ProjectPBZ.PBZCharacter_NPC'
     cls=cls:GetSuperStruct()
    end
    assert(not(cls and cls:IsValid())and npc and lineage[#lineage]=='/Script/CoreUObject.Object',
     'complete native NPC lineage required')
    local config=defaults['Actor Config'];local config_path=path(config)
    assert(config:IsA('/Script/Engine.PrimaryDataAsset'),'Actor Config data asset required')
    local name=config:GetCharacterName():ToString()
    assert(type(name)=='string'and #name>0 and #name<=512 and not name:find('[%c|]'),'bounded display name required')
    emit('OUTCOME',job.key..'|character|'..job.path..'|'..config_path..'|'..name..'|'..table.concat(lineage,','))
   end
  end)
  if not ok then emit('REJECTED',job.key..'|'..clean(why))end
  busy=false
 end)
 return false
end)
'''.replace('ROWS',encoded).replace('FINGERPRINT',fingerprint)


def freeze(jobs,parent,root=ROOT):
    catalog_sha256=catalog_jobs(jobs,root)
    sources={name:sha(root/name) for name in SOURCES}
    identity=dict(target_build_sha256=BUILD,jobs=jobs,source_files=sources,catalog_sha256=catalog_sha256)
    fingerprint=hashlib.sha256(canonical(identity)).hexdigest()[:20]
    target=Path(parent)/('metadata-'+fingerprint)
    raw=render(jobs,fingerprint).encode('utf-8')
    if target.exists():
        verify_batch(target,root)
        return target
    target.mkdir(parents=True)
    (target/'metadata-probe.lua').write_bytes(raw)
    manifest=dict(schema_version=1,kind='adapter_metadata_jobs',batch_fingerprint=fingerprint,
        **identity,script_sha256=hashlib.sha256(raw).hexdigest(),max_seconds=90,
        max_requests=64,max_poll_callbacks=900,game_started=False,deployed=False,runtime_verified=False,
        playable=False,ability_activation_allowed=False)
    write_json(target/'metadata-probe-manifest.json',manifest)
    verify_batch(target,root)
    return target


def verify_batch(target,root=ROOT):
    target=Path(target);manifest=json.loads((target/'metadata-probe-manifest.json').read_bytes())
    assert manifest['schema_version']==1 and manifest['kind']=='adapter_metadata_jobs'
    assert manifest['target_build_sha256']==BUILD
    for key in ('game_started','deployed','runtime_verified','playable','ability_activation_allowed'):
        assert manifest[key] is False,key
    assert manifest['source_files']=={name:sha(root/name) for name in SOURCES}
    assert manifest['catalog_sha256']==catalog_jobs(manifest['jobs'],root)
    identity={key:manifest[key] for key in ('target_build_sha256','jobs','source_files','catalog_sha256')}
    fingerprint=hashlib.sha256(canonical(identity)).hexdigest()[:20]
    assert fingerprint==manifest['batch_fingerprint'] and target.name=='metadata-'+fingerprint
    assert manifest['max_seconds']==90 and manifest['max_requests']==64 and manifest['max_poll_callbacks']==900
    assert len({j['key'] for j in manifest['jobs']})==len(manifest['jobs'])
    assert {p.name for p in target.iterdir()}=={'metadata-probe.lua','metadata-probe-manifest.json'}
    raw=(target/'metadata-probe.lua').read_bytes()
    assert raw==render(manifest['jobs'],fingerprint).encode('utf-8')
    assert hashlib.sha256(raw).hexdigest()==manifest['script_sha256']
    return manifest


def analyze(lines,manifest):
    expected={j['key']:j for j in manifest['jobs']}
    observed={};started=False;ended=False
    fingerprint=manifest['batch_fingerprint']
    for line in lines:
        match=re.search(r'PBZ_ADAPTER_META:([A-Z_]+)=(.*)',line)
        if not match:
            continue
        event,payload=match.groups();payload=payload.strip()
        if event=='START':
            assert not started and not ended and payload==fingerprint,'exact single metadata batch required'
            started=True;continue
        assert started and not ended,'metadata outcome outside its batch'
        if event=='END':
            assert payload==fingerprint and set(observed)==set(expected),'complete metadata batch required'
            ended=True;continue
        assert event in ('OUTCOME','REJECTED'),'stopped or unknown metadata event'
        parts=payload.split('|');job=expected.get(parts[0])
        assert job and job['key'] not in observed,'unknown or duplicate metadata outcome'
        row=dict(key=job['key'],id=job['id'],class_path=job['lookup_path'],role=job['role'],
            metadata_verified=False,identity_verified=False,live_grant_verified=False,
            activation_verified=False,playable=False)
        if event=='REJECTED':
            assert len(parts)==2 and parts[1],'bounded rejection required'
            row['rejection']=parts[1]
        else:
            assert len(parts)>=4 and parts[1]==job['role'] and parts[2]==job['lookup_path'],'metadata identity mismatch'
            if job['role']=='ability':
                assert len(parts)==4 and parts[3] in ('leaf','subtree'),'ability kind required'
                row['ability_kind']=parts[3]
            else:
                assert len(parts)==6 and re.fullmatch(r'/[A-Za-z0-9_/]+\.[A-Za-z0-9_]+',parts[3]),'character config path required'
                assert 0<len(parts[4].encode('utf-8'))<=512 and not re.search(r'[\x00-\x1f\x7f]',parts[4]),'bounded character name required'
                lineage=parts[5].split(',')
                assert 1<=len(lineage)<=16 and len(set(lineage))==len(lineage)
                assert all(re.fullmatch(r'/[A-Za-z0-9_/]+\.[A-Za-z0-9_]+',p) for p in lineage)
                assert lineage[0]==job['lookup_path'] and lineage[-1]=='/Script/CoreUObject.Object'
                assert '/Script/ProjectPBZ.PBZCharacter_NPC' in lineage,'NPC lineage required'
                row.update(observed_config=parts[3],display_name=parts[4],lineage=lineage,
                    config_in_observed_candidates=parts[3] in job['config_candidates'])
            row['metadata_verified']=True
        observed[job['key']]=row
    assert started and ended and set(observed)==set(expected),'complete metadata outcomes required'
    return [observed[j['key']] for j in manifest['jobs']]
