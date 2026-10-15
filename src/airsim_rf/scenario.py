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
