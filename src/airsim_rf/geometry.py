"""Versioned, offline geometry handoff; no AirSim, Sionna or GPU imports.

Source adapters supply local triangles and local-to-NED metre transforms.
The export adapter bakes these into the project's RF (x, -y, -z) frame.
This is an interchange boundary, not a live simulator synchronization API.
"""
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np


def geometry_digest(document):
    """Content identity, including materials and transforms, independent of key order."""
    return sha256(json.dumps(document, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def file_digest(path):
    digest = sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _fields(value, names, where):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError(f'{where} requires exactly: {names}')


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', value):
        raise ValueError(f'Invalid geometry identifier: {value!r}')


def validate_geometry(document):
    """Validate schema v1 strictly, including finite, nondegenerate triangles.

    Return a detached JSON-compatible snapshot. Unknown schema versions or
    fields fail explicitly so adapter upgrades cannot silently change meaning.
    """
    _fields(document, 'schema_version scene_id revision source materials objects', 'scene')
    if type(document['schema_version']) is not int or document['schema_version'] != 1:
        raise ValueError('Only geometry schema_version 1 is supported')
    _identifier(document['scene_id'])
    if not isinstance(document['revision'], str) or not document['revision'].strip():
        raise ValueError('scene revision must be a nonempty string')
    _fields(document['source'], 'adapter version asset revision geometry_kind', 'source')
    if any(not isinstance(v, str) or not v.strip() for v in document['source'].values()):
        raise ValueError('Source provenance fields must be nonempty strings')
    if document['source']['geometry_kind'] not in ('collision', 'render', 'shared'):
        raise ValueError('geometry_kind must be collision, render or shared')
    materials = document['materials']
    if not isinstance(materials, dict) or not materials:
        raise ValueError('At least one explicit RF material is required')
    for name, material in materials.items():
        _identifier(name)
        _fields(material, 'relative_permittivity conductivity_s_m assumption', f'material {name}')
        for key, minimum in (('relative_permittivity', 1), ('conductivity_s_m', 0)):
            value = material[key]
            if type(value) not in (int, float) or not np.isfinite(value) or value < minimum:
                raise ValueError(f'{name}.{key} must be finite and >= {minimum}')
        if not isinstance(material['assumption'], str) or not material['assumption'].strip():
            raise ValueError(f'{name} must document its material assumption')
    if not isinstance(document['objects'], list) or not document['objects']:
        raise ValueError('At least one geometry object is required')
    identifiers = set()
    for obj in document['objects']:
        _fields(obj, 'id material vertices_local faces local_to_ned_m', 'object')
        _identifier(obj['id'])
        if obj['id'] in identifiers:
            raise ValueError(f'Duplicate object ID: {obj["id"]}')
        identifiers.add(obj['id'])
        if not isinstance(obj['material'], str) or obj['material'] not in materials:
            raise ValueError(f'{obj["id"]}: unknown RF material')
        vertices = np.asarray(obj['vertices_local'], dtype=float)
        faces = np.asarray(obj['faces'])
        transform = np.asarray(obj['local_to_ned_m'], dtype=float)
        if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 3 or not np.isfinite(vertices).all():
            raise ValueError(f'{obj["id"]}: finite Nx3 vertices required')
        if (faces.ndim != 2 or faces.shape[1] != 3 or not len(faces)
                or faces.dtype.kind not in 'iu' or np.any(faces < 0) or np.any(faces >= len(vertices))):
            raise ValueError(f'{obj["id"]}: valid integer triangle indices required')
        if (transform.shape != (4, 4) or not np.isfinite(transform).all()
                or not np.array_equal(transform[3], [0, 0, 0, 1])
                or np.linalg.det(transform[:3, :3]) == 0):
            raise ValueError(f'{obj["id"]}: nonsingular affine 4x4 transform required')
        transformed = vertices @ transform[:3, :3].T + transform[:3, 3]
        triangles = transformed[faces]
        area = np.linalg.norm(np.cross(triangles[:, 1]-triangles[:, 0],
                                       triangles[:, 2]-triangles[:, 0]), axis=1)
        if not np.isfinite(transformed).all() or not np.isfinite(area).all() or np.any(area == 0):
            raise ValueError(f'{obj["id"]}: degenerate or nonfinite transformed geometry')
    return json.loads(json.dumps(document, allow_nan=False))


def rf_mesh(obj):
    """Convert a validated object's local geometry to RF metres.

    Affine matrices multiply column vectors. Reverse winding for reflections
    so negative object scale or a source handedness change preserves normals.
    """
    transform = np.asarray(obj['local_to_ned_m'], float)
    vertices = (np.asarray(obj['vertices_local']) @ transform[:3, :3].T
                + transform[:3, 3]) * [1, -1, -1]
    faces = np.array(obj['faces'], dtype=int, copy=True)
    if np.linalg.det(transform[:3, :3]) < 0:
        faces = faces[:, [0, 2, 1]]
    return vertices, faces


def export_sionna_geometry(document, output, *, provenance=None, bindings=None):
    """Write a new, offline PLY/XML bundle for the current Sionna adapter.

    The caller must use a fresh directory. The manifest is written last;
    its presence identifies a completed export, not runtime qualification.
    Content hashes include transforms/materials, supporting cache invalidation.
    """
    document = validate_geometry(document)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    canonical = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False)
    (output/'geometry.json').write_text(canonical+'\n')
    if provenance is not None:
        (output/'source.json').write_text(json.dumps(provenance, indent=2, allow_nan=False)+'\n')
    if bindings is not None:
        (output/'bindings.json').write_text(json.dumps(bindings, indent=2, allow_nan=False)+'\n')
    scene = ET.Element('scene', version='2.1.0')
    for name, material in document['materials'].items():
        node = ET.SubElement(scene, 'bsdf', type='radio-material', id='mat_'+name)
        for key, source in (('relative_permittivity', 'relative_permittivity'),
                            ('conductivity', 'conductivity_s_m')):
            ET.SubElement(node, 'float', name=key, value=str(material[source]))
    for obj in document['objects']:
        vertices, faces = rf_mesh(obj)
        filename = obj['id']+'.ply'
        with (output/filename).open('w') as stream:
            stream.write('ply\nformat ascii 1.0\n')
            stream.write(f'element vertex {len(vertices)}\nproperty double x\nproperty double y\nproperty double z\n')
            stream.write(f'element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n')
            np.savetxt(stream, vertices, fmt='%.17g')
            np.savetxt(stream, np.column_stack((np.full(len(faces), 3), faces)), fmt='%d')
        node = ET.SubElement(scene, 'shape', type='ply', id='obj_'+obj['id'])
        ET.SubElement(node, 'string', name='filename', value=filename)
        ET.SubElement(node, 'ref', name='bsdf', id='mat_'+obj['material'])
    ET.ElementTree(scene).write(output/'scene.xml', encoding='utf-8', xml_declaration=True)
    manifest = {'schema_version': 1, 'adapter': 'sionna-ply-xml-v1',
                'qualification': 'offline export only; runtime loading not checked',
                'scene_sha256': sha256(canonical.encode()).hexdigest(),
                'object_map': {obj['id']: 'obj_'+obj['id'] for obj in document['objects']},
                'load_options': {'merge_shapes': False},
                'files': {p.name: file_digest(p)
                          for p in sorted(output.iterdir())}}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def read_bundle(directory):
    """Check a completed local export before any runtime connects or loads it.

    Hashes detect changes, not the trustworthiness of the producing machine.
    Source layers need not remain installed once an export has been prepared.
    """
    root = Path(directory).resolve()
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest.get('schema_version') != 1 or manifest.get('adapter') != 'sionna-ply-xml-v1':
        raise ValueError('Unsupported geometry bundle manifest')
    files = manifest.get('files', {})
    if not isinstance(files, dict) or not {'scene.xml', 'geometry.json'} <= files.keys():
        raise ValueError('Incomplete geometry bundle')
    for name, expected in files.items():
        path = root/name
        if Path(name).name != name or path.is_symlink() or not path.is_file():
            raise ValueError(f'Invalid or missing bundle member: {name}')
        if file_digest(path) != expected:
            raise ValueError(f'Geometry bundle content changed: {name}')
    document = validate_geometry(json.loads((root/'geometry.json').read_text()))
    if geometry_digest(document) != manifest.get('scene_sha256'):
        raise ValueError('Geometry snapshot identity does not match manifest')
    # Prevent XML references from escaping the checked asset set.
    tree = ET.parse(root/'scene.xml')
    for node in tree.iter('string'):
        if node.get('name') == 'filename' and node.get('value') not in files:
            raise ValueError('Scene references an unchecked mesh')
    bindings = json.loads((root/'bindings.json').read_text()) if 'bindings.json' in files else None
    return document, manifest, bindings


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('geometry', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New export directory')
    args = parser.parse_args()
    export_sionna_geometry(json.loads(args.geometry.read_text()), args.output)


if __name__ == '__main__':
    main()
