"""Reuse closed natural actions only when every deployed Lua module is identical."""
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, BUILD, sha
from candidate_effect_scope import local_effect
from collect_skill_acceptance import analyze


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify_actions(report, raw, actions, state_file):
    verified = {}
    for action in actions:
        if action.get('interrupt') or not action.get('passed'):
            continue
        assert action['state_file'] == state_file
        start, end = action['log_offset'], action['log_end']
        assert 0 <= start < end <= len(raw)
        interval = raw[start:end]
        assert action['lines'] == interval.splitlines(), 'Previous action raw interval changed'
        skill = action['skill']
        assert skill in report['skills'] and skill not in verified
        proof = local_effect(analyze(interval, skill), interval)
        path = report['skills'][skill]['class_path']
        assert proof['activation_instance_verified'] and proof['natural_completion'] and proof['restoration']['passed']
        assert proof['ability_class_short'] == path.rsplit('.', 1)[-1], 'Previous action class differs'
        assert proof['natural_completion']['damage_observed'] or proof['natural_completion']['movement_observed']
        verified[skill] = dict(proof, skill=skill, interrupt=False, exact_granted_class=path,
            class_matches_live_binding=True, log_offset=start, log_end=end)
    assert verified, 'No independently verified natural actions to reuse'
    return verified


def previous_natural(session, identifier, modules, root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    work = root / 'evidence/official-validation' / session
    report_path = work / 'boss-candidate-acceptance.json'
    report = read(report_path)
    assert report['session'] == session and report['id'] == identifier
    assert report['target_build_sha256'] == BUILD and report['playable'] is False
    assert report['module_source_sha256'] == modules, 'Changed runtime modules require new natural tests'
    for name, expected in report['sources'].items():
        path = (root / name).resolve()
        assert path.is_relative_to(root.resolve()) and sha(path) == expected, 'Previous natural source changed: ' + name
    state_path = root / 'runtime' / ('official-validation-' + session) / 'state.json'
    state = read(state_path)
    post = read(work / 'postcheck.json')
    assert state['restored'] and Path(state['work']).resolve() == work.resolve()
    assert post['validation_state'] == str(state_path)
    assert post['research_box_empty'] and post['research_loader_removed'] and post['host_registry_unchanged']
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    raw = (work / 'UE4SS.log').read_text(encoding='utf-8', errors='replace')
    verified = verify_actions(report, raw, read(work / 'player-extra-skill-actions.json'), str(state_path))
    return verified, {report_path.relative_to(root).as_posix(): sha(report_path)}
