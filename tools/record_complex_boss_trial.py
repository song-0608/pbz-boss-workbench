"""Record exact native grants, completed attacks and restoration from a closed trial."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from boss_adaptation_workflow import ROOT, sha
from boss_catalog_database import DATABASE, Catalog, check_identity, encode
from boss_offline_inventory import closed, read
from boss_skill_session import complete_assembly
from collect_boss_candidate_acceptance import candidate_interval
from collect_skill_acceptance import analyze
from control_action_evidence import control_identity, restoration_result
from mod_installation import unlinked_path
from prepare_boss_variant_candidates import captured_grants
from prepare_complex_boss_candidates import verify
from research_storage import PROJECT_STORAGE


def replay(session, root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}', session)
    work = unlinked_path(root / 'evidence/official-validation' / session)
    state = unlinked_path(root / ('runtime/official-validation-' + session) / 'state.json')
    post = unlinked_path(work / 'postcheck.json')
    assert closed(state, post, work), 'clean closed research session required'
    prefix = work / 'inventory-skill-ui-stage'
    staged_path = unlinked_path(prefix.with_name(prefix.name + '-staged.json'))
    capture_path = unlinked_path(prefix.with_name(prefix.name + '-capture.json'))
    staged, capture = read(staged_path), read(capture_path)
    assert staged['staged'] and staged['state_file'] == capture['state_file'] == str(state)
    workflow_path = unlinked_path(Path(staged['workflow']) / 'manifest.json')
    assert sha(workflow_path) == staged['workflow_manifest_sha256'] == capture['workflow_manifest_sha256']
    deployment_path = unlinked_path(work / Path(staged['deployment_archive']).name)
    assert sha(deployment_path) == staged['deployment_sha256']
    deployment = read(deployment_path)
    bundle = unlinked_path(Path(staged['bundle']))
    record = verify(bundle, root)
    definition = record['definition']
    identifier = definition['id']
    assert staged['id'] == capture['id'] == deployment['boss_candidate'] == identifier
    assert deployment['developer_bundle'] == str(bundle) and deployment['player_entry'] is False
    assert deployment['module_source_sha256']['boss_candidate.lua'] == record['module_sha256']
    assert deployment['grant']['developer_bundle_sha256'] == sha(bundle / 'manifest.json')
    raw_path = unlinked_path(work / 'UE4SS.log')
    raw = raw_path.read_bytes()
    offset = staged['log_byte_offset']
    assert type(offset) is int and 0 <= offset <= len(raw)
    assert hashlib.sha256(raw[:offset]).hexdigest() == staged['log_prefix_sha256']
    tail = raw[offset:].decode('utf-8')
    assert tail.splitlines()[:len(capture['lines'])] == capture['lines']
    begin, _ = candidate_interval(tail, identifier)
    assembly = tail[begin:]
    expected = [(row['skill'], row['class_path']) for row in record['bindings']]
    matches = re.findall(r'CANDIDATE_LIVE_BINDING=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)', assembly)
    assert matches == [(identifier, skill, path) for skill, path in expected]
    assert expected == [(row['skill'], row['class_path']) for row in capture['bindings']]
    grants = captured_grants(tail, definition, capture['bindings'])
    assert grants['native_grant_counts'] == capture['native_grant_counts']
    assert not grants['missing_native_grants'] and not grants['duplicate_native_candidates']
    assert complete_assembly(assembly), 'owned cleanup and original player restoration required'

    keys = {row['skill']: (row['key'], row['class_path']) for row in record['bindings']}
    actions = []
    takeovers = assembly.split('[PBZBossControl] enter success=true state=ACTIVE')
    for cycle in takeovers[1:]:
        cycle = '[PBZBossControl] enter success=true state=ACTIVE' + cycle
        identity = control_identity(cycle)
        assert identity and identity['participants']['boss']['class'].split(' ', 1)[-1] == definition['class_path']
        assert restoration_result(cycle, 'exit')['passed']
        casts = list(re.finditer(r'KEY_SKILL_BEGIN=([^|\r\n]+)\|', cycle))
        for i, event in enumerate(casts):
            skill = event[1]
            key, path = keys[skill]
            end = casts[i + 1].start() if i + 1 < len(casts) else len(cycle)
            result = analyze(cycle[event.start():end], skill)
            assert result['ability_class_short'] == path.rsplit('.', 1)[-1]
            if result['natural_completion']:
                actions.append(dict(key=key, class_path=path, **result['natural_completion']))

    sources = (state, post, raw_path, staged_path, capture_path, deployment_path, workflow_path, bundle / 'manifest.json')
    return dict(id=identifier, session=session, class_path=definition['class_path'],
        native_grants_verified=True, total_native_classes=len(grants['native_grant_counts']),
        natural_completions=actions, takeovers=len(takeovers) - 1, owned_cleanup_verified=True,
        native_grant_counts=grants['native_grant_counts'], playable=False,
        sources={path.relative_to(root).as_posix(): sha(path) for path in sources})


def index(report, root=ROOT, storage=PROJECT_STORAGE):
    catalog = Catalog(root, storage)
    database = unlinked_path(Path(storage) / DATABASE)
    with closing(sqlite3.connect(database.as_uri() + '?mode=rw', uri=True)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        check_identity(db, catalog)
        rows = db.execute('SELECT folder, payload FROM complex_boss_profiles WHERE class_path=?',
                          (report['class_path'],)).fetchall()
        assert len(rows) == 1
        (folder, raw), = rows
        entry = json.loads(raw)
        assert entry['id'] == report['id'] and entry['metadata_verified'] is True
        assert all(report['native_grant_counts'].get(slot['class_path']) == 1 for slot in entry['bindings'])
        entry.update(trial=report, native_grants_verified=True)
        db.execute('UPDATE complex_boss_profiles SET payload=? WHERE folder=?', (encode(entry), folder))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    parser.add_argument('--index', action='store_true')
    args = parser.parse_args()
    result = replay(args.session)
    if args.index:
        index(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
