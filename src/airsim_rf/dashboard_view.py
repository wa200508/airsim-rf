"""Actual scene framing and presentation-only radio location markers."""
import numpy as np
from scipy.spatial.transform import Rotation

CHASE_DISTANCE_M=5.
CAMERA_FOV_DEG=90.
TERRAIN_BASE_COLOR_RGBA=[.12,.18,.085,1.]
TERRAIN_EMISSIVE_RGB=[.008,.012,.005]


def camera_frame(position_rf, receiver_positions_rf, *, distance_m=CHASE_DISTANCE_M,elevation_bias=.25):
    """Five-metre chase boom, slightly above the drone, aimed between the radios."""
    flip=np.array([1,-1,-1]);position=np.asarray(position_rf,float)
    center=np.mean(receiver_positions_rf,axis=0)
    outward=position-center;outward/=np.linalg.norm(outward)
    boom=outward+[0,0,elevation_bias];boom*=distance_m/np.linalg.norm(boom)
    eye=(position+boom)*flip
    target=center*flip
    forward=target-eye;forward/=np.linalg.norm(forward)
    right=np.cross([0,0,1],forward);right/=np.linalg.norm(right)
    down=np.cross(forward,right)
    return eye,np.column_stack((forward,right,down))


def relative_camera_pose(eye_ned, camera_to_ned, kinematics):
    pose=kinematics['pose'];p=pose['position'];q=pose['orientation']
    position=np.array([p[k] for k in ('x','y','z')])
    body=Rotation.from_quat([q[k] for k in ('x','y','z','w')]).as_matrix()
    translation=body.T@(eye_ned-position)
    quat=Rotation.from_matrix(body.T@camera_to_ned).as_quat()
    return {'frame_id':'DEFAULT_ID','translation':dict(zip(('x','y','z'),translation.tolist())),
            'rotation':dict(zip(('x','y','z','w'),quat.tolist()))}


def queue_chase_camera_pose(drone, position_rf, receiver_positions_rf, kinematics, *, sensor='Chase',distance_m=CHASE_DISTANCE_M,elevation_bias=.25):
    """Queue a view for the next renderer tick without waiting on a paused world.

    ProjectAirSim's default waits for Unreal to apply the pose. Our single
    stepping owner must return from this RPC before it can advance the world;
    waiting here can time out even though the pose request was accepted.
    """
    eye, rotation = camera_frame(position_rf, receiver_positions_rf,distance_m=distance_m,elevation_bias=elevation_bias)
    if not drone.set_camera_pose(sensor, relative_camera_pose(eye, rotation, kinematics),
                                 wait_for_pose_update=False):
        raise RuntimeError('Chase camera pose request was rejected')
    return eye, rotation


def project_radios(eye_ned,camera_to_ned,points_rf,width,height,fov_deg=CAMERA_FOV_DEG):
    points=np.asarray(points_rf)*[1,-1,-1]
    local=(points-eye_ned)@camera_to_ned
    focal=width/(2*np.tan(np.deg2rad(fov_deg)/2))
    return np.column_stack((width/2+focal*local[:,1]/local[:,0],
                            height/2+focal*local[:,2]/local[:,0],local[:,0]))


def camera_labels(message,mount_pose,receiver_positions_rf,document,*,fov_deg=CAMERA_FOV_DEG,platform_label='TX / DRONE'):
    """Project actual-frame TX/RX anchors; omit labels hidden by the shared mesh.

    The applied body-relative camera mount and native image pose reconstruct the
    drone origin at image time. This avoids using a newer RF pose for a delayed
    image. Camera visibility is separate from TX/RX propagation visibility.
    """
    from .geometry_sync import nearest_intersections
    eye=np.array([message['pos_'+axis] for axis in ('x','y','z')])
    rotation=Rotation.from_quat([message['rot_'+axis] for axis in ('x','y','z','w')]).as_matrix()
    q=mount_pose['rotation'];relative=Rotation.from_quat([q[k] for k in ('x','y','z','w')]).as_matrix()
    translation=np.array([mount_pose['translation'][k] for k in ('x','y','z')])
    drone=eye-rotation@relative.T@translation
    points=np.vstack((drone,np.asarray(receiver_positions_rf)*[1,-1,-1]))
    vectors=points-eye;distances=np.linalg.norm(vectors,axis=1)
    hits=nearest_intersections(document,np.tile(eye,(len(points),1)),vectors,
        maximum_distance_m=float(distances.max()))
    pixels=project_radios(eye,rotation,points*[1,-1,-1],message['width'],message['height'],fov_deg=fov_deg)
    labels=[]
    for index,((x,y,depth),hit,distance) in enumerate(zip(pixels,hits,distances)):
        if depth<=0 or not (0<x<message['width'] and 0<y<message['height']):continue
        if hit is not None and hit['distance_m']<distance-.01:continue
        labels.append({'text':platform_label if index==0 else f'RX {index-1}',
            'x':float(x),'y':float(y),'color_rgb':([255,200,90] if index==0 else
                [85,215,208] if index==1 else [230,185,108])})
    return labels


def radio_marker_glb(color):
    """Eight-metre radio location beacon; illustrative marker, not RF geometry."""
    from .glb_geometry import triangle_glb
    vertices=[];faces=[]
    for lo,hi in [([-1,-1,0],[1,1,-8]),([-5,-1,-6],[5,1,-8])]:
        start=len(vertices)
        vertices.extend([[x,y,z] for z in (lo[2],hi[2]) for y in (lo[1],hi[1]) for x in (lo[0],hi[0])])
        faces.extend([[start+a,start+b,start+c] for a,b,c in [(0,1,3),(0,3,2),(4,6,7),(4,7,5),(0,4,5),(0,5,1),(2,3,7),(2,7,6),(0,2,6),(0,6,4),(1,5,7),(1,7,3)]])
    return triangle_glb(vertices,faces,base_color_rgba=[*color,1],emissive_rgb=(np.asarray(color)*.7).tolist())
