"""Freeze metadata follow-ups from exact closed native grant observations.

No game access, player registration, manual grants, activation or deployment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from boss_metadata_jobs import render, canonical

REVIEWS = {
    '071_xianzhe': ('20261117-190547', '071_XianZhe', (
        'GA_XianZhe_Skill_01_C', 'GA_XianZhe_CA_C')),
    '067_motian': ('20261117-194042', '067_MoTian', (
        'GA_MoTian_Dodge_F_02_C', 'GA_MoTian_Dodge_R_02_C')),
}
SOURCES = ('tools/boss_native_grant_followup.py', 'tools/boss_metadata_jobs.py',
           'tools/native_grant_metadata_workflow.py', 'tools/collect_boss_metadata_jobs.py',
           'tests/test_boss_native_grant_followup.py', 'tests/test_native_grant_metadata_workflow.py')


def observations(raw, identifier, folder):
    marker = 'PBZ_CONTROL_LIFECYCLE:CANDIDATE_IDENTITY_READY=' + identifier + '|'
    assert raw.count(marker) == 1, 'one exact native candidate identity required'
    tail = raw.split(marker, 1)[1]
    identity, tail = tail.split('\n', 1)
    base = '/PBZCombatAsset/ActorData/Mobs/' + folder + '/'
    actor, config = identity.strip().split('|')
    assert actor.startswith(base) and config.startswith(base), 'foreign character/config rejected'
    assert actor.endswith('_C') and re.fullmatch(r'/[A-Za-z0-9_/]+\.[A-Za-z0-9_]+', config)
    # A later assembly must never contribute grants to the earlier character.
    tail = re.split(r'PBZ_CONTROL_LIFECYCLE:(?:SPAWN_ATTEMPT|CANDIDATE_LIVE_BINDING|'
                    r'INTERACTIVE_READY|ISSUE_READY|CANDIDATE_IDENTITY_READY)=', tail, maxsplit=1)[0]
    grants = re.findall(r'PBZ_CONTROL_LIFECYCLE:GRANTED_ABILITY=[^ \r\n]+ (/[^\r\n]+)', tail)
    assert 1 <= len(grants) <= 512 and len(grants) == len(set(grants)), 'bounded unique native grants required'
    assert all(re.fullmatch(r'/[A-Za-z0-9_/]+\.[A-Za-z0-9_]+', p) for p in grants)
    return actor, config, grants


def expected(root=ROOT):
    jobs, evidence, roles = [], {}, []
    for identifier, (session, folder, shorts) in REVIEWS.items():
        state_path = root / 'runtime' / ('official-validation-' + session) / 'state.json'
        work = root / 'evidence/official-validation' / session
        post_path, raw_path = work / 'postcheck.json', work / 'UE4SS.log'
        state, post = (json.loads(p.read_bytes()) for p in (state_path, post_path))
        assert state['restored'] is True and Path(state['work']).resolve() == work.resolve()
        assert post['validation_state'] == str(state_path)
        assert all(post[k] is True for k in ('research_box_empty', 'research_loader_removed', 'host_registry_unchanged'))
        assert not post['formal_files_changed'] and not post['host_config_files_changed']
        actor, config, grants = observations(raw_path.read_text(encoding='utf-8', errors='strict'), identifier, folder)
        roles.append(dict(id=identifier, session=session, class_path=actor, config_path=config,
                          observed_native_grants=grants, playable=False, attack_adaptation_complete=False))
        for short in shorts:
            matches = [p for p in grants if p.rsplit('.', 1)[-1] == short]
            assert len(matches) == 1 and matches[0].startswith('/PBZCombatAsset/ActorData/Mobs/' + folder + '/Ability/')
            path, = matches
            job = dict(id=identifier, role='ability', lookup_path=path, package=path.split('.', 1)[0],
                       source_session=session, historical_grant_only=True,
                       current_leaf_verified=False, activation_allowed=False, config_candidates=[])
            job['key'] = hashlib.sha256(canonical(job)).hexdigest()[:20]
            jobs.append(job)
        evidence.update({p.relative_to(root).as_posix(): sha(p) for p in (state_path, post_path, raw_path)})
    identity = dict(schema=1, target_build_sha256=BUILD, jobs=jobs, roles=roles, evidence=evidence,
                    sources={n: sha(root / n) for n in SOURCES}, metadata_only=True,
                    playable=False, deployed=False, installed=False, ability_activation_allowed=False)
    fingerprint = hashlib.sha256(canonical(identity)).hexdigest()[:20]
    script = render(jobs, fingerprint).encode('utf-8')
    record = dict(identity, fingerprint=fingerprint, script_sha256=hashlib.sha256(script).hexdigest(),
                  scope='Historical native grants require current CDO kind and live grant checks; no gameplay promotion.')
    return record, script


def build(root=ROOT):
    record, script = expected(root)
    target = root / 'research/boss-adaptation/native-grant-followups' / record['fingerprint']
    if not target.exists():
        target.mkdir(parents=True)
        write_json(target / 'manifest.json', record)
        (target / 'metadata-probe.lua').write_bytes(script)
    assert json.loads((target / 'manifest.json').read_bytes()) == record
    assert (target / 'metadata-probe.lua').read_bytes() == script
    return target


def verify(target, root=ROOT):
    """Replay exact historical grants; a manifest flag alone is never authority."""
    target, root = Path(target).resolve(), Path(root).resolve()
    record, script = expected(root)
    canonical_path = root / 'research/boss-adaptation/native-grant-followups' / record['fingerprint']
    assert target == canonical_path, 'canonical native grant follow-up directory required'
    assert {p.name for p in target.iterdir()} == {'manifest.json', 'metadata-probe.lua'}
    assert json.loads((target / 'manifest.json').read_bytes()) == record, 'native grant source drift'
    assert (target / 'metadata-probe.lua').read_bytes() == script, 'native grant script drift'
    return record


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(dict(bundle=str(build()), game_started=False, playable_bosses_added=0), ensure_ascii=False))
