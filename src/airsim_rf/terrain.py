"""Small elevation grids exported as actual RF triangle geometry."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class TerrainGrid:
    """Cartesian metres, z upward; heights[y_index, x_index].

    Cells use the lower-left to upper-right diagonal. Elevation queries use
    the same piecewise planar interpolation as the exported triangle mesh.
    """
    x_m: np.ndarray
    y_m: np.ndarray
    heights_m: np.ndarray

    def __post_init__(self):
        for name in ('x_m', 'y_m', 'heights_m'):
            value = np.array(getattr(self, name), dtype=float, copy=True)
            if not np.isfinite(value).all():
                raise ValueError("Terrain coordinates/heights must be finite")
            value.flags.writeable = False
            object.__setattr__(self, name, value)
        if any(axis.ndim != 1 or axis.size < 2 or np.any(np.diff(axis) <= 0)
               for axis in (self.x_m, self.y_m)):
            raise ValueError("Terrain axes must be increasing 1-D arrays with >=2 points")
        if self.heights_m.shape != (self.y_m.size, self.x_m.size):
            raise ValueError("Height shape must be [len(y), len(x)]")

    def mesh(self):
        x, y = np.meshgrid(self.x_m, self.y_m)
        vertices = np.column_stack((x.ravel(), y.ravel(), self.heights_m.ravel()))
        ny, nx = self.heights_m.shape
        a = (np.arange(ny-1)[:, None]*nx+np.arange(nx-1)[None, :]).ravel()
        faces = np.stack((np.column_stack((a, a+1, a+nx+1)),
                          np.column_stack((a, a+nx+1, a+nx))), axis=1).reshape(-1, 3)
        return vertices, faces

    def elevation_at(self, x_m, y_m):
        x, y = np.broadcast_arrays(np.asarray(x_m, dtype=float), np.asarray(y_m, dtype=float))
        if (not np.isfinite(x).all() or not np.isfinite(y).all()
                or np.any((x < self.x_m[0]) | (x > self.x_m[-1]))
                or np.any((y < self.y_m[0]) | (y > self.y_m[-1]))):
            raise ValueError("Elevation query is outside the DEM or nonfinite")
        ix = np.clip(np.searchsorted(self.x_m, x, side='right')-1, 0, self.x_m.size-2)
        iy = np.clip(np.searchsorted(self.y_m, y, side='right')-1, 0, self.y_m.size-2)
        u = (x-self.x_m[ix])/(self.x_m[ix+1]-self.x_m[ix])
        v = (y-self.y_m[iy])/(self.y_m[iy+1]-self.y_m[iy])
        h00, h10 = self.heights_m[iy, ix], self.heights_m[iy, ix+1]
        h01, h11 = self.heights_m[iy+1, ix], self.heights_m[iy+1, ix+1]
        return np.where(v <= u, h00+(h10-h00)*u+(h11-h10)*v,
                        h00+(h11-h01)*u+(h01-h00)*v)

    def write_ply(self, filename):
        vertices, faces = self.mesh()
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w') as output:
            output.write('ply\nformat ascii 1.0\n')
            output.write(f'element vertex {len(vertices)}\nproperty float x\nproperty float y\nproperty float z\n')
            output.write(f'element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n')
            np.savetxt(output, vertices, fmt='%.9g')
            np.savetxt(output, np.column_stack((np.full(len(faces), 3), faces)), fmt='%d')


def demo_terrain():
    """Deterministic synthetic DEM: broad hills, drainage swale and low relief.

    No surveyed location, small-scale roughness or land-cover calibration is
    implied. Material properties belong to the scene, not elevation samples.
    """
    axis = np.linspace(-100, 100, 21)
    x, y = np.meshgrid(axis, axis)
    heights = (2+.01*x
               +5.5*np.exp(-((x+40)/28)**2-((y+25)/35)**2)
               +3.5*np.exp(-((x-50)/35)**2-((y-40)/25)**2)
               -3*np.exp(-((y-.25*x-10)/14)**2)
               +.8*np.sin(x/30)*np.cos(y/35))
    return TerrainGrid(axis, axis, heights)
