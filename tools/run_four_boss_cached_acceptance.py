"""Reuse pure candidate calculations within one verification, retaining every gate."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time

from mod_installation import ROOT

BUILDERS = tuple('build_yanqiansui_' + name + '_candidate' for name in
                 ('search', 'terrain', 'dense', 'centered', 'slope'))


def snapshot(root):
    """Hash all calculation inputs, including path membership; never hash live logs."""
    paths = []
    for folder in ('tools', 'tests', 'runtime/release-candidates'):
        paths.extend(p for p in (root / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


@contextmanager
def calculation_cache(root=ROOT):
    before = snapshot(root)
    originals = [importlib.import_module(name).expected for name in BUILDERS]
    replacements = {}
    for original in originals:
        cache = {}

        def make_cached(function, values):
            @wraps(function)
            def cached(*args, **kwargs):
                key = (args, tuple(sorted(kwargs.items())))
                if key not in values:
                    values[key] = function(*args, **kwargs)
                # Callers cannot mutate a later verification's expected manifest.
                return deepcopy(values[key])
            return cached

        replacements[original] = make_cached(original, cache)
    changed = []
    for module in list(sys.modules.values()):
        if module is None:
            continue
        for name, value in list(vars(module).items()):
            if callable(value) and any(value is f for f in originals):
                changed.append((module, name, value))
                setattr(module, name, replacements[value])
    try:
        yield
        assert snapshot(root) == before, 'Verification inputs changed; discard calculated values'
    finally:
        for module, name, original in changed:
            setattr(module, name, original)


def main(action, workflow):
    # Frozen subprocess runners decode UTF-8 explicitly; make their writers agree.
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    import yanqiansui_slope_acceptance as slope
    import test_four_boss_integration as frozen
    from four_boss_integration_workflow import verify as verify_workflow, modules
    from build_yanqiansui_slope_candidate import expected, verify

    def checked(function, *args):
        start = time.monotonic()
        with calculation_cache():
            result = function(*args)
        print(json.dumps({'verification': function.__name__,
                          'seconds': round(time.monotonic() - start, 3),
                          'all_input_hashes_unchanged': True}), flush=True)
        return result

    checked(verify_workflow, workflow)
    if action == 'verify':
        def verify_all():
            candidate = ROOT / 'runtime/release-candidates' / expected()[-1]
            actions, _ = slope.verify_current(modules(verify(candidate)))
            return {'passed': True, 'ordinary_actions': len(actions), 'input_sent': False}
        print(json.dumps(checked(verify_all)))
        return 0
    frozen.verify_current = lambda current: checked(slope.verify_current, current)
    return frozen.main(workflow, '073_yanqiansui', finish_world=action == 'finish-world')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('verify', 'run', 'finish-world'))
    parser.add_argument('--workflow', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.action, args.workflow.resolve()))
