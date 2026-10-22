"""Actual scene framing and presentation-only radio location markers."""
import numpy as np
from scipy.spatial.transform import Rotation


def camera_frame(position_rf, receiver_positions_rf):
    """World NED camera outside/above the drone, aimed between the radios."""
    flip=np.array([1,-1,-1]);position=np.asarray(position_rf,float)
    center=np.mean(receiver_positions_rf,axis=0)
    outward=position-center;outward[2]=0;outward/=np.linalg.norm(outward)
    eye=(position+100*outward+[0,0,65])*flip
    target=(.45*position+.55*center)*flip
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


def project_radios(eye_ned,camera_to_ned,points_rf,width,height,fov_deg=90):
    points=np.asarray(points_rf)*[1,-1,-1]
    local=(points-eye_ned)@camera_to_ned
    focal=width/(2*np.tan(np.deg2rad(fov_deg)/2))
    return np.column_stack((width/2+focal*local[:,1]/local[:,0],
                            height/2+focal*local[:,2]/local[:,0],local[:,0]))


def radio_marker_glb(color):
    """Eight-metre radio location beacon; illustrative marker, not RF geometry."""
    from .glb_geometry import triangle_glb
    vertices=[];faces=[]
    for lo,hi in [([-1,-1,0],[1,1,-8]),([-5,-1,-6],[5,1,-8])]:
        start=len(vertices)
        vertices.extend([[x,y,z] for z in (lo[2],hi[2]) for y in (lo[1],hi[1]) for x in (lo[0],hi[0])])
        faces.extend([[start+a,start+b,start+c] for a,b,c in [(0,1,3),(0,3,2),(4,6,7),(4,7,5),(0,4,5),(0,5,1),(2,3,7),(2,7,6),(0,2,6),(0,6,4),(1,5,7),(1,7,3)]])
    return triangle_glb(vertices,faces,base_color_rgba=[*color,1],emissive_rgb=(np.asarray(color)*.7).tolist())
