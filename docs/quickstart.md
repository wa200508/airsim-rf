# First complete shared-scene recording

This path is for RF/SDR engineers and algorithm developers using the qualified
Linux x86-64/Docker/NVIDIA environment. It prepares one common geometry source,
records a known waveform through a real simulator and RF solver, and reads the
result into a CPU processor. Keep this work local; no registry, release or
package upload is needed. [Capability and acceptance matrix](capabilities.md).

For a self-contained moving-emitter direction-finding consumer, start with
[MUSIC AoA and emitter tracking](aoa-emitter-tracking.md). That example uses
a supplied RF trajectory and runs without a simulator.

## 1. Install and prepare on CPU

Use Python 3.12, Git and the system libraries in the
[setup guide](setup.md). From the repository root:

```bash
python3.12 scripts/bootstrap.py --geometry
source .venv/bin/activate
airsim-rf example --output recordings/shared-inputs
airsim-rf preflight --config recordings/shared-inputs/radios.json \
  --output recordings/shared-capture
```

Bootstrap creates a project virtual environment, checks out the exact Sionna
and ProjectAirSim client commits in `sources.json`, and installs the locked
dependencies plus the qualified OpenUSD 26.8 pin. It needs network access on
first use and refuses to replace a modified dependency checkout.

The installed `airsim-rf` command includes its example assets; generating inputs
also works outside the checkout. The output directory must be new. It contains
`radios.json`, `tx0.npy`, simulator robot/scene configurations, the source USD
and RF profile, an exported `bundle/`, and `README.txt`. All runtime file paths
resolve beside `radios.json`. The generated directory can be copied together;
source provenance retains the original source paths as historical information.

The default scene has a ground slab, sloping-roof building and rotated wall,
all described by explicit triangles. `geometry_placement: "spawn"` creates GLB
collision meshes from those triangles after loading the simulator scene. The
same triangles produce the RF meshes. This requires **Blocks 1.0.1**, rather
than the standalone Runtime's flat-ground host. It places stationary non-physics
radios at NED `(-20,0,-120)` and `(20,0,-120)` m; the ground is NED z = −100 m.
This baseline tests the complete recording workflow; it does not command flight.

The waveform is a unit-power +150 kHz complex tone at 2 MS/s, 500,000 samples
(0.25 s), with a 915 MHz carrier and 0.1 mW configured transmit power. The
shared example disables receiver noise for repeatable inspection. Default
antennas are single, vertically polarized half-wave dipoles. RF properties are
illustrative constant dielectric values, not calibrated material measurements.

Preflight validates the radio/robot mapping and every referenced input, bundle
hashes, receiver and propagation settings, source duration, physics tick/sample
alignment, sample cap and optional output space. For the default ten requested
10 ms advances and 3 ms physics ticks it reports:

| Planned quantity | Expected value |
| --- | ---: |
| Actual interval under the configured clock | 12,000,000 ns |
| Complex samples per receiver per window | 24,000 |
| Total complex samples per receiver | 240,000 |
| Signal seconds per receiver | 0.120 |
| Raw receiver I/Q bytes | 960,000 |

This is a clock-based plan. The actual recording timestamps and counts remain
authoritative. Preflight does not connect to a simulator or prove geometry
equivalence. `--gpu` adds a CUDA/OptiX solve, actual RF mesh loading and a
CPU-referenced CuPy renderer check; it still does not contact the server.

## 2. Prepare the CUDA environment and simulator

