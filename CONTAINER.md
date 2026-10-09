# Run the tests in a container

**Timing scope:** Mixed scope or architecture/reference document; each workload/table retains its stated timed operation. [Common measurement definitions](TIMING_CONVENTIONS.md) apply to units, statistics, cache state, ratios and comparisons. Historical measurements and estimates are not current fleet-update qualification.



For the GPU profiling branch, [P100_PROFILING.md](P100_PROFILING.md) provides
a pinned-base profiling image, host launcher and results-publication helper.

The CPU image bundles Python 3.12, LLVM 19, the pinned Sionna RT and ProjectAirSim
Python SDK, and this project's code and tests. Tests run as an unprivileged user
and require no GPU, running AirSim instance, or network access. This is the RF
test environment; a native AirSim/Unreal simulator is installed separately.

## Pull and test

After the repository's **Test and publish container** workflow succeeds:

```bash
docker pull ghcr.io/wa200508/airsim-rf:latest
docker run --rm --network none ghcr.io/wa200508/airsim-rf:latest
```

The default command runs the entire pytest suite and returns a nonzero exit code
on failure. Published images currently target Linux x86-64 (`linux/amd64`).
Docker Desktop supports this image; ARM hosts may need `--platform linux/amd64`
and emulation, which has not been tested here. Container timing under emulation
should not be used to judge real-time RF performance.

GitHub may initially create a private package even for a public repository.
For anonymous pulls, set the `airsim-rf` package's visibility to **Public** in
your GitHub package settings. If it stays private, authenticate with
`docker login ghcr.io` using a token with `read:packages`.

Each published build also gets a `sha-<full repository commit>` tag. Use that
tag, or the registry digest, to reproduce a particular image rather than the
moving `latest` tag.

## Examples and benchmarks

Override the default command to generate radar I/Q. Mount a writable output
directory to keep the recording and plot after the container exits:

```bash
mkdir -p output
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/output:/work" ghcr.io/wa200508/airsim-rf:latest \
  python /opt/airsim-rf/examples/distance2gol_radar.py

docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/output:/work" ghcr.io/wa200508/airsim-rf:latest \
  python /opt/airsim-rf/benchmarks/benchmark_rf.py \
  --backend cpu --targets 2 --fft --iterations 1000 --output /work/timing.json
```

These bind-mount commands use a Linux/macOS shell. On Docker Desktop, adapt the
host path for your shell and omit `--user` if needed. The image includes the
CPU backend; NVIDIA/CUDA operation is outside this container's validated scope.
See [PERFORMANCE.md](PERFORMANCE.md) for timing limitations.

The [COTS SDR lab](COTS_SDR_LAB.md) runs two beacons and two passive receivers
through shared terrain propagation, a Pluto-class front end and I/Q export:

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/output:/work" ghcr.io/wa200508/airsim-rf:latest \
  python /opt/airsim-rf/examples/pluto_esm_drones.py --output-dir /work/pluto_esm
```

## Build locally

```bash
git clone https://github.com/wa200508/airsim-rf.git
cd airsim-rf
docker build -t airsim-rf:test .
docker run --rm --network none airsim-rf:test
```

Builds need internet access to download the exact external source commits and
Python dependencies. Running the tests afterward needs no downloads. An optional
BuildKit secret named `proxy_ca` lets an HTTPS inspection proxy supply its CA
bundle during dependency installation without putting it in the image.

## Automatic publishing

`.github/workflows/container.yml` builds on pull requests, pushes to `main`,
version tags (`v*`), and manual dispatch. It runs offline tests and the radar
example before pushing the same image to GHCR. Pull requests only build and
test. Main publishes `latest` and a commit tag; version tags publish their tag
and a commit tag. Publishing uses the workflow's `GITHUB_TOKEN` with
`packages: write`; no stored registry password is needed.
# Distributed simulation

The same image can run `airsim-rf-worker` and `airsim-rf-coordinator`.
See [DISTRIBUTED.md](DISTRIBUTED.md) for the offline two-worker demonstration,
one-GPU-per-receiver deployment, and the AMS-GRA MEL integration.

<!-- BEGIN SIGNAL TIME CONTEXT -->

**Simulation-time reference:** use **wall seconds per simulated signal second**, not an unlabeled whole-run time. For fixed windows, divide mean service milliseconds by samples/sample-rate × 1,000. Stage costs use their parent window denominator. Geometry-only solves and analytic operation counts have no generated signal duration; a signal-time ratio is **not applicable**, unless an explicit update interval is assumed and labeled as a scheduling estimate. Unrecorded flight costs remain unknown. See [recorded normalized cases](SIGNAL_TIME_RESULTS.md).

<!-- END SIGNAL TIME CONTEXT -->
