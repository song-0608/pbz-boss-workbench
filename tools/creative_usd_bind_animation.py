"""Compose a decoded USD animation with its actual exported binding mesh."""
import hashlib
import json
from pathlib import Path
import re


def compose(mesh, animation, destination):
    mesh, animation, destination = map(Path, (mesh, animation, destination))
    assert mesh.is_file() and animation.is_file() and not destination.exists()
    mesh_text, animation_text = mesh.read_text(encoding='utf-8'), animation.read_text(encoding='utf-8')
    mesh_root, = re.findall(r'^def SkelRoot "([A-Za-z_0-9]+)"', mesh_text, re.M)
    anim_root, = re.findall(r'^def SkelRoot "([A-Za-z_0-9]+)"', animation_text, re.M)
    clip, = re.findall(r'^    def SkelAnimation "([A-Za-z_0-9]+)"', animation_text, re.M)
    mesh_joints = re.search(r'\buniform token\[\] joints = (\[[^\n]+\])', mesh_text)
    anim_joints = re.search(r'\buniform token\[\] joints = (\[[^\n]+\])', animation_text)
    assert mesh_joints and anim_joints
    m, a = map(lambda v: json.loads(v.group(1)), (mesh_joints, anim_joints))
    assert set(m) <= set(a), 'binding mesh contains joints absent from this animation'
    timing = {}
    for name in ('timeCodesPerSecond', 'startTimeCode', 'endTimeCode'):
        value, = re.findall(r'^    ' + name + r' = ([0-9.eE+-]+)$', animation_text, re.M)
        timing[name] = float(value)
    assert timing['timeCodesPerSecond'] > 0 and timing['endTimeCode'] > timing['startTimeCode']
    paths = [p.resolve().as_posix() for p in (mesh, animation)]
    assert all('@' not in p and '\n' not in p for p in paths)
    source = f'''#usda 1.0
(
    defaultPrim = "{mesh_root}"
    metersPerUnit = 0.01
    upAxis = "Z"
    timeCodesPerSecond = {timing['timeCodesPerSecond']}
    startTimeCode = {timing['startTimeCode']}
    endTimeCode = {timing['endTimeCode']}
    subLayers = [@{paths[0]}@]
)

over "{mesh_root}" (
    prepend apiSchemas = ["SkelBindingAPI"]
)
{{
    rel skel:animationSource = </{mesh_root}/{clip}>
    def SkelAnimation "{clip}" (
        prepend references = @{paths[1]}@</{anim_root}/{clip}>
    )
    {{
    }}
}}
'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(source)
    return dict(mesh=str(mesh), animation=str(animation), composed=str(destination),
                mesh_sha256=hashlib.sha256(mesh.read_bytes()).hexdigest(),
                animation_sha256=hashlib.sha256(animation.read_bytes()).hexdigest(),
                skeleton_joint_count=len(m), animation_joint_count=len(a), timing=timing)
