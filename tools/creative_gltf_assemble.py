"""Assemble actual skin parts on their shared skeleton, preserving skin weights."""
import copy
import hashlib
import json
from pathlib import Path
import struct

from creative_gltf_prepare import read_glb, summary


def accessor_values(value, binary, index):
    accessor = value['accessors'][index]
    assert 'sparse' not in accessor
    sizes = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
    formats = {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}
    fmt = '<' + formats[accessor['componentType']] * sizes[accessor['type']]
    view = value['bufferViews'][accessor['bufferView']]
    offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    stride = view.get('byteStride', struct.calcsize(fmt))
    assert offset + (accessor['count'] - 1) * stride + struct.calcsize(fmt) <= len(binary)
    return [struct.unpack_from(fmt, binary, offset + i * stride) for i in range(accessor['count'])]


def write_glb(path, value, binary):
    value['buffers'][0]['byteLength'] = len(binary)
    raw = json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()
    raw += b' ' * ((-len(raw)) % 4)
    binary += b'\0' * ((-len(binary)) % 4)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('xb') as stream:
        stream.write(struct.pack('<4sII', b'glTF', 2, 28 + len(raw) + len(binary)))
        stream.write(struct.pack('<II', len(raw), 0x4E4F534A)); stream.write(raw)
        stream.write(struct.pack('<II', len(binary), 0x004E4942)); stream.write(binary)


def assemble(body, parts, destination):
    body, destination = Path(body), Path(destination)
    assert not destination.exists() and body not in [Path(p) for p in parts]
    value, binary = read_glb(body)
    assert not value.get('animations') and len(value['skins']) == len(value['meshes']) == 1
    skin = value['skins'][0]
    names = [value['nodes'][i]['name'] for i in skin['joints']]
    lookup = {name: i for i, name in enumerate(names)}
    body_bind = accessor_values(value, binary, skin['inverseBindMatrices'])
    expected_vertices = summary(value, binary)['vertices']
    provenance = [dict(source=str(body), sha256=hashlib.sha256(body.read_bytes()).hexdigest())]
    for part in map(Path, parts):
        item, source_binary = read_glb(part)
        assert not item.get('animations') and len(item['skins']) == len(item['meshes']) == 1
        assert all(not any(k in n for k in ('translation', 'rotation', 'scale', 'matrix'))
                   for n in item['nodes'] if 'mesh' in n), 'transformed skin part needs explicit conversion'
        joints = item['skins'][0]['joints']
        mapping = [lookup[item['nodes'][i]['name']] for i in joints]
        matrices = accessor_values(item, source_binary, item['skins'][0]['inverseBindMatrices'])
        assert len(matrices) == len(mapping)
        max_bind_difference = max(abs(a - b) for index, matrix in enumerate(matrices)
                                  for a, b in zip(matrix, body_bind[mapping[index]]))
        assert max_bind_difference < 0.002, 'different bind poses cannot share one skin'
        expected_vertices += summary(item, source_binary)['vertices']
        data = bytearray(source_binary)
        for primitive in item['meshes'][0]['primitives']:
            assert not primitive.get('targets'), 'morph target assembly requires explicit matching'
            for name, index in primitive['attributes'].items():
                if not name.startswith('JOINTS_'):
                    continue
                accessor = item['accessors'][index]
                rows = accessor_values(item, source_binary, index)
                assert accessor['type'] == 'VEC4' and not accessor.get('normalized')
                remapped = [tuple(mapping[j] for j in row) for row in rows]
                while len(data) % 4:
                    data.append(0)
                offset = len(data)
                for row in remapped:
                    data.extend(struct.pack('<4H', *row))
                item['bufferViews'].append(dict(buffer=0, byteOffset=offset, byteLength=len(rows) * 8, target=34962))
                accessor.update(bufferView=len(item['bufferViews']) - 1, byteOffset=0, componentType=5123)
                for key in ('min', 'max'):
                    accessor.pop(key, None)
        while len(binary) % 4:
            binary += b'\0'
        byte_offset = len(binary)
        offsets = {name: len(value.get(name, [])) for name in
                   ('bufferViews', 'accessors', 'images', 'samplers', 'textures', 'materials')}
        for view in item['bufferViews']:
            view['byteOffset'] = view.get('byteOffset', 0) + byte_offset
        for accessor in item['accessors']:
            assert 'sparse' not in accessor
            accessor['bufferView'] += offsets['bufferViews']
        for image in item.get('images', []):
            assert 'uri' not in image
            image['bufferView'] += offsets['bufferViews']
        for texture in item.get('textures', []):
            assert not texture.get('extensions'), 'compressed texture extensions require explicit remapping'
            if 'source' in texture:
                texture['source'] += offsets['images']
            if 'sampler' in texture:
                texture['sampler'] += offsets['samplers']
        def material_indices(node):
            if isinstance(node, dict):
                for key, child in node.items():
                    if key == 'index':
                        node[key] += offsets['textures']
                    else:
                        material_indices(child)
            elif isinstance(node, list):
                for child in node:
                    material_indices(child)
        for material in item.get('materials', []):
            material_indices(material)
        for primitive in item['meshes'][0]['primitives']:
            primitive['attributes'] = {name: index + offsets['accessors'] for name, index in primitive['attributes'].items()}
            if 'indices' in primitive:
                primitive['indices'] += offsets['accessors']
            if 'material' in primitive:
                primitive['material'] += offsets['materials']
            value['meshes'][0]['primitives'].append(primitive)
        for name in offsets:
            value.setdefault(name, []).extend(item.get(name, []))
        for name in ('extensionsUsed', 'extensionsRequired'):
            if name in item:
                value[name] = sorted(set(value.get(name, [])) | set(item[name]))
        binary += data
        provenance.append(dict(source=str(part), sha256=hashlib.sha256(part.read_bytes()).hexdigest(),
                               max_bind_matrix_difference=max_bind_difference))
    result = summary(value, binary)
    assert result['vertices'] == expected_vertices and result['skins'] == 1
    write_glb(destination, value, binary)
    reopened, data = read_glb(destination)
    assert summary(reopened, data) == result
    return dict(file=str(destination), content=result, parts=provenance,
                sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                rest_pose_and_geometry_verified=True, animated_preview_verified=False)
