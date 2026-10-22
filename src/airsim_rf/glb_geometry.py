"""Blocks client-mesh adapter v1: shared actor-local NED triangles to GLB 2.0.

The pinned Assimp/Unreal loader converts metres to centimetres, makes glTF
left handed and rotates +90 degrees about X. Its inverse is (x, -z, y).
This adapter has no visual-to-RF material inference and no runtime dependency.
"""
import json
import struct

import numpy as np


def triangle_glb(vertices_actor_m, faces, *, base_color_rgba=None, emissive_rgb=None):
    """Encode one triangle mesh, with explicit normals, in a self-contained GLB."""
    vertices = np.asarray(vertices_actor_m, float)
    faces = np.asarray(faces)
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all()
            or faces.ndim != 2 or faces.shape[1] != 3 or faces.dtype.kind not in 'iu'
            or not len(faces) or np.any(faces < 0) or np.any(faces >= len(vertices))):
        raise ValueError('Finite vertices and valid triangle indices required')
    # Duplicate corners for flat normals. The mapping is a proper rotation;
    # reflected object transforms must have their winding corrected by caller.
    points = vertices[faces.reshape(-1)][:, [0, 2, 1]] * [1, -1, 1]
    points = points.astype('<f4')
    triangles = points.reshape(-1, 3, 3)
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    if not np.isfinite(points).all() or not np.isfinite(lengths).all() or np.any(lengths == 0):
        raise ValueError('Triangles must remain finite and nondegenerate at GLB float32 precision')
    normals = np.repeat(normals/lengths[:, None], 3, axis=0).astype('<f4')
    indices = np.arange(len(points), dtype='<u4')
    axis=np.zeros_like(normals);axis[:,0]=1
    axis[abs(normals[:,0])>.9]=[0,1,0]
    tangent=axis-(axis*normals).sum(axis=1)[:,None]*normals
    tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    tangent=np.column_stack((tangent,np.ones(len(points)))).astype('<f4')
    axes=np.argsort(np.ptp(points,axis=0))[-2:]
    uv=points[:,axes].copy()
    uv=(uv-uv.min(axis=0))/np.maximum(np.ptp(uv,axis=0),1e-6)
    uv=uv.astype('<f4')
    chunks = [points.tobytes(), normals.tobytes(), indices.tobytes(),uv.tobytes(),tangent.tobytes()]
    views, offset = [], 0
    for chunk, target in zip(chunks, [34962, 34962, 34963,34962,34962]):
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(chunk), 'target': target})
        offset += len(chunk)
    doc = {'asset': {'version': '2.0', 'generator': 'airsim-rf-blocks-glb-v1'},
           'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
           'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0':3,'TANGENT':4},
                                      'indices': 2, 'material': 0, 'mode': 4}]}],
           'materials': [{'doubleSided': True, 'pbrMetallicRoughness': {
               'baseColorFactor': [.7, .7, .7, 1], 'metallicFactor': 0, 'roughnessFactor': 1}}],
           'buffers': [{'byteLength': offset}], 'bufferViews': views,
           'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': len(points), 'type': 'VEC3',
                          'min': points.min(axis=0).tolist(), 'max': points.max(axis=0).tolist()},
                         {'bufferView': 1, 'componentType': 5126, 'count': len(points), 'type': 'VEC3'},
                         {'bufferView': 2, 'componentType': 5125, 'count': len(points), 'type': 'SCALAR'},
                         {'bufferView':3,'componentType':5126,'count':len(points),'type':'VEC2'},
                         {'bufferView':4,'componentType':5126,'count':len(points),'type':'VEC4'}]}
    material=doc['materials'][0]
    if base_color_rgba is not None:
        color=np.asarray(base_color_rgba,float)
        if color.shape!=(4,) or not np.isfinite(color).all() or np.any(color<0) or np.any(color>1):
            raise ValueError('Visual base color must be four finite values in [0,1]')
        material['pbrMetallicRoughness']['baseColorFactor']=color.tolist()
    if emissive_rgb is not None:
        color=np.asarray(emissive_rgb,float)
        if color.shape!=(3,) or not np.isfinite(color).all() or np.any(color<0) or np.any(color>1):
            raise ValueError('Visual emission must be three finite values in [0,1]')
        material['emissiveFactor']=color.tolist()
    metadata = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
    metadata += b' ' * (-len(metadata) % 4)
    binary = b''.join(chunks)
    return (struct.pack('<III', 0x46546c67, 2, 12+8+len(metadata)+8+len(binary))
            + struct.pack('<II', len(metadata), 0x4e4f534a) + metadata
            + struct.pack('<II', len(binary), 0x004e4942) + binary)
