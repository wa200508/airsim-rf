# Setup and supported environments

Use Python **3.12** for the tested lock. The package declares a wider Python
range, but that declaration is not a tested environment matrix. The simulator
server is a separate component; installing the Python client does not launch it.

| Workflow | Environment | Status |
| --- | --- | --- |
| Offline examples/tests | Standard locked Sionna RT stack, LLVM | CPU CI and offline tests |
| GPU live capture | Standard stack plus CuPy and CUDA libraries | Real static Runtime smoke tested on the explicit P100 stack; other devices need qualification |
| Pascal/P100 capture | Sionna RT 2.2.0, Mitsuba 3.8.0, Dr.Jit 1.3.1, CuPy 13.6, CUDA 12.2 libraries | Explicit compatibility adapter; measured GPU pipeline |
| Sensing gallery postprocessing | Scientific Python with recorded source files | Backend-neutral observables; CUDA CAF is optional |

<a id="reproduce"></a>

## Offline first run

```bash
git clone https://github.com/wa200508/airsim-rf.git
cd airsim-rf
python3.12 scripts/bootstrap.py
.venv/bin/python -m pytest tests -q
.venv/bin/python examples/distance2gol_radar.py
```

Bootstrap fetches clean pinned ProjectAirSim client and Sionna source checkouts
from `sources.json` into ignored `.deps/` paths. It installs the tested lock and
editable packages. LLVM/system libraries must be available for propagation; see
the [container recipe](#container) if using an isolated environment. No simulator
is needed for the offline point-target example.

## Live CUDA dependencies

The `live` extra declares CuPy and the optional ProjectAirSim client. CUDA-enabled
propagation additionally requires a compatible driver/device and user-space
libraries. For the tested CUDA 12.2 library set:

```bash
.venv/bin/python -m pip install -e '.[live]' -r requirements-p100-cuda.txt
.venv/bin/python scripts/basis_launch.py -m airsim_rf.live --help
```

The CUDA library file's name records its original P100 qualification; installing
those libraries alone does not make current Mitsuba/Dr.Jit support Pascal. Use
the explicit P100 image below for that device. Run the
[two-radio live walkthrough](live-workflow.md) before scaling.

<a id="container"></a>

## Containers

```bash
docker build -t airsim-rf:test .
docker run --rm --network none airsim-rf:test
```

The ordinary Dockerfile is the CPU test environment. It is not a simulator server
or a CuPy live environment. GitHub Actions publishes tested CPU images to
`ghcr.io/wa200508/airsim-rf`; publication and source pins are in the
[development guide](development.md) and `sources.json`.

<a id="p100-profiling"></a>

## P100-compatible GPU environment

The compatibility stack keeps Sionna RT 2.2.0 but pins older Mitsuba/Dr.Jit.
The adapter has exact version/layout guards; dependency upgrades require new
qualification. The early legacy-Sionna tests are historical and are not this
current stack.

```bash
docker build -f Dockerfile.profiling --build-arg BASE_IMAGE=airsim-rf:test \
  --build-arg PROFILE_BASIS_CUDA=1 -t airsim-rf:p100-profile .
docker build -f Dockerfile.p100-gpu \
  --build-arg PROFILE_BASE_IMAGE=airsim-rf:p100-profile -t airsim-rf:p100-modern-gpu .
```

A host NVIDIA driver and NVIDIA Container Toolkit are required. For a source
checkout mounted at `/work/repo`, invoke Python with `scripts/basis_launch.py` to
expose pinned wheel libraries, and provide writable `/.drjit` and plotting/cache
paths. Keep the RF checkout mounted when exercising new changes; an existing
image otherwise contains its build-time source.

<a id="p100-basis-profiling"></a>

## Complete RF benchmark

Use the versioned original low-relief scene for matched performance comparisons:

```bash
docker run --rm --gpus device=0 --network none --tmpfs /.drjit:rw,mode=1777 \
  --user "$(id -u):$(id -g)" -v "$PWD:/work/repo" -w /work/repo \
  -e PYTHONPATH=/work/repo/src -e MPLCONFIGDIR=/tmp/matplotlib \
  --entrypoint /opt/airsim-rf/.venv/bin/python airsim-rf:p100-modern-gpu \
  scripts/basis_launch.py benchmarks/benchmark_end_to_end.py \
  --propagation-backend cuda --renderer basis-cuda --pascal-compat \
  --tx 2 --rx 2 --iterations 3 --warmup 1 --output results/end_to_end/first-gpu-check
```

Start small, inspect scene provenance and clearance, then use the declared
100×10 workload if desired. Never overwrite a result directory. The benchmark
uses deterministic trajectories and loopback storage, excluding live physics/RPC.
[Performance](performance.md) and [timing definitions](timing.md) identify scope
and simulation-time denominators. Device availability is not proof of a real-time
120 Hz update rate.

<a id="complete-rf-pipeline-fill-every-stage-row"></a>

## Profiling and historical recipes

Instrumented call traces diagnose stages but are not unprofiled throughput.
`--profile-rendering` and `--python-profile` are separate profiling controls.
Published measurement reproduction, collector/Nsight options, earlier hybrid
CPU-propagation commands and publication helpers are retained in
[dated setup recipes](archive/setup-recipes.md). Their old “no GPU available”
statement describes an earlier validation phase, not current workspace status.

<a id="regenerate-documentation-figures-on-the-p100"></a>

## Regenerate sensing figures

```bash
scripts/regenerate_p100_figures.sh
python3 scripts/check_docs.py
```

The script uses the available P100 to simulate the documented sensing scenarios,
then generates the current gallery, mesh-visibility checks and source manifests.
The simulation source data and plot interpretation are hardware-neutral; device
information stays in provenance. For postprocessing existing recordings without
new simulation, run the two commands in [the sensing guide](sensing-plots.md).
