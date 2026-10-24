[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# RF architecture and code ownership

![Shared scene, RF source, receiver I/Q, independent skills and observer](figures/rf-architecture.svg)

The maintained applications are [direction finding](../scenarios/drone-orbit/README.md)
and [FMCW radar](../scenarios/mmwave-radar/README.md). Each mission launches a
simulator container, an RF-source container and one independently packaged skill;
the dashboard and supervision run on the host.

## Scenario and source

A [scenario package](scenarios.md) owns the terrain/materials, vehicle, flight,
waveform/mode, radios/antennas, hardware profile and skill wiring. Preparation
exports the **same triangle mesh** to Unreal and Sionna, resolves AGL positions,
plans terrain-clearance paths, and freezes the inputs. Native flight readback
supplies actual RF antenna position, velocity and attitude. Display color does
not set dielectric properties. [Code map](code-map.md).

| Responsibility | Main code / data |
| --- | --- |
| Scenario validation and shared-scene compilation | [scenario_definition.py](../src/airsim_rf/scenario_definition.py), [dashboard_scenario.py](../src/airsim_rf/dashboard_scenario.py), [scenario inputs](../scenarios/README.md) |
| One owner of native physics stepping / kinematic snapshots | [dashboard_producer.py](../src/airsim_rf/dashboard_producer.py) |
| Coordinate/mount mapping, RF north/west/up ↔ AirSim NED | [bridge.py](../src/airsim_rf/bridge.py) |
| Shared geometry interchange / scene matching | [Geometry contract](reference/geometry-contract.md), [Unreal import](reference/unreal-geometry.md) |

The terrain-aware path is a native controller command, not a pose clamp in the
RF solver. Actual tracking can differ from planned clearance. New geometry needs
a fresh scene/bundle; geometry hashes and direct-ray checks guard alignment.

<a id="cots-sdr-lab"></a>

## One-way ESM and communications

Each TX owns private complex samples, power, carrier and frequency bounds.
The source computes directed radio-to-radio channels with complex gains,
fractional delays and Dopplers. Antenna TX/RX patterns, polarization, dielectric
properties and geometry determine those paths. The DF demo enables direct and
supported first-order specular paths; other experiments use different solvers.

Waveform rendering applies the channel to the private TX buffers and sums
coherent voltages at each receiver. The deployed one-way renderer uses the
Doppler-basis / FFT operator within declared delay, Doppler and interpolation
bounds; reference CPU/direct operators are also available. Filtering, independent
receiver noise and ADC conversion produce the acquired samples. The current basis
workflow requires equal nominal sample clocks. [Rendering details](rendering.md),
[SDR front end](../src/airsim_rf/sdr.py), [clutter/multipath](clutter.md).

<a id="radar"></a>

## Active radar

The RF adapter simulates a transmitter and dechirped receiver. The radar skill
knows its own waveform/mode and commands TX/RX configuration/state through a
hardware-neutral control API. The source returns receiver samples, without
feeding target locations or expected detections to the skill.

Each visible point target or terrain patch contributes one first-order echo.
Point RCS and empirical surface sigma0 × area set strength; mesh visibility,
both antenna gains, round-trip delay, carrier phase and Doppler set the coherent
response. There is no outbound/return path cross-product or target-leg multipath.
Visibility is refreshed per chirp using locally extrapolated platform motion;
native kinematics are refreshed per source window. This is narrowband Doppler,
not wideband time scaling. [Physical model](radar-scattering.md).

[FMCW synthesis](../src/airsim_rf/fmcw.py) runs on host NumPy even when visibility
uses CUDA. The [window adapter](../src/airsim_rf/dashboard_radar.py) retains receive
gates at their PRI positions. This differs from continuous DF/ESM I/Q, and
from legacy pulsed-LFM examples. [Detailed radar reference](reference/radar-scenario.md).

## Acquisition and skill boundary

Only post-ADC complex volts and hardware metadata cross the
[receiver contract](skill-boundary.md): channel IDs, timestamps, sample offsets,
rate/carrier and array/gate calibration. The skill sees a receiver interface;
it imports neither the simulator nor scene/path truth. Active radar control is
valid knowledge of its own radio, rather than private simulation truth.

| Skill | Implementation | Outputs |
| --- | --- | --- |
| Direction finding | [DF-Skill](https://github.com/wa200508/DF-Skill) | MUSIC arrival candidates, spectra, waterfall and array diagnostics |
| Radar | [Radar-skill](https://github.com/wa200508/Radar-skill) | Range–Doppler map and thresholded candidate; active TX/RX commands |

The source waits on a generic complete-window acknowledgement, not a MUSIC or
radar result. Skill-owned [display descriptions](skill-display.md) expose plots,
metrics and units; the host renderer does not select an algorithm by scenario.
A physical adapter could implement the same contract; vendor hardware drivers
are not supplied or qualified here.

## Recording and observer

Post-ADC [cf32/SigMF recording](iq-replay.md) can feed the same unmodified skill
without rerunning physics or propagation. Radar replay sends no TX commands.
Source telemetry/camera and skill results are independent journals. Only the
observer joins them by timestamp for synchronized display, replay and held-out
evaluation. Truth cannot flow back into a deployed skill through that join.
[Dashboard guide](dashboard.md), [GNU Radio development](gnuradio.md).

<a id="end-to-end"></a>

## Timing

The **[profiling page](profiling.md)** is the timing entry point. Per-sample
RF rate, per-window acquisition time, per-chirp channel refresh, service wall
time and display latency are different quantities. Historical renderer or RF-only
numbers do not measure the current native simulator/skill/camera loop.

<a id="distributed"></a>
<a id="ams-gra-compatibility"></a>

## AMS-GRA and distributed interfaces

`airsim-rf-worker` / `airsim-rf-coordinator` and the
[two-worker example](../examples/distributed_hello.py) provide a separate radar
worker integration. The dashboard's acknowledged TCP v2 stream preserves coherent
channel metadata; it is distinct from stock bare SC16 UDP and is not native
MEL/VITA conformance. A native coherent-array bridge and physical drivers require
additional integration. [Contracts and limits](skill-boundary.md),
[dated integration details](archive/architecture-notes.md#ams-gra-compatibility).

<a id="distance2gol"></a>

## Additional examples and references

The [Infineon Distance2GoL example](../examples/distance2gol_radar.py),
[pulsed LFM](../examples/lfm_radar.py), [offline sensing gallery](reference/sensing-plots.md)
and [manual live recorder](reference/live-workflow.md) have different configurations and
qualification scopes. They are not extra dashboard scenarios.
[External sources](references.md), [capability matrix](capabilities.md),
[historical architecture studies](archive/architecture-notes.md).
