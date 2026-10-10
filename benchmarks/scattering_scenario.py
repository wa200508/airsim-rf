"""Shared geometry and trajectories for timing and documentation runs."""
from pathlib import Path

import numpy as np


def load_fixture(name, transmitters, receivers, *, historical=False):
    import sionna.rt as rt
    scene_name = 'terrain_benchmark_v1' if historical and name == 'terrain' else name
    scene = rt.load_scene(str(Path(__file__).resolve().parent/'scenes'/f'{scene_name}.xml'))
    scene.frequency = 24.125e9
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='tr38901', polarization='V')
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern='tr38901', polarization='V')
    for i in range(transmitters):
        scene.add(rt.Transmitter(f'tx_{i}', position=[0, -25+50*i/max(transmitters-1, 1), 10],
                                orientation=[0, np.pi/2, 0], velocity=[1, 0, 0]))
    for i in range(receivers):
        scene.add(rt.Receiver(f'rx_{i}', position=[10, -5+i, 15],
                             orientation=[0, np.pi/2, 0], velocity=[0, .5, 0]))
    return scene


def update_platforms(scene, epoch):
    count = len(scene.transmitters)
    for i, tx in enumerate(scene.transmitters.values()):
        tx.position = [epoch, -25+50*i/max(count-1, 1), 10]
        tx.orientation = [0, float(np.pi/2+.05*np.sin(epoch+i)), 0]
    for i, rx in enumerate(scene.receivers.values()):
        rx.position = [10, -5+i+.5*epoch, 15]
        rx.orientation = [0, float(np.pi/2+.05*np.sin(epoch)), 0]
