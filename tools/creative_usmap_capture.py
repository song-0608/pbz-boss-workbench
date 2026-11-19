"""Capture exact native asset mappings through the existing isolated lease.

Preparation and current Steam cloud screenshot review remain separate. The
verified carrier's only substitution is its read-only Lua payload. No frozen
source is edited, no keys are sent, and no gameplay or Blueprint types dumped.
"""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import struct
import time

import ahua_practice as practice
import official_validation as validation
import pbz_ue4ss_baseline as baseline
from mod_installation import unlinked_path
from research_storage import container_path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / 'tools/creative_usmap_probe.lua'
OLD = "(v.ROOT/'adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua').read_bytes()"
NEW = "(v.ROOT/'tools/creative_usmap_probe.lua').read_bytes()"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def launch():
    owner, state = practice.owned_session()
    assert owner['phase'] == 'prepared' and owner.get('observed_ui_preparation')
    work = Path(state['work'])
    assert (work / 'observed-ui-properties.json').is_file()
    assert not state.get('ue4ss_deployed') and time.time() < state['deadline_unix'] - 180
    assert not (work / 'creative-usmap-deployment.json').exists(), 'never replay an attempt'
    # Retain the independently observed cloud gate required by the frozen launcher.
    observation = practice.read(work / 'observed-ui-properties.json')
    assert observation['cloud_off_reviewed'] is True
    screenshot = ROOT / 'runtime/steam-menu-private.png'
    assert sha(screenshot) == observation['observation']['screenshot_sha256']
    shutil.copy2(screenshot, work / 'cloud-off-reviewed.png')
    validation.save(work / 'cloud-gate.json', dict(at=validation.utc8(), ui_off_verified=True,
                    screenshot='cloud-off-reviewed.png', observed_ui_receipt='observed-ui-properties.json'))
    source = inspect.getsource(baseline.deploy_and_launch)
    assert source.count(OLD) == 1, 'carrier changed; review before adapting'
    rendered = source.replace(OLD, NEW)
    scope = dict(vars(baseline))
    exec(compile(rendered, __file__ + ':readonly_payload_variant', 'exec'), scope)
    validation.c.isolation.select_box('PBZSteamLab')
    dll = validation.c.isolation.api()
    target = unlinked_path(validation.c.isolation.virtual_file(validation.c.isolation.get_root(dll),
                           validation.c.baseline.GAME / 'platform/steam'))
    assert target.is_relative_to(unlinked_path(container_path()))
    previous = {str(p): sha(p) for p in target.rglob('*.usmap')}
    validation.save(work / 'creative-usmap-deployment.json', dict(schema=1, state_file=state['state_file'],
                    created_at=validation.utc8(), probe_sha256=sha(PROBE),
                    baseline_source_sha256=sha(baseline.__file__),
                    rendered_launcher_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
                    previous_usmaps=previous, physical_target=str(target),
                    native_types_only=True, input_sent=False, gameplay_modified=False))
    scope['deploy_and_launch'](with_signature=True, readonly_ai=True)
    owner.update(phase='game_launched', purpose='one-shot-native-type-mapping')
    practice.save_owner(owner)


def collect(destination):
    owner, state = practice.owned_session()
    assert owner.get('purpose') == 'one-shot-native-type-mapping'
    assert time.time() < state['deadline_unix'] - 60
    validation.verify_build(state['ue4ss_loader_manifest'])
    assert validation.c.baseline.formal_files() == state['formal_before']
    work = Path(state['work'])
    receipt = practice.read(work / 'creative-usmap-deployment.json')
    target = unlinked_path(receipt['physical_target'])
    assert target.is_relative_to(unlinked_path(container_path()))
    log = practice.log_path(state).read_text(encoding='utf-8', errors='replace')
    assert log.count('PBZ_CREATIVE_USMAP:ATTEMPT=1') == 1, 'one native attempt required'
    assert 'PBZ_CREATIVE_USMAP:FAILED=' not in log
    assert 'PBZ_CREATIVE_USMAP:RETURNED=true' in log
    assert 'Mappings Generation Completed Successfully!' in log
    assert '[USMAP] Lossy output:' not in log, 'lossy mappings cannot be accepted'
    candidates = [p for p in target.rglob('*.usmap') if str(p) not in receipt['previous_usmaps']]
    assert len(candidates) == 1, 'one new native output required'
    source, = candidates
    source = unlinked_path(source)
    assert source.is_relative_to(target)
    raw = source.read_bytes()
    assert len(raw) > 16 and struct.unpack_from('<H', raw)[0] == 0x30C4
    assert raw[2] <= 4 and struct.unpack_from('<i', raw, 3)[0] == 0 and raw[7] == 0
    compressed, uncompressed = struct.unpack_from('<II', raw, 8)
    assert compressed == uncompressed == len(raw) - 16 and uncompressed > 1000
    destination = unlinked_path(destination)
    assert destination.is_relative_to(Path(r'E:\项目\PBZ-Boss操控研究\创作协作'))
    destination.mkdir(parents=True, exist_ok=False)
    copied = destination / source.name
    with copied.open('xb') as stream:
        stream.write(raw)
    assert sha(copied) == sha(source)
    result = dict(schema=1, state_file=state['state_file'], source_file=str(source), mapping_file=str(copied),
                  sha256=sha(copied), bytes=len(raw), usmap_version=raw[2],
                  probe_sha256=receipt['probe_sha256'], exact_native_build=True,
                  mapping_usable_by_converter=False, model_exported=False, imported_to_editor=False)
    validation.save(destination / 'mapping-capture.json', result)
    validation.save(work / 'creative-usmap-captured.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('launch', 'collect'))
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    result = launch() if args.action == 'launch' else collect(args.destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))
