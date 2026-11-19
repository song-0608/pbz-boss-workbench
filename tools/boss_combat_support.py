"""Extract indexed defense/input/cue support declarations without launching PBZ.

This complements the Mobs-only inventory. Selection is a research clue, never
an ability grant or permission to call an unverified native function.
"""
import argparse
import csv
from pathlib import Path, PurePosixPath
import re

import boss_disk_declarations as disk

COMBAT = 'ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/'
INPUT = 'ProjectPBZ/Plugins/Secret/PBZInput/Content/'
DEFLECT = 'ProjectPBZ/Plugins/Secret/PBZDeflectSystem/Content/'
TOKENS = ('deflect', 'defence', 'defense', 'blueredeye', 'powerattackparticle')
ROLE_FOLDERS = {'038_AquaKiller', '042_AHua', '056_YouLong', '057_WanJun',
                '058_MadDoctor', '071_XianZhe', '073_YanQianSui'}
SHARED = {'ProjectPBZ/Content/RenewalContent/Prototypes/Character/BP_RenewalNPC.uasset',
          COMBAT+'Prototypes/Config/PBZ_MainWeaponConfig.uasset',
          COMBAT+'Prototypes/Config/PDA_ActorConfig.uasset'}


def selected_packages(index):
    found = {}
    with Path(index).open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream, skipinitialspace=True):
            raw = row.get('Filename', '').strip()
            if not raw.startswith('../../../'):
                continue
            name = raw[len('../../../'):]
            if ('\\' in name or ':' in name or '..' in PurePosixPath(name).parts
                    or not name.endswith('.uasset')
                    or row.get('ChunkType', '').strip() != 'ExportBundleData'):
                continue
            leaf = PurePosixPath(name).stem.casefold()
            match = name in SHARED or name.startswith(DEFLECT) or (name.startswith(INPUT) and leaf in {
                'imc_default', 'imc_deflect', 'ia_faceup_hold',
                'ia_attackl_hold', 'ia_attackh_hold'})
            if name.startswith(COMBAT):
                relative = name[len(COMBAT):]
                relevant = any(t in leaf for t in TOKENS) or bool(re.search(r'(?:^|_)stance(?:_|$)', leaf))
                parts = relative.split('/')
                weapon = (len(parts) >= 5 and parts[:2] == ['ActorData', 'Mobs']
                          and parts[2] in ROLE_FOLDERS and leaf.startswith('weapon_'))
                match = match or weapon or (relative.startswith('Prototypes/') and relevant) or (
                    relative.startswith('ActorData/Players/Hun/Abilities/')
                    and relevant and leaf.startswith(('ga_', 'bp_')))
            if not match:
                continue
            item = dict(package=name, folder='combat_support', package_hash=row.get('Hash', '').strip())
            if name in found and found[name] != item:
                raise ValueError('Conflicting indexed combat support package')
            found[name] = item
    return sorted(found.values(), key=lambda item: item['package'])


def plan(index, mapping, target):
    rows = selected_packages(index)
    if not rows or len(rows) > 256:
        raise ValueError('Expected 1–256 indexed combat support candidates')
    mapping, target = Path(mapping).resolve(), Path(target).resolve()
    if not mapping.is_file():
        raise ValueError('Exact existing local mapping required')
    target.mkdir(parents=True, exist_ok=False)
    batches = []
    for offset in range(0, len(rows), 64):
        ordinal = offset // 64
        job = f'job-{ordinal:04d}.json'
        packages = [r['package'] for r in rows[offset:offset+64]]
        disk.write_new(target/job, dict(mode='declarations', game='GAME_UE5_7',
                       usmap=str(mapping), packages=packages))
        batches.append(dict(job=job, sha256=disk.digest(target/job), packages=packages,
                            output=f'batch-{ordinal:04d}'))
    record = dict(schema=1, kind='offline_boss_disk_declarations',
        purpose='defense_input_and_attack_cues', index_sha256=disk.digest(index),
        mapping_sha256=disk.digest(mapping), selector_sha256=disk.digest(__file__),
        packages=rows, batches=batches, disk_metadata_only=True,
        complete_package_inventory=False, live_grant_verified=False,
        execution_verified=False, playable=False, game_started=False, installed=False)
    disk.write_new(target/'plan.json', record)
    disk.checked_plan(target)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('index', 'mapping', 'target'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    result = plan(args.index, args.mapping, args.target)
    print(f"Prepared {len(result['packages'])} support declarations; game_started=false")
