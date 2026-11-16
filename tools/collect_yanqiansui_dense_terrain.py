"""Version the frozen refusal collector for the exact dense-search candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[1]
FROZEN = 'ee3d1a0b0d26afceb777569c1f849bf4fa6e80e2d3fd3a8de12525081a6b14f6'
CHANGES = (
    ('from build_yanqiansui_terrain_candidate import expected,verify',
     'from build_yanqiansui_dense_candidate import expected,verify'),
    ("ROOT/'tools/collect_yanqiansui_terrain.py']",
     "ROOT/'tools/collect_yanqiansui_terrain.py',ROOT/'tools/collect_yanqiansui_dense_terrain.py']"),
    ("('yanqiansui-terrain-'+session+'.json')",
     "('yanqiansui-dense-terrain-'+session+'.json')"),
)


def render(root=ROOT):
    path = root / 'tools/collect_yanqiansui_terrain.py'
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FROZEN, 'Historical collector changed'
    source = data.decode('utf-8')
    for before, after in CHANGES:
        assert source.count(before) == 1
        source = source.replace(before, after)
    return source


def collector():
    module = types.ModuleType('versioned_dense_terrain_collector')
    module.__file__ = str(ROOT / 'tools/collect_yanqiansui_terrain.py')
    exec(compile(render(), module.__file__, 'exec'), module.__dict__)
    return module


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('session')
    args = parser.parse_args()
    print(json.dumps(collector().collect(args.session), ensure_ascii=False))
