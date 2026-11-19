"""Read bounded defense/cue reflection declarations in the existing research lease.

Never calls gameplay functions, grants abilities, changes tags or sends input.
"""
import json
import hashlib
from pathlib import Path
import time

import ahua_practice as practice
from inspect_pbz_ai_metadata import fields, functions
from pbz_readonly import GameRead
from boss_defense_cue_audit import native_contract_ready
import official_validation as validation

PREFIXES = ('/Script/PBZDeflectSystem.',)
EXACT = {'/Script/ProjectPBZ.PBZCharacter_NPC', '/Script/ProjectPBZ.PBZCharacter',
         '/Script/GameplayAbilities.AbilitySystemComponent', '/Script/GameplayAbilities.GameplayAbility',
         '/Script/LegoAbility.LGAAction', '/Script/LegoAbility.LGAAction_Executable',
         '/Script/Engine.ActorComponent', '/Script/Engine.ParticleSystemComponent',
         '/Script/Niagara.NiagaraComponent'}
BLUEPRINTS = {'BP_StanceAction_Base_C', 'BP_StanceAction_Base_NPC_C',
              'BP_StanceAction_Base_Player_C', 'GAAction_WeaponParticle_BlueRedEye_C'}


def collect():
    owner, state = practice.owned_session()
    assert owner['phase'] == 'game_launched', 'Unassembled research game required'
    target = Path(state['work'])/'defense-cue-native-contract.json'
    assert not target.exists(), 'One read-only contract pass per research session'
    classes, errors = [], 0
    started = time.monotonic()
    with GameRead() as game:
        for index in range(game.count):
            if time.monotonic()-started > 75:
                raise RuntimeError('Bounded reflection pass timed out; do not treat as complete')
            try:
                obj = game.object(index)
                if not obj:
                    continue
                header = game.header(obj)
                kind = game.header(header['class'])['name']
                if kind not in ('Class', 'BlueprintGeneratedClass', 'LegoAbilityBlueprintGeneratedClass'):
                    continue
                path = game.path(obj)
                if not (path.startswith(PREFIXES) or path in EXACT or
                        header['name'] in BLUEPRINTS and path.startswith(('/PBZDeflectSystem/', '/PBZCombatAsset/'))):
                    continue
                assert len(classes) < 96, 'Bounded combat reflection class count exceeded'
                classes.append(dict(path=path, super=game.path(game.u64(obj+0x40)),
                    properties=fields(game, obj, 256), functions=functions(game, obj)))
            except (OSError, ValueError, UnicodeError):
                errors += 1
        report = dict(schema=1, at=validation.utc8(), state_file=state['state_file'], pid=game.pid,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            classes=classes, invalid_or_unreadable_candidates=errors,
            reflection_ready=native_contract_ready(classes),
            gameplay_called=False, input_sent=False, grants_changed=False, tags_changed=False,
            declaration_only=True, runtime_behavior_verified=False)
    validation.save(target, report)
    print(json.dumps(dict(report=str(target), classes=[c['path'] for c in classes],
        reflection_ready=report['reflection_ready'], gameplay_called=False,
        runtime_behavior_verified=False), ensure_ascii=False))


if __name__ == '__main__':
    collect()
