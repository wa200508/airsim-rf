#!/usr/bin/env bash
set -euo pipefail
runtime_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$runtime_repo_root"
runtime_source=".deps/ProjectAirSim-runtime"
runtime_revision="$(python3 -c 'import json; print(json.load(open("sources.json"))["projectairsim"]["commit"])')"
if [[ ! -d "$runtime_source/.git" ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/iamaisim/ProjectAirSim.git "$runtime_source"
  git -C "$runtime_source" sparse-checkout set core_sim simserver vehicle_apis physics rendering mavlinkcom thirdparty samples client tools templates
  git -C "$runtime_source" checkout --detach "$runtime_revision"
fi
[[ "$(git -C "$runtime_source" rev-parse HEAD)" == "$runtime_revision" ]] || { echo 'Runtime checkout differs from sources.json' >&2; exit 1; }
docker build -f "$runtime_repo_root/Dockerfile.airsim-runtime" --build-arg BUILD_JOBS="${RF_RUNTIME_BUILD_JOBS:-4}" \
  -t airsim-rf:airsim-runtime "$runtime_source"
