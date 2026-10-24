[Documentation](../README.md) · [Scenarios](../../scenarios/README.md) · [Run dashboard](../dashboard.md)

# Configuration and integration interfaces

This is the local configuration/recording interface for RF/SDR developers.
Generate a working file with `airsim-rf example` and modify one field at a time.
Run `airsim-rf preflight` with the intended capture counts before recording;
the live runner also performs those checks before GPU initialization or world
loading. Unknown configuration keys are errors, so misspellings cannot silently
leave a default in effect.

## Live configuration

All file paths resolve beside the JSON configuration, including absolute paths
when explicitly supplied. IDs and units are part of the interface:

| Key | Meaning |
| --- | --- |
| `address` | ProjectAirSim server address. The current client workflow uses default ports 8989/8990. |
| `sim_config`, `scene` | Simulator configuration directory and scene filename. Every radio's robot must exist in the scene, and each robot-config file must be present relative to that directory. Simulator JSONC comments require the client's `commentjson` dependency. |
| `rf_scene` | RF XML with its referenced meshes. With a bundle, this must be that bundle's `scene.xml`. |
| `geometry_bundle` | Optional immutable geometry directory with checked manifest/hashes, simulator bindings and RF object IDs. |
| `geometry_placement` | `existing` (default) reads actors after scene load; `spawn` explicitly creates the bundle's actors in that dedicated world. Requires a bundle. |
| `receiver_profile` | `PlutoSDRProfile` settings: carrier/sample rate/bandwidth in Hz, impedance in ohms, temperature in K, noise figure in dB, input ADC full scale in dBm and a boolean noise flag. See defaults and validation in [the source](../../src/airsim_rf/sdr.py). |
| `antennas` | Independent `tx`/`rx` objects with `pattern` (`iso`, `dipole`, `hw_dipole`, `tr38901`) and `polarization` (`V` or `H`). One element/channel per radio; default `hw_dipole`/`V`. |
| `propagation` | `mode` (`direct`, `specular`, `diffuse-angular`, `diffuse-surface`), `samples_per_link` (integer ≥2), `seed` (nonnegative integer). Attempted diffuse samples are not an I/Q sample count or convergence guarantee. |
| `radios` | Nonempty mapping of radio IDs to settings below; at least one TX and one RX. IDs use letters, digits, `_` and `-`. |

Each radio has `robot` (simulator robot name) and optional `mount_body_m`
(three body-frame metres, default zero). A transmitter additionally requires
`waveform_npy`, positive `transmit_power_w`, and increasing
`baseband_frequency_bounds_hz`. A radio without a waveform is a receiver.
Multiple radios may share a robot. Mixed per-radio arrays, rate profiles or
separate antenna boresight offsets are not exposed by this JSON interface.

Compatibility: configurations without `propagation` retain `diffuse-angular`;
legacy top-level `samples_per_link` remains accepted. New examples explicitly
select `specular`. Prefer explicit mode selection.

## Time, coordinates and amplitude

| Quantity | Contract |
| --- | --- |
| World positions | Simulator NED metres → RF north/west/up `(x,-y,-z)`; do not pass raw Unreal centimetres as NED. |
| Mounts | Body-frame metres, rotated by robot attitude; angular velocity contributes lever-arm velocity. |
| Timestamps | Integer simulator nanoseconds at window start. Subtract integer epochs before conversion to seconds. |
| Samples | Complex baseband `I + jQ`; occupied baseband frequencies are relative to the carrier. Source rate equals the configured nominal receiver rate. |
| TX normalization | The sampled array is not normalized or looped. TX watts scale squared sample amplitude; unit mean sample power makes configured watts the average source power. |
| Channel | Paths use the paused start pose, then per-path narrowband Doppler within that window. The next window refreshes geometry; acceleration can cause a model phase correction. |
| Receiver voltage | Complex input-referred volts under the configured impedance/power convention, not a measured SDR's calibrated transfer function. |

The live runner requires a steppable clock for its capture plan. It accounts for
configured tick overshoot, verifies integer sample alignment, and checks each
actual interval again during capture. A planned source must cover all windows
plus the default 16-sample lookahead. Zero boundary at transmission onset is
explicit; this interface does not add prehistory or loop the source.

## Python entry points

```python
from airsim_rf.live import run, record
from airsim_rf.preflight import check
from airsim_rf.recording import iter_sample_blocks

plan = check("inputs/radios.json", updates=10, advance_ns=10_000_000)
run("inputs/radios.json", "capture", updates=10, advance_ns=10_000_000,
    on_samples=process_samples)
```

`run` owns client connection, scene loading, pause/advance and disconnection.
`record(world, robots, receiver, output, ...)` instead uses already-created
handles and a continuous receiver; use it when your application owns flight and
world preparation. Map every scene TX/RX ID to a robot handle. Pass the matching
`geometry_binding` when using the lower-level API; omission makes no geometry
equivalence claim. Complete shared-scene loading is implemented in
[live.py](../../src/airsim_rf/live.py).

`on_samples(block)` runs synchronously after the window is saved. The simulator
is paused; callback time is included in service timing. Keep state per receiver.
Exceptions fail recording and preserve completed data. `SampleBlock` exposes
post-ADC complex volts, channel ID, acquisition `timestamp_ns`, sample offset,
rate, carrier and clipping fraction. It contains no paths, pre-ADC reference or
source truth. `iter_sample_blocks()` provides the same neutral recording view.

The legacy `on_capture(receiver_id, capture)` exposes full simulation capture
instrumentation, including pre-ADC data. It is retained for diagnostics, not for
new RF skills. See the [boundary guide](../skill-boundary.md).

## Recording and process boundaries

| File/API | Format and use |
| --- | --- |
| `<rx>.sigmf-data` | Headerless little-endian signed int16 `I0,Q0,I1,Q1,...`; signed 12-bit values −2048…2047; four bytes per complex sample. |
| `<rx>.sigmf-meta` | SigMF datatype/rate/carrier/offset plus per-capture simulator time, volts-per-count and clipping. Apply each capture's scale; do not divide by 32768. |
| `manifest.json` | Running/complete/failed state, per-window timestamps/counts/timing and input/backend/geometry provenance. Consume only immutable completed recordings. |
| `iter_iq_blocks(directory, receiver, units="volts")` | Window-sized complex64 arrays, rate, timestamp, sample offset, carrier and clipping. `units="adc_codes"` returns raw integer-valued complex samples. Rejects inconsistent counts/times/metadata/range. |
| Official SigMF | `sigmf.fromfile(..., autoscale=False)`, then apply `airsim_rf:volts_per_count`. Only NumPy and SigMF are needed in a separate analysis environment; [example](../../examples/process_sigmf.py). |
| Separate process | The [experimental TCP adapter](iq-stream.md) adds framing and consumer completion. It is not a hardware SDR driver or distributed continuous-SDR plane. |

See the [SigMF extension definition](../extensions/airsim_rf.sigmf-ext.md) for exact
metadata names. Metadata checkpoints retain partial data on failure but are not
atomic or a crash-recovery guarantee. Bounded long-run memory, durable checkpoints
and consumer-fault recovery remain priority 4.

AMS-GRA radar workers use a separate RPC/model interface. RF MEL, OMS/UCI/CAL and
DIS decisions are documented in the [standards selection](../archive/reviews/ase-standards-selection-20261018.md);
this package does not claim new standards certification or a continuous SDR bus.
