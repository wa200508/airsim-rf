#!/usr/bin/env bash
# Build branch harness over the pinned dependency image, then retain results on host.
set -euo pipefail
profile_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$profile_repo_root"
for profile_arg in "$@"; do
  if [[ "$profile_arg" == --help || "$profile_arg" == -h ]]; then
    python3 scripts/run_gpu_profile.py --help
    exit 0
  fi
done
profile_image="${RF_PROFILE_IMAGE:-airsim-rf:p100-profile}"
profile_revision="$(git rev-parse HEAD)"
profile_dirty=false
if ! git diff --quiet || ! git diff --cached --quiet; then profile_dirty=true; fi
profile_build=(docker build -f Dockerfile.profiling -t "$profile_image"
  --build-arg "PROFILE_SOURCE_REV=$profile_revision"
  --build-arg "PROFILE_SOURCE_DIRTY=$profile_dirty")
if [[ -n "${CODEX_PROXY_CERT:-}" ]]; then
  profile_build+=(--secret "id=proxy_ca,src=$CODEX_PROXY_CERT")
fi
"${profile_build[@]}" .
mkdir -p results/profiling
profile_run=(docker run --rm --user "$(id -u):$(id -g)"
  -v "$profile_repo_root/results/profiling:/work/results"
  -e MPLCONFIGDIR=/tmp/matplotlib)
profile_cpu_only=false
for profile_arg in "$@"; do
  if [[ "$profile_arg" == --cpu-only ]]; then profile_cpu_only=true; fi
done
if [[ "$profile_cpu_only" == false ]]; then
  profile_run+=(--gpus "device=${RF_PROFILE_GPU:-0}"
    -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics -e CUDA_VISIBLE_DEVICES=0)
fi
# Optional host Nsight installation, mounted read-only with its sibling libraries.
profile_nsys="${NSYS_BIN:-}"
if [[ -z "$profile_nsys" ]]; then profile_nsys="$(command -v nsys || true)"; fi
if [[ -n "$profile_nsys" && "$profile_nsys" != /* ]]; then
  profile_nsys="$(command -v "$profile_nsys" || true)"
fi
if [[ -n "$profile_nsys" ]]; then
  profile_nsys="$(readlink -f "$profile_nsys")"
  profile_nsys_root="${NSYS_INSTALL_DIR:-$(dirname "$(dirname "$profile_nsys")")}"
  if [[ "$profile_nsys_root" == / || "$profile_nsys_root" == /usr || "$profile_nsys_root" == /usr/local || "$profile_nsys_root" == /opt ]]; then
    echo 'Set NSYS_INSTALL_DIR to the specific Nsight installation directory; skipping broad host mount.' >&2
  else
    profile_run+=(-v "$profile_nsys_root:$profile_nsys_root:ro" -e "NSYS_BIN=$profile_nsys")
  fi
fi
"${profile_run[@]}" "$profile_image" --output-root /work/results "$@"
