"""Freeze a reviewed native subtree adapter without inventing child execution order.

The runtime is an isolated override of accepted v5 modules, never a player
registry update. Current unique idle grants, exact Actor/CDO and the original
tree weights are checked again before its bounded native scheduler is opened.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_metadata_jobs import canonical
from build_boss_profile_candidate import lua
from build_player_experience_candidate import replace
import boss_combo_dependencies as dependencies
import boss_offline_inventory as inventory
import boss_inventory_spawn_repair as spawn
from mod_installation import active_mod_root, unlinked_path, validate_package

PREFIX = '/PBZCombatAsset/ActorData/Mobs/044_PengMeng/'
REVIEWS = {'044_pengmeng': dict(
    actor=PREFIX+'BP_Monster_PengMeng_Axe.BP_Monster_PengMeng_Axe_C',
    config=PREFIX+'ActorData/ActorC_PengMeng_Axe.ActorC_PengMeng_Axe',
    parent=PREFIX+'Ability/Axe/Abilities/GA_PengMeng_Special05_Combo.GA_PengMeng_Special05_Combo_C')}
OUTPUT = 'runtime/boss-native-combo-candidates'
SOURCES = ('tools/boss_native_combo_candidate.py', 'tools/boss_native_combo_candidate.lua',
           'tests/test_boss_native_combo_candidate.py', 'tests/test_boss_native_combo_candidate.lua',
           'tools/boss_combo_dependencies.py')
read = inventory.read


def candidate_ids(root=ROOT):
    return tuple(REVIEWS)


def select(identifier, report, characters):
    review = REVIEWS[identifier]
    rows = [r for r in report['parents'] if r['id']==identifier and r['parent_class']==review['parent']]
    assert len(rows)==1, 'one explicitly reviewed parent required'
    row, = rows
    assert row['declaration_closure_complete'] and not row['issues'] and not row['context_review'], \
        'complete independently reviewed leaf closure required'
    assert row['subtree_classes']==[review['parent']], 'nested scheduler contexts need separate adaptation'
    assert row['leaf_classes'] and row['trees'] and not row['activation_allowed'] and not row['playable']
    pairs = [p for p in row['exact_parent_variants'] if p['actor']==review['actor'] and p['config']==review['config']]
    assert len(pairs)==1 and pairs[0]['parent_grant_snapshots'], 'exact historical parent variant required'
    character, = [c for c in characters if c['id']==identifier]
    variant, = [v for v in character['variants'] if v['path']==review['actor']]
    fact=variant['observation']
    assert variant['metadata']=='verified' and variant['receipts'] and fact['observed_config']==review['config']
    assert fact['lineage'][0]==review['actor'] and '/Script/ProjectPBZ.PBZCharacter_NPC' in fact['lineage']
    name=fact['display_name'];assert name and name not in ('NA','N/A','None')
    prefix='/'.join(review['actor'].split('/')[:5])+'/'
    assert all(p.startswith(prefix) for p in row['leaf_classes'])
    refs=set()
    for tree in row['trees']:
        assert tree['path'].startswith(prefix) and type(tree['weight']) in (int,float) \
            and math.isfinite(tree['weight']) and tree['weight']>0, 'exact finite positive tree weights required'
        refs.update(tree['references'])
    assert refs==set(row['leaf_classes']), 'direct leaf references must exactly match the closed graph'
    assert len({t['path'] for t in row['trees']})==len(row['trees'])
    return dict(id=identifier,display_name=name,class_path=review['actor'],config_path=review['config'],
        parent_class=review['parent'],ability_pool=[review['parent']],
        contract=dict(**{'class':review['parent']},actor=review['actor'],config=review['config'],
            trees={t['path']:t['weight'] for t in row['trees']},leaves={p:True for p in row['leaf_classes']}),
        parent_grant_snapshots=pairs[0]['parent_grant_snapshots'],
        tree_declarations=[dict(path=t['path'],sha256=t['declaration_sha256']) for t in row['trees']])


def modules(definition,root=ROOT):
    base=root/'releases'/spawn.BASE
    manifest=validate_package(base)
    assert manifest['release_id']==spawn.BASE and manifest['exe_sha256']==BUILD
    source=base/'PBZBossControl/Scripts/combo_scheduler.lua'
    assert sha(source)==manifest['files']['PBZBossControl/Scripts/combo_scheduler.lua']
    scheduler=source.read_text(encoding='utf-8')
    scheduler=replace(scheduler,
        "local contract=id=='attack_01'and {class=Trial.class,trees={[Trial.tree]=true},leaves=Trial.native_leaves}or contracts[id]",
        'local contract=contracts[id]')
    scheduler=replace(scheduler,'    if not contract then return false end\n',
        "    assert(contract and id=='skill_01','only the reviewed developer combo may schedule')\n"
        "    local boss=self.calls:resolve(receipt.boss)\n"
        "    assert(boss:GetClass():GetFullName():match('^[^ ]+ (.+)$')==contract.actor,'combo Actor changed')\n"
        "    local config=boss:GetClass():GetCDO()['Actor Config']\n"
        "    assert(config and config:IsValid() and config:GetFullName():match('^[^ ]+ (.+)$')==contract.config,'combo CDO changed')\n")
    scheduler=replace(scheduler,"    assert(parent.active==0,'parent already active')\n",
        "    assert(parent.active==0,'parent already active')\n"
        "    for leaf in pairs(contract.leaves)do\n"
        "        assert(not baseline[leaf] or baseline[leaf].active==0,'combo child already active')\n"
        "    end\n")
    scheduler=replace(scheduler,'if key~=ticket.parent_class then ticket.child_active=true end',
        'if key~=ticket.parent_class then ticket.child_active=true;ticket.child_observed=true end')
    scheduler=replace(scheduler,
        'if parent_active>0 or #changed>0 or not receipt.combo_trial.observed[receipt.combo_trial.parent_class]then return false end',
        'if parent_active>0 or #changed>0 or not receipt.combo_trial.observed[receipt.combo_trial.parent_class]or not receipt.combo_trial.child_observed then return false end')
    arena=spawn.payload(root).decode('utf-8')
    arena=replace(arena,'local native_combo_enabled=experiment_combo_scheduler_trial or(',
        'local native_combo_enabled=(experiment_boss_candidate and profile.developer_native_combo==true)or experiment_combo_scheduler_trial or(')
    return {'boss_candidate.lua':('local definition='+lua(definition)+'\n').encode('utf-8')
                +(root/'tools/boss_native_combo_candidate.lua').read_bytes(),
            'combo_scheduler.lua':scheduler.encode('utf-8'),
            'subtree_contracts.lua':('return '+lua({'skill_01':definition['contract']})+'\n').encode('utf-8'),
            'owned_arena.lua':arena.encode('utf-8')}


def expected(identifier,root=ROOT):
    report_path,report=dependencies.build(root)
    snapshot,*_=inventory.inputs(root)
    definition=select(identifier,report,snapshot['characters'])
    definition['dependency_report_sha256']=sha(report_path)
    files=modules(definition,root)
    sources=dict(report['sources'])
    sources.update({p:sha(root/p) for p in (*SOURCES,*spawn.SOURCES)})
    record=dict(schema=1,kind='isolated_native_combo_candidate',build=BUILD,definition=definition,
        dependency_report=report_path.relative_to(root).as_posix(),dependency_report_sha256=sha(report_path),
        source_files=sources,overrides={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()},
        module_sha256=hashlib.sha256(files['boss_candidate.lua']).hexdigest(),
        developer_only=True,playable=False,installed=False,game_started=False,
        execution_order='native_engine_only',runtime_acceptance_current=False)
    key=hashlib.sha256(canonical(record)).hexdigest()[:20]
    return record,files,identifier+'-'+key


def build(identifier,root=ROOT):
    record,files,name=expected(identifier,root)
    target=root/OUTPUT/name
    target.mkdir(parents=True,exist_ok=True)
    for filename,raw in {**files,'manifest.json':(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf-8')}.items():
        path=target/filename
        if path.exists(): assert path.read_bytes()==raw, 'preserve frozen combo candidate'
        else:path.write_bytes(raw)
    return target


def validate(identifier,target,base=None,root=ROOT):
    target=unlinked_path(target)
    assert target.parent==(root/OUTPUT).resolve(), 'exact internal combo candidate location required'
    record,files,name=expected(identifier,root)
    assert target.name==name and read(unlinked_path(target/'manifest.json'))==record, 'combo evidence or source drift'
    assert {p.name for p in target.iterdir()}==set(files)|{'manifest.json'}
    assert all(unlinked_path(target/n).read_bytes()==raw for n,raw in files.items())
    base=base or active_mod_root(root)
    frozen=root/'releases'/spawn.BASE
    release=validate_package(frozen)
    prefix='PBZBossControl/'
    expected_base={n.removeprefix(prefix):v for n,v in release['files'].items()
                   if n.startswith(prefix+'Scripts/') and n.endswith('.lua')}
    assert expected_base=={p.relative_to(base).as_posix():sha(p) for p in (base/'Scripts').rglob('*.lua')}, \
        'accepted base changed; preserve installed files'
    return dict(boss_candidate=identifier,developer_combo_only=True,
        developer_combo_evidence_sha256=record['dependency_report_sha256'],
        developer_bundle_sha256=sha(target/'manifest.json'),developer_max_displacement_cm=3000)


def overrides(target,root=ROOT):
    record=read(target/'manifest.json');validate(record['definition']['id'],target,root=root)
    return {name:unlinked_path(target/name).read_bytes() for name in record['overrides']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifier',choices=tuple(REVIEWS));args=parser.parse_args()
    target=build(args.identifier)
    print(json.dumps(dict(candidate=str(target),grant=validate(args.identifier,target),game_started=False,playable=False),ensure_ascii=False,indent=2))
