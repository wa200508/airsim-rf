"""First-order monostatic terrain backscatter on the shared Sionna mesh.

sigma0 is RCS per square metre of actual surface area at normal incidence.
A configurable cosine exponent supplies an illustrative angular response. This
is an explicit phenomenological model, not inferred from dielectric properties.
"""
import numpy as np


def segment_visibility(scene,origin,endpoints):
    """Batch direct segments on the active Mitsuba CPU/CUDA backend.

    Shorten both ends to avoid surface self-intersection. The tolerance scales
    with float32 ray precision, not an RF wavelength or visibility heuristic.
    """
    import mitsuba as mi
    points=np.asarray(endpoints,float).reshape(-1,3)
    if not len(points):return np.empty(0,bool)
    delta=points-np.asarray(origin,float);distance=np.linalg.norm(delta,axis=1)
    if np.any(distance<=0) or not np.isfinite(distance).all():raise ValueError('Visibility segments must be finite and nonzero')
    direction=delta/distance[:,None]
    epsilon=np.minimum(distance*.1,np.maximum(1e-5,8*np.finfo(np.float32).eps*distance))
    ray=mi.Ray3f(mi.Point3f((np.asarray(origin)+direction*epsilon[:,None]).T),mi.Vector3f(direction.T))
    ray.maxt=mi.Float(distance-2*epsilon)
    return ~scene.mi_scene.ray_test(ray).numpy()


class TerrainBackscatter:
    """Seeded, uniform-area stratified quadrature; one coherent return per patch.

    All material classes are sampled across the whole configured static mesh.
    Range/normal tests precede visibility. Geometry/count/seed changes start a
    new realization; motion alone never redraws samples or their phases.
    """
    def __init__(self,scene,configuration,*,samples_per_link):
        self.scene=scene;self.configuration=configuration;self.samples_per_link=samples_per_link;self.fingerprint=None
        self.points=np.empty((0,3));self.normals=np.empty((0,3));self.rcs=np.empty(0)
        self.exponents=np.empty(0);self.weights=np.empty(0,complex);self.total_area_m2=0.

    def prepare(self):
        import mitsuba as mi
        c=self.configuration;objects=c['shape_materials'];shapes=list(self.scene.mi_scene.shapes())
        # Retain buffers as well as their IDs, as Dr.Jit can recycle IDs.
        selected_shapes=[s for s in shapes if s.id() in objects]
        if any(not isinstance(s,mi.Mesh) for s in selected_shapes):raise ValueError('Terrain clutter requires triangle meshes')
        buffers=[(s,s.vertex_positions_buffer(),s.faces_buffer()) for s in selected_shapes]
        rules=tuple((name,rule['sigma0_db'],rule['incidence_exponent']) for name,rule in sorted(c['materials'].items()))
        fingerprint=(self.samples_per_link,c['seed'],rules,tuple((s,v.index,f.index,objects[s.id()]) for s,v,f in buffers))
        if fingerprint==self.fingerprint:return
        triangles=[];materials=[]
        for shape,vertices,faces in buffers:
            if not isinstance(shape,mi.Mesh):raise ValueError('Terrain clutter requires triangle meshes')
            xyz=vertices.numpy().reshape(-1,3);indices=faces.numpy().reshape(-1,3)
            triangles.extend(xyz[indices]);materials.extend([objects[shape.id()]]*len(indices))
        if not triangles:raise ValueError('Enabled clutter has no configured surface meshes')
        triangles=np.asarray(triangles,float);cross=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        area=np.linalg.norm(cross,axis=1)/2
        if np.any(area<=0) or not np.isfinite(area).all():raise ValueError('Terrain clutter requires finite positive triangle areas')
        self.total_area_m2=float(area.sum());count=self.samples_per_link;rng=np.random.default_rng(c['seed'])
        cumulative=np.cumsum(area)
        chosen=np.searchsorted(cumulative,(np.arange(count)+rng.random(count))*self.total_area_m2/count)
        bary=rng.random((count,2));root=np.sqrt(bary[:,0]);tri=triangles[chosen]
        self.points=(1-root[:,None])*tri[:,0]+(root*(1-bary[:,1]))[:,None]*tri[:,1]+(root*bary[:,1])[:,None]*tri[:,2]
        self.normals=cross[chosen]/(2*area[chosen,None])
        rules=[c['materials'][materials[i]] for i in chosen]
        self.rcs=np.array([10**(rule['sigma0_db']/10) for rule in rules])*self.total_area_m2/count
        self.exponents=np.array([rule['incidence_exponent'] for rule in rules])
        self.weights=np.exp(2j*np.pi*rng.random(count))
        self.fingerprint=fingerprint;self.buffers=buffers

    def candidates(self,position,max_range_m):
        self.prepare();delta=np.asarray(position)-self.points;distance=np.linalg.norm(delta,axis=1)
        in_range=(distance>0)&(distance<=max_range_m)
        cosine=np.sum(self.normals*delta,axis=1)/np.maximum(distance,np.finfo(float).tiny)
        selected=np.flatnonzero(in_range&(cosine>0))
        rcs=self.rcs[selected]*np.clip(cosine[selected],0,1)**self.exponents[selected]
        self.diagnostics={'sample_count':len(self.points),'in_range':int(in_range.sum()),'front_facing':len(selected),
                          'surface_area_m2':self.total_area_m2,'visible':0,'contributing':0}
        return self.points[selected],rcs,self.weights[selected]
