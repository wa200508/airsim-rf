"""User-facing propagation choices shared by configuration and recording."""


def propagation_options(config):
    propagation = config.get('propagation', {})
    if not isinstance(propagation, dict):
        raise ValueError('propagation must be an object with a mode')
    unknown = set(propagation) - {'mode', 'samples_per_link', 'seed'}
    if unknown:
        raise ValueError(f'Unknown propagation settings: {sorted(unknown)}')
    mode = propagation.get('mode', 'diffuse-angular')
    if mode not in ('direct', 'specular', 'diffuse-angular', 'diffuse-surface'):
        raise ValueError('propagation.mode must be direct, specular, diffuse-angular, or diffuse-surface')
    samples = propagation.get('samples_per_link', config.get('samples_per_link', 1028))
    seed = propagation.get('seed', 42)
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
        raise ValueError('propagation.samples_per_link must be an integer >= 2')
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('propagation.seed must be a nonnegative integer')
    return {'path_solver': 'single-bounce' if mode == 'specular' else 'first-order-scattering',
            'max_depth': 0 if mode == 'direct' else 1,
            'surface_sampling': mode == 'diffuse-surface',
            'samples_per_link': samples, 'seed': seed}


def antenna_options(config):
    """Single-element TX/RX arrays; omitted settings preserve half-wave dipoles."""
    antennas=config.get('antennas',{})
    if not isinstance(antennas,dict) or set(antennas)-{'tx','rx'}:
        raise ValueError('antennas must contain only tx and rx objects')
    result={}
    for side in ('tx','rx'):
        values=antennas.get(side,{})
        if not isinstance(values,dict) or set(values)-{'pattern','polarization'}:
            raise ValueError(f'antennas.{side} accepts pattern and polarization')
        pattern=values.get('pattern','hw_dipole');polarization=values.get('polarization','V')
        if pattern not in ('iso','dipole','hw_dipole','tr38901'):
            raise ValueError(f'antennas.{side}.pattern must be iso, dipole, hw_dipole, or tr38901')
        if polarization not in ('V','H'):
            raise ValueError(f'antennas.{side}.polarization must be V or H (one channel)')
        result[side]={'num_rows':1,'num_cols':1,'pattern':pattern,'polarization':polarization}
    return result
