#!/usr/bin/env bash
# Build branch harness over the pinned dependency image, then retain results on host.
set -euo pipefail
profile_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$profile_repo_root"
profile_basis=false
profile_e2e=false
profile_gpu_propagation=false
profile_args=()
for profile_arg in "$@"; do
  if [[ "$profile_arg" == --doppler-basis ]]; then profile_basis=true;
  elif [[ "$profile_arg" == --end-to-end ]]; then profile_e2e=true;
  elif [[ "$profile_arg" == --p100-gpu ]]; then profile_gpu_propagation=true;
  else profile_args+=("$profile_arg"); fi
done
if [[ "$profile_basis" == true && "$profile_e2e" == true ]]; then
  echo 'Select either --end-to-end or --doppler-basis.' >&2
  exit 2
fi
if [[ "$profile_gpu_propagation" == true && "$profile_e2e" != true ]]; then
  echo '--p100-gpu requires --end-to-end.' >&2
  exit 2
fi
if [[ "$profile_gpu_propagation" == true ]]; then
  profile_args=(--backend cuda --propagation-backend cuda --pascal-compat "${profile_args[@]}")
fi
for profile_arg in "$@"; do
  if [[ "$profile_arg" == --help || "$profile_arg" == -h ]]; then
    if [[ "$profile_e2e" == true ]]; then python3 scripts/run_end_to_end_profile.py --help;
    elif [[ "$profile_basis" == true ]]; then python3 scripts/run_doppler_basis_profile.py --help;
    else python3 scripts/run_gpu_profile.py --help; fi
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
if [[ "$profile_basis" == true || "$profile_e2e" == true ]]; then profile_build+=(--build-arg PROFILE_BASIS_CUDA=1); fi
if [[ -n "${CODEX_PROXY_CERT:-}" ]]; then
  profile_build+=(--secret "id=proxy_ca,src=$CODEX_PROXY_CERT")
fi
"${profile_build[@]}" .
if [[ "$profile_gpu_propagation" == true ]]; then
  docker build -f Dockerfile.p100-gpu --build-arg "PROFILE_BASE_IMAGE=$profile_image" -t "$profile_image-gpu" .
  profile_image="$profile_image-gpu"
fi
mkdir -p results/profiling
profile_run=(docker run --rm --user "$(id -u):$(id -g)"
  -v "$profile_repo_root/results/profiling:/work/results"
  -e MPLCONFIGDIR=/tmp/matplotlib)
if [[ "$profile_basis" == true || "$profile_e2e" == true ]]; then
  profile_run+=(--entrypoint python -e CUPY_CACHE_DIR=/tmp/cupy-kernel-cache
    -e CUDA_CACHE_PATH=/tmp/cuda-kernel-cache
    -e DRJIT_CACHE_DIR=/tmp/drjit-cache)
  if [[ "$profile_gpu_propagation" == true ]]; then
    profile_run+=(--tmpfs /.drjit:rw,mode=1777)
  else
    profile_run+=(-e DRJIT_LIBCUDA_PATH=/tmp/disabled-drjit-cuda.so)
  fi
fi
profile_cpu_only=false
profile_previous_arg=""
for profile_arg in "$@"; do
  if [[ "$profile_arg" == --cpu-only || "$profile_arg" == --backend=cpu ]]; then profile_cpu_only=true; fi
  if [[ "$profile_arg" == cpu && "$profile_previous_arg" == --backend ]]; then profile_cpu_only=true; fi
  profile_previous_arg="$profile_arg"
done
if [[ "$profile_cpu_only" == true && "$profile_gpu_propagation" == true ]]; then
  echo 'GPU propagation cannot run with --cpu-only or --backend cpu.' >&2
  exit 2
fi
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
if [[ "$profile_e2e" == true ]]; then
  "${profile_run[@]}" "$profile_image" /opt/airsim-rf/scripts/basis_launch.py \
    /opt/airsim-rf/scripts/run_end_to_end_profile.py --output-root /work/results "${profile_args[@]}"
elif [[ "$profile_basis" == true ]]; then
  "${profile_run[@]}" "$profile_image" /opt/airsim-rf/scripts/basis_launch.py \
    /opt/airsim-rf/scripts/run_doppler_basis_profile.py --output-root /work/results "${profile_args[@]}"
else
  "${profile_run[@]}" "$profile_image" --output-root /work/results "${profile_args[@]}"
fi
