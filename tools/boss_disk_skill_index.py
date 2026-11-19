"""Index serialized GA timelines without executing or inventing runtime behavior."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

import boss_disk_declarations as disk

MOUNT = 'ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/'
OBJECT_NAME = re.compile(r"([^']+)'([^']+)'")


def package_name(path):
    if not path.startswith(MOUNT) or not path.endswith('.uasset'):
        raise ValueError('Expected the exact PBZ combat mount')
    return '/PBZCombatAsset/'+path[len(MOUNT):-len('.uasset')]


def resolve_local(reference, package, exports):
    """Numeric export indices are accepted only with matching native name/type."""
    if not isinstance(reference,dict):
        return None
    name = OBJECT_NAME.fullmatch(reference.get('ObjectName',''))
    path = reference.get('ObjectPath','')
    if not name or '.' not in path:
        return None
    referenced_package,ordinal=path.rsplit('.',1)
    if referenced_package.casefold()!=package.casefold():
        return None
    if not ordinal.isdigit() or int(ordinal) >= len(exports):
        return None
    item = exports[int(ordinal)]
    short = name[2].rsplit('.',1)[-1].rsplit(':',1)[-1]
    if item.get('Type') != name[1] or item.get('Name') != short:
        return None
    return item


def references(value, pointer=''):
    if isinstance(value,dict):
        if isinstance(value.get('ObjectPath'),str) and isinstance(value.get('ObjectName'),str):
            yield dict(pointer=pointer,**{key:value[key] for key in ('ObjectName','ObjectPath')})
        for key,child in value.items():
            escaped=str(key).replace('~','~0').replace('/','~1')
            yield from references(child,pointer+'/'+escaped)
    elif isinstance(value,list):
        for index,child in enumerate(value):
            yield from references(child,pointer+'/'+str(index))


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


def abilities(exports, package):
    result=[]
    for index, obj in enumerate(exports):
        if not ('BlueprintGeneratedClass' in obj.get('Type','')
                and re.fullmatch(r'GA_[A-Za-z0-9_]+_C',obj.get('Name',''))):
            continue
        issues=[]
        native_package=obj.get('Package')
        package_matches=isinstance(native_package,str) and native_package.casefold()==package.casefold()
        if not package_matches:
            issues.append('serialized class package does not match the exact index path')
        cdo=resolve_local(obj.get('ClassDefaultObject'),package,exports)
        if cdo is None or cdo.get('Name') != 'Default__'+obj['Name']:
            issues.append('matching local class default object is unresolved')
            cdo=None
        timeline_refs=obj.get('Properties',{}).get('AbilityTimelines',[])
        if not isinstance(timeline_refs,list):
            issues.append('unsupported serialized timeline collection')
            timeline_refs=[]
        timelines=[]
        for reference in timeline_refs:
            timeline=resolve_local(reference,package,exports)
            if timeline is None or timeline.get('Type')!='LGATimeline':
                issues.append('local timeline reference is unresolved')
                continue
            actions=[]
            declarations=timeline.get('Properties',{}).get('Actions',[])
            if not isinstance(declarations,list):
                issues.append('unsupported timeline action collection')
                continue
            for ordinal,item in enumerate(declarations):
                if not isinstance(item,dict):
                    issues.append('unsupported timeline action declaration')
                    continue
                action=resolve_local(item.get('Action'),package,exports)
                start,duration=item.get('StartTime'),item.get('duration')
                # Native timelines can contain authored pre-roll (including
                # tiny negative floating-point values). Preserve it exactly.
                valid_time=number(start) and number(duration) and duration>=0
                if not valid_time:
                    issues.append(f'{timeline["Name"]}/{ordinal}: explicit finite timing unavailable')
                if action is None:
                    issues.append(f'{timeline["Name"]}/{ordinal}: local action reference is unresolved')
                actions.append(dict(ordinal=ordinal, start_seconds=start,duration_seconds=duration,
                    has_pre_roll=number(start) and start<0,
                    timing_fields_valid=valid_time, track=item.get('TrackIndex'),
                    action_reference=item.get('Action'), action_resolved=action is not None,
                    action_type=action.get('Type') if action else None,
                    action_name=action.get('Name') if action else None,
                    serialized_action_properties=action.get('Properties',{}) if action else None,
                    sections=item.get('Sections'),
                    trigger_time_offset=item.get('TriggerTimeOffset'),
                    end_trigger_time_offset=item.get('EndTriggerTimeOffset')))
            timelines.append(dict(name=timeline['Name'],actions=actions,
                declared_end_seconds=max((a['start_seconds']+a['duration_seconds'] for a in actions),default=None)
                    if all(a['timing_fields_valid'] for a in actions) else None))
        result.append(dict(class_path=native_package+'.'+obj['Name'] if package_matches else None,
            serialized_package=native_package,export_index=index,
            serialized_super=obj.get('Super'),
            serialized_class_properties=obj.get('Properties',{}),
            serialized_cdo_properties=cdo.get('Properties',{}) if cdo else None,
            timelines=timelines,issues=issues, serialized_overrides_only=True,
            declared_end_is_runtime_completion=False, live_grant_verified=False,
            execution_verified=False, playable=False))
    return result


def build(target):
    target=Path(target).resolve()
    inventory=disk.summarize(target)
    rows=[]
    for item in inventory['packages']:
        if not item['passed']:
            continue
        path=target/item['declaration']
        if disk.digest(path)!=item['declaration_sha256']:
            raise ValueError('Declaration changed while indexing')
        exports=json.loads(path.read_bytes())
        package=package_name(item['package'])
        skills=abilities(exports,package)
        if not skills:
            continue
        refs=list(references(exports))
        rows.append(dict(package=item['package'],folder=item['folder'],
            declaration=item['declaration'],declaration_sha256=item['declaration_sha256'],
            abilities=skills,serialized_references=refs))
    counts=Counter()
    timeline_count=action_count=issues=0
    for row in rows:
        counts[row['folder']]+=len(row['abilities'])
        for ability in row['abilities']:
            timeline_count+=len(ability['timelines'])
            action_count+=sum(len(t['actions']) for t in ability['timelines'])
            issues+=len(ability['issues'])
    return dict(schema=1,kind='offline_serialized_boss_skill_index',
        plan_sha256=inventory['plan_sha256'],exporter_sha256=inventory['exporter_sha256'],
        sources={name:disk.digest(Path(__file__).parent/name)
                 for name in ('boss_disk_declarations.py','boss_disk_skill_index.py')},
        requested_packages=inventory['requested'],extracted_packages=inventory['extracted'],
        pending_packages=inventory['pending'],failed_packages=inventory['failed'],
        ability_classes=sum(counts.values()),ability_classes_by_folder=dict(sorted(counts.items())),
        timelines=timeline_count,action_declarations=action_count,indexing_issues=issues,
        packages=rows,disk_metadata_only=True,serialized_overrides_only=True,
        complete_package_inventory=False,all_boss_skills_complete=False,
        live_grant_verified=False,execution_verified=False,playable=False,
        game_started=False,installed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=build(args.target)
    disk.write_new(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('packages','sources')},ensure_ascii=False))
