"""Freeze missing metadata only: corrected YouLong config and YanQianSui ability types."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, OUT, BUILD, sha, write_json
from build_boss_identity_probe import requests

RECEIPT = 'research/boss-adaptation/identity-receipts/20261115-090045.json'
PREFIX = '/PBZCombatAsset/ActorData/Mobs/'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def plan(root=ROOT):
    receipt_path = root / RECEIPT
    receipt = read(receipt_path)
    assert receipt['target_build_sha256'] == BUILD and receipt['metadata_only'] and not receipt['playable']
    for name, expected in receipt['sources'].items():
        source = (root / name).resolve()
        assert source.is_relative_to(root.resolve()) and sha(source) == expected, 'Identity source changed: ' + name
    rows = {row['id']: row for row in receipt['candidates']}
    yan, dragon = rows['073_yanqiansui'], rows['056_youlong']
    assert yan['identity_verified'] and not dragon['identity_verified']
    assert dragon['checks']['exact_class'] and len(dragon['observed_cdo_config']) == 1
    observed = dragon['observed_cdo_config'][0].split(' ', 1)[1]
    package, leaf = observed.rsplit('.', 1)
    assert package.startswith(PREFIX + '056_YouLong/') and package.rsplit('/', 1)[-1] == leaf
    assert re.fullmatch(r'/[A-Za-z0-9_/]+', package)
    class_package = dragon['class_path'].split('.', 1)[0]
    candidate = {'id': dragon['id'], 'resource_folder': '056_YouLong',
        'class_candidates': [{'package': class_package}], 'config_candidates': [package],
        'enabled': False, 'playable': False, 'identity_verified': False,
        'correction_source': {'receipt': RECEIPT, 'sha256': sha(receipt_path),
            'observed_cdo_config': dragon['observed_cdo_config'][0],
            'previous_rejected_config': dragon['config_path'],
            'runtime_revalidation_required': True}}
    dossier_path = root / 'research/boss-adaptation/dossiers/073_yanqiansui.json'
    dossier = read(dossier_path)
    assert dossier['metadata_identity']['receipt_sha256'] == sha(receipt_path)
    assert dossier['metadata_identity']['identity_verified']
    assets = sorted(set(dossier['resources'].get('ability_clue', [])
        + dossier['resources'].get('ability_dependency_clue', [])))
    assert 1 <= len(assets) <= 64
    abilities = []
    for asset in assets:
        assert asset.startswith(PREFIX + '073_YanQianSui/') and re.fullmatch(r'/[A-Za-z0-9_/]+', asset)
        name = asset.rsplit('/', 1)[-1]
        assert name.startswith('GA_')
        abilities.append({'id': yan['id'], 'role': 'ability', 'package': asset,
            'lookup_path': asset + '.' + name + '_C',
            'lookup_path_derivation': 'Conventional class suffix from observed package; metadata request only.',
            'granted_to_actor': False, 'playable': False})
    return candidate, requests(candidate), abilities, {
        RECEIPT: sha(receipt_path), str(dossier_path.relative_to(root)).replace('\\', '/'): sha(dossier_path)}


def render(identity, abilities, fingerprint):
    rows = identity + abilities
    encoded = '\n'.join(' ' + '{id=' + json.dumps(row['id']) + ',role=' + json.dumps(row['role'])
        + ',path=' + json.dumps(row['lookup_path']) + ',config=' + json.dumps(row.get('expected_config', '')) + '},'
        for row in rows)
    return '''-- Frozen metadata only. No actor creation, grants, possession or activation.
local requests={
ROWS
}
local deadline=os.time()+90
local next_item,busy=1,false
local function emit(prefix,event,value) print(prefix..':'..event..'='..tostring(value)..'\\n') end
emit('PBZ_MULTI_ID','START','FINGERPRINT')
emit('PBZ_BOSS_META','START','FINGERPRINT')
LoopAsync(100,function()
 if busy then return false end
 if os.time()>=deadline then emit('PBZ_BOSS_META','STOP','deadline');return true end
 if next_item>#requests then
  emit('PBZ_MULTI_ID','END','FINGERPRINT')
  emit('PBZ_BOSS_META','END','FINGERPRINT');return true
 end
 busy=true
 local row=requests[next_item];next_item=next_item+1
 ExecuteInGameThread(function()
  local prefix=row.role=='ability' and 'PBZ_BOSS_META' or 'PBZ_MULTI_ID'
  local ok,why=pcall(function()
   assert(os.time()<deadline,'metadata batch expired')
   local asset=LoadAsset(row.path)
   assert(asset and asset:IsValid(),'asset unavailable')
   local full=asset:GetFullName()
   assert(full:match('^[^ ]+ (.+)$')==row.path,'asset identity changed')
   if row.role=='ability' then
    assert(asset:IsA('/Script/CoreUObject.Class'),'ability class required')
    local defaults=asset:GetCDO()
    assert(defaults and defaults:IsValid(),'ability CDO unavailable')
    assert(defaults:IsA('/Script/GameplayAbilities.GameplayAbility'),'not a gameplay ability')
    local kind=defaults:IsA('/Script/SGameAI.RunSubtreeAbility') and 'subtree' or 'leaf'
    emit(prefix,'ABILITY',row.id..'|'..row.path..'|'..kind)
   else
    emit(prefix,'ASSET',row.id..'|'..row.role..'|'..full)
    if row.role=='character' then
     assert(asset:IsA('/Script/CoreUObject.Class'),'character class required')
     local cls,depth=asset,0
     while cls and cls:IsValid() and depth<16 do
      emit(prefix,'LINEAGE',row.id..'|'..depth..'|'..cls:GetFullName())
      cls=cls:GetSuperStruct();depth=depth+1
     end
     assert(not(cls and cls:IsValid()),'lineage exceeds bound')
     local defaults=asset:GetCDO()
     assert(defaults and defaults:IsValid(),'character CDO unavailable')
     local config=defaults['Actor Config']
     assert(config and config:IsValid(),'default config unavailable')
     local actual=config:GetFullName()
     emit(prefix,'CDO_CONFIG',row.id..'|'..actual)
     assert(actual:match('^[^ ]+ (.+)$')==row.config..'.'..row.config:match('([^/]+)$'),'default config differs')
     emit(prefix,'DEFAULT_CONFIG_MATCH',row.id)
    else
     assert(asset:IsA('/Script/Engine.PrimaryDataAsset'),'primary data asset required')
     emit(prefix,'NAME',row.id..'|'..asset:GetCharacterName():ToString())
    end
   end
  end)
  if not ok then emit(prefix,'REJECTED',row.id..'|'..row.role..'|'..row.path..'|'..tostring(why)) end
  busy=false
 end)
 return false
end)
'''.replace('ROWS', encoded).replace('FINGERPRINT', fingerprint)


def build(root=ROOT):
    candidate, identity, abilities, evidence = plan(root)
    source_names = ('tools/build_boss_followup_batch.py', 'tools/build_boss_identity_probe.py',
        'tools/run_boss_identity_batch.py', 'tools/collect_boss_identity.py',
        'tools/collect_boss_followup.py', 'tests/test_boss_followup.py', 'tests/test_boss_followup_probe.lua')
    sources = {name: sha(root / name) for name in source_names}
    fingerprint = hashlib.sha256(json.dumps({'candidate': candidate, 'abilities': abilities,
        'evidence': evidence, 'sources': sources}, sort_keys=True).encode()).hexdigest()[:16]
    target = root / 'research/boss-adaptation/followup-batches' / ('metadata-' + fingerprint)
    if target.exists():
        verify(target, root)
        return target
    target.mkdir(parents=True)
    write_json(target / 'candidates/056_youlong.json', candidate)
    manifest = {'schema_version': 1, 'fingerprint': fingerprint, 'target_build_sha256': BUILD,
        'source_files': sources, 'evidence': evidence, 'offline_only': True, 'game_started': False,
        'candidate_files': {'candidates/056_youlong.json': sha(target / 'candidates/056_youlong.json')},
        'next_batch': {'kind': 'missing_metadata_only', 'candidate_ids': ['056_youlong'],
            'ability_metadata_candidate': '073_yanqiansui', 'max_seconds': 90,
            'repeat_name_scan': False, 'repeat_verified_identity': False,
            'gameplay_input_allowed': False, 'ability_activation_allowed': False}}
    write_json(target / 'manifest.json', manifest)
    script = target / 'identity-probe.lua'
    script.write_text(render(identity, abilities, fingerprint), encoding='utf-8')
    write_json(target / 'identity-probe-manifest.json', {'schema_version': 1,
        'target_build_sha256': BUILD, 'batch_manifest_sha256': sha(target / 'manifest.json'),
        'script_sha256': sha(script), 'requests': identity, 'ability_requests': abilities,
        'batch_fingerprint': fingerprint, 'auto_deploy': False, 'runtime_verified': False,
        'scope': 'One corrected config pair and bounded ability CDO metadata; not live grants or gameplay.'})
    verify(target, root)
    return target


def verify(batch, root=ROOT):
    manifest, probe = read(batch / 'manifest.json'), read(batch / 'identity-probe-manifest.json')
    assert manifest['target_build_sha256'] == probe['target_build_sha256'] == BUILD
    for name, expected in {**manifest['source_files'], **manifest['evidence']}.items():
        path = (root / name).resolve()
        assert path.is_relative_to(root.resolve()) and sha(path) == expected, 'Frozen source changed: ' + name
    for name, expected in manifest['candidate_files'].items():
        path = (batch / name).resolve()
        assert path.is_relative_to(batch.resolve()) and sha(path) == expected
    assert sha(batch / 'manifest.json') == probe['batch_manifest_sha256']
    assert sha(batch / 'identity-probe.lua') == probe['script_sha256']
    assert len(probe['requests']) == 2 and 1 <= len(probe['ability_requests']) <= 64
    assert probe['batch_fingerprint'] == manifest['fingerprint']
    assert (batch / 'identity-probe.lua').read_text(encoding='utf-8') == render(
        probe['requests'], probe['ability_requests'], manifest['fingerprint'])
    return manifest, probe


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    batch = args.verify or build()
    _, probe = verify(batch)
    print(json.dumps({'batch': str(batch), 'identity_lookups': len(probe['requests']),
        'ability_metadata_lookups': len(probe['ability_requests']), 'game_started': False,
        'playable_bosses_added': 0}, ensure_ascii=False))
