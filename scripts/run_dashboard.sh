#!/usr/bin/env bash
# Standalone host launcher: pull the RF image and extract its stdlib UI launcher.
# The launcher pulls/inspects all three images, starts them concurrently and
# requires a live simulator, GPU/OptiX/CuPy probe, camera and skill before the UI.
set -euo pipefail
command -v docker >/dev/null
command -v python3 >/dev/null
rf_dashboard_image="${RF_DASHBOARD_IMAGE:-ghcr.io/wa200508/airsim-rf:dashboard-gpu}"
rf_dashboard_cache="${XDG_CACHE_HOME:-$HOME/.cache}/airsim-rf-dashboard"
mkdir -p "$rf_dashboard_cache"
docker pull "$rf_dashboard_image"
rf_dashboard_source=$(docker create --entrypoint python "$rf_dashboard_image" -c pass)
trap 'docker rm -f "$rf_dashboard_source" >/dev/null' EXIT
docker cp "$rf_dashboard_source:/opt/airsim-rf/src/airsim_rf/dashboard.py" "$rf_dashboard_cache/dashboard.py"
docker cp "$rf_dashboard_source:/opt/airsim-rf/src/airsim_rf/dashboard_static" "$rf_dashboard_cache/"
docker rm "$rf_dashboard_source" >/dev/null
trap - EXIT
exec python3 "$rf_dashboard_cache/dashboard.py" --pascal-compat --rf-image "$rf_dashboard_image" "$@"
