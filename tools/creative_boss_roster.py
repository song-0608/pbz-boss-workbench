"""Plan UE authoring imports from exact archived Boss body references."""
import argparse
from contextlib import closing
from functools import lru_cache
import json
from pathlib import Path
import re

from boss_catalog_database import PROJECT_STORAGE, DATABASE, connect_readonly
from boss_disk_declarations import write_new
from boss_disk_dependencies import native_package
from boss_mechanism_database import read_declaration
from build_boss_disk_combo_index import split_reference, Unresolved


PUBLISHED = ('boss-model-expansion-published-20261123.json', 'boss-model-expansion-published-20261124.json')
ORIGINAL_ROLES = {
    'AHua': '042_AHua', 'WanJun': '057_WanJun', 'YouLong': '056_YouLong',
    'YanQianSui': '073_YanQianSui', 'XianZhe': '071_XianZhe', 'MadDocter': '058_MadDoctor',
}


def plan(db, evidence):
    published = {}
    for name in PUBLISHED:
        receipt = json.loads((evidence / name).read_bytes())
        if receipt['completed'] is not True or receipt['verified_blueprint_mesh_binding'] is not True:
            raise ValueError(f'UE authoring model receipt not verified: {name}')
        for row in receipt['roles']:
            published[row['actor']] = row
    originals = json.loads((evidence / 'boss-library-native-result-v2.json').read_bytes())['roles']
    roles = [dict(id=row['role'], label=row['display_name'], folder=ORIGINAL_ROLES[row['role']],
                  mesh=row['mesh'], source='character_lab') for row in originals]
    packages = {native_package(p).casefold(): p for p, in db.execute('''
        SELECT package FROM boss_mechanism_declarations WHERE package LIKE '%.uasset' ''')}
    folders = {folder for folder, in db.execute('''SELECT folder FROM folders
        WHERE folder<>'native_support' AND skill_count>0''')}
    unsupported = []
    load = lru_cache(maxsize=24)(lambda package: read_declaration(db, package))

    def character_mesh(ancestry):
        for cls in ancestry:
            mount, _, name = cls.rpartition('.')
            package = packages[mount.casefold()]
            exports = load(package)
            owners = [i for i, obj in enumerate(exports) if obj['Name'] == 'Default__' + name and obj['Type'] == name]
            if len(owners) != 1:
                continue
            cdo = exports[owners[0]]
            ref = cdo.get('Properties', {}).get('Mesh')
            if not ref:
                continue
            remote, ordinal, kind, subobject = split_reference(ref)
            if remote.casefold() != mount.casefold() or not 0 <= ordinal < len(exports):
                raise ValueError('Mesh component belongs to an unexpected package')
            component = exports[ordinal]
            if (component['Name'], component['Type']) != (subobject.rsplit(':', 1)[-1], kind):
                raise ValueError('Mesh component identity differs')
            if 'SkeletalMesh' not in component.get('Properties', {}):
                continue
            target = component['Properties']['SkeletalMesh']
            if target is None:
                raise ValueError('CharacterMesh0 explicitly clears its skeletal mesh')
            mesh_mount, index, kind, name = split_reference(target)
            source = packages[mesh_mount.casefold()]
            asset = load(source)[index]
            if kind != 'SkeletalMesh' or (asset['Type'], asset['Name']) != (kind, name):
                raise ValueError('Skeletal mesh target identity differs')
            return source, cls
        raise ValueError('No exact skeletal mesh override in archived CharacterMesh0 ancestry')

    for folder, actor, ancestry in db.execute('''SELECT folder,class_path,class_ancestry
        FROM boss_native_actors ORDER BY folder,class_path'''):
        if actor in published:
            row = published.pop(actor)
            roles.append(dict(id=row['role'], label=row['role'], folder=folder, actor=actor, mesh=row['body']['object'],
                              source='published_model'))
        elif folder in folders:
            try:
                source, owner = character_mesh(json.loads(ancestry))
            except (KeyError, IndexError, Unresolved, ValueError) as error:
                unsupported.append(dict(folder=folder, actor=actor, reason=str(error)))
                continue
            label = actor.rsplit('.', 1)[-1].removeprefix('BP_Monster_').removesuffix('_C')
            roles.append(dict(id=label, label=label, folder=folder, actor=actor, body_package=source,
                              mesh_owner=owner, source='native_skeletal_mesh'))
    for actor, row in published.items():
        roles.append(dict(id=row['role'], label=row['role'], folder=row['folder'], actor=actor,
                          mesh=row['body']['object'], source='published_model'))
    for ordinal, row in enumerate(roles):
        row['id'] = f"{ordinal:03d}_{re.sub(r'[^A-Za-z0-9_]', '_', row['id'])}"
    covered = {row['folder'] for row in roles}
    return dict(roles=roles, unsupported_actor_classes=unsupported, target_folders=sorted(folders),
                folders_without_selectable_body=sorted(folders - covered),
                export_packages=sorted({r['body_package'] for r in roles if 'body_package' in r}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with closing(connect_readonly(PROJECT_STORAGE / DATABASE)) as db:
        evidence = next(PROJECT_STORAGE.glob('*/**/' + PUBLISHED[0])).parent
        result = plan(db, evidence)
    write_new(args.output, result)
    print(json.dumps({key: len(value) for key, value in result.items()}, ensure_ascii=False))
