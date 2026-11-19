"""Validate exported skeletons and make bounded-texture UE authoring copies."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct

from PIL import Image


def read_glb(path):
    raw = Path(path).read_bytes()
    assert len(raw) <= 512 * 1024 * 1024, 'asset exceeds per-file processing budget'
    assert struct.unpack_from('<4sII', raw) == (b'glTF', 2, len(raw))
    offset, chunks = 12, []
    while offset < len(raw):
        length, kind = struct.unpack_from('<II', raw, offset)
        assert length % 4 == 0 and offset + 8 + length <= len(raw)
        chunks.append((kind, raw[offset + 8:offset + 8 + length]))
        offset += 8 + length
    assert len(chunks) == 2 and chunks[0][0] == 0x4E4F534A and chunks[1][0] == 0x004E4942
    value = json.loads(chunks[0][1])
    assert len(value['buffers']) == 1 and 'uri' not in value['buffers'][0]
    return value, chunks[1][1]


def summary(value, binary):
    views = value['bufferViews']
    for view in views:
        assert view.get('buffer', 0) == 0
        assert 0 <= view.get('byteOffset', 0) <= len(binary) - view['byteLength']
    vertices = 0
    for mesh in value.get('meshes', []):
        for primitive in mesh['primitives']:
            attrs = primitive['attributes']
            assert all(k in attrs for k in ('POSITION', 'JOINTS_0', 'WEIGHTS_0'))
            counts = [value['accessors'][attrs[k]]['count'] for k in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')]
            assert counts[0] > 0 and len(set(counts)) == 1
            vertices += counts[0]
    skins = value.get('skins', [])
    assert vertices > 0 and skins and all(skin['joints'] for skin in skins)
    nodes = value['nodes']
    for skin in skins:
        assert all(type(n) is int and 0 <= n < len(nodes) for n in skin['joints'])
        names = [nodes[n]['name'] for n in skin['joints']]
        assert len(names) == len(set(names)), 'ambiguous bone names'
    return dict(meshes=len(value['meshes']), vertices=vertices, skins=len(skins),
                joints=[len(s['joints']) for s in skins], images=len(value.get('images', [])),
                materials=len(value.get('materials', [])))


def prepare(source, destination, edge=2048):
    source, destination = Path(source), Path(destination)
    assert source.is_file() and not destination.exists() and edge in (1024, 2048, 4096)
    value, binary = read_glb(source)
    before = summary(value, binary)
    replacements, images = {}, []
    for image in value.get('images', []):
        assert 'uri' not in image and 'bufferView' in image, 'embedded source images required'
        index = image['bufferView']
        assert index not in replacements, 'shared image buffer view requires review'
        view = value['bufferViews'][index]
        start = view.get('byteOffset', 0)
        with Image.open(io.BytesIO(binary[start:start + view['byteLength']])) as texture:
            original = texture.size
            if max(original) > edge:
                texture.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                texture.save(output, format='PNG', compress_level=3)
                replacements[index] = output.getvalue()
                image['mimeType'] = 'image/png'
            images.append(dict(name=image.get('name'), original_size=original, authoring_size=texture.size))
    pieces, position = [], 0
    for index, view in enumerate(value['bufferViews']):
        start = view.get('byteOffset', 0)
        content = replacements.get(index, binary[start:start + view['byteLength']])
        pad = (-position) % 4
        pieces.append(b'\0' * pad)
        position += pad
        view['byteOffset'], view['byteLength'] = position, len(content)
        pieces.append(content)
        position += len(content)
    output_bin = b''.join(pieces)
    value['buffers'][0]['byteLength'] = len(output_bin)
    assert summary(value, output_bin) == before, 'geometry or skeleton changed'
    output_bin += b'\0' * ((-len(output_bin)) % 4)
    output_json = json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    output_json += b' ' * ((-len(output_json)) % 4)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(output_json) + 8 + len(output_bin)))
        stream.write(struct.pack('<II', len(output_json), 0x4E4F534A))
        stream.write(output_json)
        stream.write(struct.pack('<II', len(output_bin), 0x004E4942))
        stream.write(output_bin)
    # Reopen the generated file; a written extension alone is not validation.
    checked, data = read_glb(destination)
    assert summary(checked, data) == before
    return dict(source=str(source), destination=str(destination), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), content=before, images=images,
                source_bytes=source.stat().st_size, authoring_bytes=destination.stat().st_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--edge', type=int, default=2048)
    args = parser.parse_args()
    assert not args.destination.exists(), 'preserve existing authoring output'
    inputs = sorted(args.source.rglob('*.glb'))
    assert 1 <= len(inputs) <= 64
    args.destination.mkdir(parents=True)
    rows = []
    for source in inputs:
        row = prepare(source, args.destination / source.relative_to(args.source), args.edge)
        rows.append(row)
        print(json.dumps(dict(mesh=source.stem, vertices=row['content']['vertices'],
                              source_bytes=row['source_bytes'], authoring_bytes=row['authoring_bytes'])), flush=True)
    result = dict(schema=1, passed=True, texture_edge=args.edge, files=rows,
                  geometry_and_bone_counts_preserved=True, original_game_shader_reconstructed=False)
    (args.destination / 'authoring-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
