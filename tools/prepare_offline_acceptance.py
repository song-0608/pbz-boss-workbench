"""Prepare one 40-minute offline acceptance session before any game launch.

The immutable player preparation remains at 20 minutes. This developer entry
changes only the preparation duration guard, never an issued state or grant.
"""
import hashlib
import inspect
from pathlib import Path

import ahua_practice as practice
import official_validation as validation

FROZEN = 'a22e33c8d6c396090028c7874e804df2c90e0d98b3cf595d881f08f8e6e142d3'
OLD = 'if lease_minutes not in (12,20) or (lease_minutes==20 and (not offline_validation or client_network)):'
NEW = 'if lease_minutes not in (12,20,40) or (lease_minutes in (20,40) and (not offline_validation or client_network)):'


def render():
    source_path = Path(validation.__file__)
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == FROZEN, 'Preparation source changed'
    source = inspect.getsource(validation.prepare)
    assert source.count(OLD) == 1
    return source.replace(OLD, NEW)


def prepare():
    source = render()
    scope = dict(vars(validation))
    exec(compile(source, __file__ + ':duration_variant', 'exec'), scope)
    variant = scope['prepare']
    original = validation.prepare

    def offline_only(**kwargs):
        assert kwargs['lease_minutes'] == 20
        assert kwargs['offline_validation'] and not kwargs.get('client_network', False)
        return variant(**dict(kwargs, lease_minutes=40))

    validation.prepare = offline_only
    try:
        practice.prepare()
    finally:
        validation.prepare = original
    state = practice.read(validation.state_path())
    validation.save(Path(state['work']) / 'offline-acceptance-preparation.json', {
        'base_source_sha256': FROZEN,
        'variant_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
        'state_file': state['state_file'], 'session_minutes': 40,
        'existing_session_extended': False, 'interactive_seconds': 600,
        'offline_validation': state['offline_validation'],
        'network_active': state['network_active'],
    })


if __name__ == '__main__':
    prepare()
