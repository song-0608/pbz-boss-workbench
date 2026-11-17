"""Join independently closed skill sessions without extending any issued lease."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re

import boss_skill_expansion as expansion
from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
from collect_boss_skill_retry_session import collect
import collect_boss_skill_session as session_collector
from mod_installation import validate_package

EXPECTED = frozenset(('057_wanjun', '073_yanqiansui', '056_youlong'))
BASE = 'ahua-boss-workbench-v3-f7034432a74d819b'


@contextmanager
def archived_base(root=ROOT):
    """Replay issued grants against their immutable base, independent of installation."""
    released=root/'releases'/BASE
    archived=root/'runtime/managed-mod'/BASE
    assert validate_package(archived)==validate_package(released), 'Archived skill base changed'
    base=archived/'PBZBossControl'
    previous_expansion,previous_collector=expansion.active_mod_root,session_collector.active_mod_root
    def resolve(requested=root):
        assert Path(requested).resolve()==root.resolve(), 'Unexpected archive root'
        return base
    expansion.active_mod_root=session_collector.active_mod_root=resolve
    try:
        yield
    finally:
        expansion.active_mod_root,session_collector.active_mod_root=previous_expansion,previous_collector


def combine(receipts):
    """Select complete Boss assemblies; never merge individual actions or retries."""
    assert receipts, 'At least one closed skill session is required'
    bosses = {}
    for receipt in receipts:
        assert receipt['formal_postcheck_passed'] is True
        assert receipt['target_build_sha256'] == BUILD
        assert re.fullmatch(r'\d{8}-\d{6}', receipt['session'])
        for row in receipt['bosses']:
            assert row['id'] in EXPECTED
            if not row['all_four_accepted']:
                continue
            assert row['id'] not in bosses, 'Duplicate accepted Boss assembly'
            assert len(row['accepted_skills']) == 4 and len(row['actions']) == 8
            assert row['owned_cleanup_and_restoration_verified'] is True
            assert row['stability']['passed'] is True and all(row['movement_camera'].values())
            bosses[row['id']] = dict(row, session=receipt['session'],
                evidence='evidence/official-validation/' + receipt['session'] + '/boss-skill-session.json')
    return [bosses[key] for key in sorted(bosses)]


def campaign(sessions, root=ROOT):
    if isinstance(sessions, str):
        sessions = [sessions]
    assert sessions and len(sessions) == len(set(sessions)), 'Unique explicit sessions required'
    receipts = []
    sources = {}
    for session in sorted(sessions):
        with archived_base(root):
            receipt = collect(session, root)
        path = root / 'evidence/official-validation' / session / 'boss-skill-session.json'
        assert expansion.read(path) == receipt, 'Closed session receipt differs from raw replay'
        receipts.append(receipt)
        sources[path.relative_to(root).as_posix()] = sha(path)
        for name, digest in receipt['sources'].items():
            assert name not in sources or sources[name] == digest, 'Conflicting source revisions across sessions'
            sources[name] = digest
    rows = combine(receipts)
    return dict(schema=1, sessions=sorted(sessions), target_build_sha256=BUILD,
        bosses=rows, sources=sources,
        all_twelve_accepted={row['id'] for row in rows} == EXPECTED,
        formal_postcheck_passed=True, playable=False, game_started_by_collector=False)


def report_path(receipt, root=ROOT):
    digest = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode('utf-8')).hexdigest()[:16]
    return root / 'evidence/adaptation' / ('boss-skill-campaign-' + digest + '.json')


def save_campaign(sessions, root=ROOT, verify=False):
    receipt = campaign(sessions, root)
    path = report_path(receipt, root)
    if verify or path.exists():
        assert expansion.read(path) == receipt, 'Campaign receipt changed'
    else:
        write_json(path, receipt)
    return path, receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sessions', nargs='+')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    path, receipt = save_campaign(args.sessions, verify=args.verify)
    print(json.dumps(dict(report=str(path), all_twelve_accepted=receipt['all_twelve_accepted'],
        accepted_bosses=[row['id'] for row in receipt['bosses']], playable=False), ensure_ascii=False))
