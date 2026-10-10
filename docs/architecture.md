# Architecture and integration contracts

ProjectAirSim kinematics feed an RF scene. Sionna supplies complex paths; private
transmitter waveforms are rendered into complex voltages, combined per receiver,
filtered, corrupted by the chosen noise model, quantized, and recorded. The
[current gallery](sensing-plots.md) explains the simulated physical scenarios.

| Component | Implemented behavior | Qualification boundary |
| --- | --- | --- |
| AirSim adapter | Paused-world poses, mount mapping, elapsed-time capture | Offline contract and real static Runtime smoke tested; vehicle physics remains unqualified |
| Propagation | Direct/specular/first-order diffuse paths with an explicit per-link sampling budget | Synthetic material/terrain, not calibrated land backscatter |
| Sample rendering | Direct reference and Doppler-basis CPU/CUDA operators | Agreement with declared finite interpolation and delay/Doppler bounds |
| Receiver | Filter, noise, clock terms, ideal ADC and input-referred scale | No analog compression, measured ENOB, or calibrated hardware response |
| Live recording | Continuous timestamped int16 I/Q and per-window metadata | Controlled simulation stepping; no real-time streaming guarantee |
| Distributed radar worker | Radar pulse API and AMS-GRA adapter | Separate from continuous SDR capture |

<a id="radar"></a>

## Radar models

`examples/lfm_radar.py` demonstrates point-target pulsed LFM. Sionna computes the
one-way path and the model constructs a reciprocal return with scalar RCS.
It is a point-target approximation, not a general multiple-bounce radar solver.
`examples/distance2gol_radar.py` demonstrates an FMCW point-target receiver.
The terrain-scan experiment is separate: one moving bistatic TX/RX pair,
matched-filtered I/Q and a DEM midpoint-height reference. See
[terrain assumptions](terrain.md) and [observables](sensing-plots.md).

## Attach it to ProjectAirSim

RF Cartesian coordinates use z upward. AirSim NED positions and body-frame mounts
are mapped by `(x, -y, -z)`; rotations and linear/angular velocities are transformed
by the bridge. The RF geometry and simulator must share origin, units and scale.
A simulator building is not an RF obstruction unless its geometry is also in the
RF scene. Scripted terrain-following demonstration poses do not prove flight-control
or collision-avoidance behavior.

The live recorder pauses/steps the world and leaves it paused. It snapshots the
start pose, advances simulation, and creates the corresponding elapsed-duration
window. Narrowband path Doppler evolves inside that frozen-geometry window. The
next update snapshots a new channel. Choose cadence according to motion and
propagation dynamics. See [the complete live recipe](live-workflow.md).

<a id="end-to-end"></a>

## Pipeline timing

[Performance](performance.md) defines the measured trajectory-source workload.
It includes private source preparation, pose mapping, propagation/export,
rendering/transfers, receiver DSP and loopback delivery/readback. It excludes
live physics/RPC and initialization. Live-recording service has different timer
boundaries; do not substitute its costs or claim the benchmark measures a whole
flight. Always relate wall time to [signal duration](timing.md).

Benchmark scenes are versioned independently of presentation terrain. The
original low-relief timing mesh is `terrain_benchmark_v1`; the current sensing
scene uses 0–30 m relief. Physical inputs must match before comparing optimizations.

<a id="cots-sdr-lab"></a>

## Simulated SDR receiver and emitter contract

Each transmitter owns a private finite complex sample stream, a power scale and
frequency bounds. Arbitrary sampled I/Q is supported within the declared model.
Files are not looped or automatically normalized; outside their support the live
file source is zero. At unit mean sample power, configured watts represent mean
emitted power. History/lookahead and boundary behavior are explicit.

Each receiver combines every retained path and applies its configured filtering,
noise and ideal signed ADC. A Pluto-class profile means selected bandwidth,
rate and quantizer settings; it is not measured hardware calibration. The
numeric eight-bit control changes quantizer resolution under the chosen gain,
not the complete model of another commercial SDR. [Sensing diagnostics](sensing-plots.md)
show where that control returns only zero codes.

The general receiver supports clock errors; the current basis live workflow
requires nominal equal sample clocks. The passive plot's known-clock correction
is postprocessing assisted by simulated truth, not an implemented blind clock
calibration algorithm. Paths retain their complex phase and coefficients; delay
and Doppler alone do not determine a coherent voltage.

<a id="distributed"></a>

## Distributed interfaces

`airsim-rf-worker` and `airsim-rf-coordinator` provide the radar worker API.
`examples/distributed_hello.py` exercises two workers offline. Receiver durations
are concurrent; aggregate sample traffic must be labeled explicitly rather than
summing durations into simulated elapsed time.

<a id="ams-gra-compatibility"></a>

## AMS-GRA integration

The radar worker and tested protocol adapters are distinct from the continuous
SDR recorder. `.sigmf-data`/`.sigmf-meta` files are recording artifacts, not a
native AMS-GRA stream or a physical SDR driver. The
[dated integration notes](archive/architecture-notes.md#ams-gra-compatibility)
retain protocol and deployment details and their qualification limits.

<a id="distance2gol"></a>

## Further detail

Use [rendering](rendering.md) for the sampled operator and numerical bounds,
[setup](setup.md) for supported environments, and [references](references.md)
for implementation precedents. The [archived architecture notes](archive/architecture-notes.md)
retain point-target equations, hardware-study references and earlier hybrid
experiments. Those historical commands are not the first-run workflow.