The [setup guide](setup.md#p100-profiling) gives the CPU, profiling and P100
image build commands. The following commands use the qualified P100 image.
Other GPUs need their own qualification; omit the Pascal option only when using
the ordinary supported dependency stack on a compatible device.

Fetch the checksum-pinned Blocks package once (about 558 MiB compressed):

```bash
python scripts/prepare_unreal_blocks.py
```

Start a dedicated server with default ports 8989/8990 available:

```bash
docker run --rm -d --name airsim-rf-demo-server \
  -p 127.0.0.1:8989:8989 -p 127.0.0.1:8990:8990 \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/.deps/blocks-linux-1.0.1/extracted:/blocks" -w /blocks \
  --entrypoint /blocks/Blocks/Binaries/Linux/Blocks-Linux-Shipping \
  airsim-rf:p100-profile Blocks -nullrhi -nosound -unattended
```

This is a collision/physics server with rendering disabled. The recorder owns
scene loading and simulation stepping; use a dedicated world. The original
Blocks map lies 100 m below the controlled shared scene and is outside its
declared RF domain. Only the selected shared surfaces participate in RF.

Use this helper to run the Python commands below in the existing GPU image with
the current local source. It also makes caches writable for the unprivileged user:

```bash
rfpython() {
  docker run --rm --gpus device=0 --network host \
    --user "$(id -u):$(id -g)" --tmpfs /.drjit:rw,mode=1777 -e HOME=/tmp \
    -e PYTHONPATH=/work/repo/src:/work/repo/.deps/openusd-26.8 \
    -v "$PWD:/work/repo" -w /work/repo \
    --entrypoint /opt/airsim-rf/.venv/bin/python airsim-rf:p100-modern-gpu "$@"
}
rfpython -m airsim_rf.cli preflight --config recordings/shared-inputs/radios.json \
  --output recordings/shared-capture --gpu --pascal-compat
```

If you rebuilt the current images, OpenUSD is installed in their virtual
environment; the extra ignored `.deps/openusd-26.8` path is only for the earlier
qualified local image. CUDA runtime libraries are exposed by the installed
launcher. CPU preparation and analysis require neither GPU access nor a server.

## 3. Record, inspect and consume

```bash
rfpython -m airsim_rf.cuda_launch -m airsim_rf.live --pascal-compat \
  --config recordings/shared-inputs/radios.json --output recordings/shared-capture \
  --updates 10 --advance-ns 10000000
airsim-rf inspect recordings/shared-capture
airsim-rf process recordings/shared-capture --receiver rx0
```

In an activated native CUDA environment, the recording command is
`airsim-rf-cuda -m airsim_rf.live` with the same arguments. `airsim-rf-live` also
works when CUDA libraries are already on the loader path. Actual captures use
CUDA propagation and rendering; there is no silent CPU fallback. First-use
compilation can dominate wall time. No real-time wall-clock rate is promised.

Success means `manifest.json` has `status: complete` and ten rows, each with
geometry identity and the start epoch. Expect `rx0.sigmf-data` (960,000 bytes),
`rx0.sigmf-meta` and contiguous timestamps. The inspector reports a final-window
peak near +150,000 Hz within its FFT-bin spacing (normally 488.28125 Hz), valid
signed 12-bit codes, and nonzero samples. The process command reports sample
count, sample rate, duration and reconstructed RMS complex volts. Levels depend
on propagation, antennas and ADC settings; no fixed calibrated power is promised.

Replace the CPU processor using the installed reader:

```python
from airsim_rf.recording import iter_sample_blocks

for block in iter_sample_blocks("recordings/shared-capture", "rx0"):
    process(block.samples, block.sample_rate_hz)  # your stateful algorithm
```

Keep processing state per receiver across blocks. For a synchronous callback,
use `airsim_rf.live.run(..., on_samples=process_samples)`. See
[interfaces](interfaces.md), [scenario customization](scenario-to-iq.md) and
[troubleshooting](troubleshooting.md).

Preserve logs and stop your example server when finished:

```bash
docker logs airsim-rf-demo-server > recordings/shared-server.log 2>&1
docker stop airsim-rf-demo-server
```

## Change the scenario

- Replace `tx0.npy` with finite one-dimensional complex samples at the declared
  sample rate. Set occupied frequency bounds inside Nyquist and TX power in watts.
  Amplitudes are preserved. Sources start at the initial capture epoch, are zero
  outside the file, and require sufficient capture duration plus lookahead.
- Edit the source USD/profile and export a new bundle to change geometry or RF
  materials. Keep the simulator and RF bundle on the same revision. Geometry
  changes require a fresh placement, RF scene, receiver and recording; see the
  [revision policy](openusd-workflow.md#geometry-changes-and-cache-lifetime).
- Add radio entries and corresponding simulator robots for additional sites.
  Each TX needs its own source file/allocation; receivers sum all TX paths.
  Keep all output IDs distinct. One configured receiver profile applies to all.
- For flight, replace non-physics robots with a supported physics/controller
  configuration and issue flight commands through a single stepping owner.
  `record(world, robots, receiver, ...)` uses an already prepared world. The
  [geometry closure harness](../scripts/qualify_live_motion.py) demonstrates
  real turning flight; it requires the pinned runtime source's controller files.

## Ground-only alternative

`airsim-rf example --geometry ground --output recordings/ground-inputs` creates
the earlier flat-ground example for the standalone Runtime server. It bundles
all its inputs and does not require OpenUSD. It has no shared-geometry guard or
nonprimitive collision meshes. Keep its matching flat-ground environment and
use the [Runtime instructions](live-workflow.md#complete-two-radio-first-run).
