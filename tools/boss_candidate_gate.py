"""Closed metadata proofs allow one protected developer assembly, never player promotion."""
import json
from pathlib import Path
from boss_adaptation_workflow import ROOT, BUILD, OUT, sha

ALLOWED = {'057_wanjun'}


def validate(identifier, root=ROOT, bundle=None):
    if bundle is not None:
        from build_boss_developer_bundle import validate as validate_bundle
        return validate_bundle(identifier, bundle, root=root)
    if identifier not in ALLOWED:
        raise RuntimeError('Candidate is not registered for protected developer assembly')
    dossier = json.loads((root/'research/boss-adaptation/dossiers'/(identifier+'.json')).read_text(encoding='utf-8'))
    metadata = dossier.get('metadata_identity', {})
    receipt_path = (root/metadata.get('receipt', 'missing')).resolve()
    receipt_path.relative_to((root/'research/boss-adaptation/identity-receipts').resolve())
    if not metadata.get('identity_verified') or sha(receipt_path) != metadata.get('receipt_sha256'):
        raise RuntimeError('Independent closed-session Boss identity receipt required')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt['target_build_sha256'] != BUILD or receipt.get('playable') is not False:
        raise RuntimeError('Candidate metadata build/scope mismatch')
    for relative, expected in receipt['sources'].items():
        source = (root/relative).resolve();source.relative_to(root.resolve())
        if sha(source) != expected:
            raise RuntimeError('Candidate identity source changed: '+relative)
    rows = [r for r in receipt['candidates'] if r['id'] == identifier and r['identity_verified'] is True]
    if len(rows) != 1 or any(rows[0].get(k) != metadata.get(k) for k in ('class_path', 'config_path', 'display_name')):
        raise RuntimeError('Candidate identity receipt does not match dossier')
    return {'boss_candidate': identifier, 'identity_receipt_sha256': sha(receipt_path)}
