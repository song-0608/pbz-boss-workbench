"""Resolve only explicitly migrated research containers; game installations stay separate."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECT_STORAGE=Path(r'E:\项目\PBZ-Boss操控研究')
BOXES={'PBZBossLab','PBZSteamLab'}


def container_path(box='PBZSteamLab',root=ROOT):
    if box not in BOXES:raise ValueError('Unknown research container')
    pointer=Path(root)/'runtime/research-storage.json'
    if not pointer.exists():return Path(root)/'sandbox'/box
    data=json.loads(pointer.read_text(encoding='utf-8'))
    if data.get('schema')!=1 or data.get('project_storage')!=str(PROJECT_STORAGE):
        raise ValueError('Unexpected research storage mapping')
    containers=data.get('containers')
    if not isinstance(containers,dict) or set(containers)-BOXES:
        raise ValueError('Unexpected container mapping')
    if box not in containers:return Path(root)/'sandbox'/box
    expected=PROJECT_STORAGE/'研究运行环境'/box
    if containers[box]!=str(expected):raise ValueError('Container mapping escaped its project directory')
    return expected
