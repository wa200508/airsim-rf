"""Shared dashboard geometry, independent visibility and scene integrity gates."""
import re
import numpy as np

from .geometry import rf_mesh
from .geometry_sync import nearest_intersections


def isolate_blocks_scene(world):
    """Remove the pinned map's physical scenery from this dedicated sim world.

    Keep lighting, sky, weather, the drone and engine infrastructure. The RF
    scene uses the generated DEM, rather than the packaged Blocks buildings.
    """
    pattern=re.compile(r'^(?:Ground|TemplateCube.*|Cylinder.*|Cone.*|OrangeBall)$')
    removed=[]
    for name in world.list_objects('.*'):
        if pattern.fullmatch(name):
            if not world.destroy_object(name):raise RuntimeError('Could not remove unmodeled Blocks geometry: '+name)
            removed.append(name)
    remaining=[name for name in world.list_objects('.*') if pattern.fullmatch(name)]
    if remaining:raise RuntimeError('Unmodeled Blocks geometry remains: '+str(remaining))
    return {'removed_native_objects':removed,'scope':'Pinned Blocks physical scenery removed; shared DEM is the environment'}


def require_rf_mesh_match(scene,document,tolerance_m=.001):
    expected={'obj_'+obj['id']:obj for obj in document['objects']}
    shapes={shape.id():shape for shape in scene.mi_scene.shapes()}
    if shapes.keys()!=expected.keys():raise RuntimeError('Sionna object inventory differs from the shared geometry')
    errors={}
    for name,obj in expected.items():
        vertices,faces=rf_mesh(obj);shape=shapes[name]
        actual=shape.vertex_positions_buffer().numpy().reshape(-1,3)
        indices=shape.faces_buffer().numpy().reshape(-1,3)
        if actual.shape!=vertices.shape or not np.array_equal(indices,faces):
            raise RuntimeError('Sionna mesh topology differs: '+name)
        errors[name]=float(np.max(np.linalg.norm(actual-vertices,axis=1)))
        if errors[name]>tolerance_m:raise RuntimeError('Sionna mesh positions differ: '+name)
    return {'maximum_vertex_error_m':errors,'tolerance_m':tolerance_m}


def link_geometry(document,arrays,position_rf,path_diagnostics,*,transmitter_id='tx0'):
    """Compare each element's actual Sionna LoS with an independent mesh ray."""
    channels=[];origins=[]
    for site in arrays['sites']:
        for name,offset in zip(site['channels'],site['element_offsets_m']):
            channels.append(name);origins.append(np.asarray(site['center_rf_m'])+offset*np.array([-np.sin(site['yaw_rad']) if 'yaw_rad' in site else 0.,np.cos(site.get('yaw_rad',0.)),0.]))
    origins=np.asarray(origins)*[1,-1,-1];end=np.asarray(position_rf)*[1,-1,-1]
    vectors=end-origins;distances=np.linalg.norm(vectors,axis=1)
    hits=nearest_intersections(document,origins,vectors,maximum_distance_m=float(distances.max()))
    details={}
    for name,hit,distance in zip(channels,hits,distances):
        blocked=hit is not None and hit['distance_m']<distance-.001
        paths=path_diagnostics[name][transmitter_id]
        if not paths.get('range_gated',False) and paths.get('illuminated',True) and bool(paths['direct_paths'])==blocked:
            raise RuntimeError('Sionna direct path disagrees with shared terrain visibility: '+name)
        details[name]={**paths,'direct_visible':not blocked,
            'blocker_rf_m':(np.asarray(hit['position_ned_m'])*[1,-1,-1]).tolist() if blocked else None}
    sites=[]
    for site in arrays['sites']:
        values=[details[name] for name in site['channels']]
        sites.append({'id':site['id'],'center_rf_m':site['center_rf_m'],
            'direct_elements':sum(v['direct_visible'] for v in values),
            'elements':len(values),'reflected_paths_per_element':[v['reflected_paths'] for v in values],
            'blocker_rf_m':next((v['blocker_rf_m'] for v in values if v['blocker_rf_m'] is not None),None)})
    return {'direct_visible':[s['direct_elements']>0 for s in sites],
            'site_paths':sites,'channel_paths':details}
