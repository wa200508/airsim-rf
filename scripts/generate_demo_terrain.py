"""Regenerate the committed 10 m synthetic terrain fixture."""
from pathlib import Path

from airsim_rf.terrain import demo_terrain


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1]/'benchmarks/scenes/terrain.ply'
    terrain = demo_terrain()
    terrain.write_ply(path)
    print(f'{path}: {terrain.heights_m.shape}, elevation {terrain.heights_m.min():.2f} to {terrain.heights_m.max():.2f} m')
