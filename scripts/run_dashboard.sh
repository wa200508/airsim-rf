#!/usr/bin/env bash
# Standalone host launcher: pull the RF image and extract its stdlib UI launcher.
# The launcher pulls/inspects all three images, starts them concurrently and
# requires a live simulator, GPU/OptiX/CuPy probe, camera and skill before the UI.
set -euo pipefail
if [[ -n "${RF_DASHBOARD_PYTHON:-}" ]]; then
  rf_dashboard_python=$(command -v "$RF_DASHBOARD_PYTHON") || {
    echo "RF_DASHBOARD_PYTHON is not executable: $RF_DASHBOARD_PYTHON" >&2; exit 1;
  }
elif [[ -n "${VIRTUAL_ENV:-}" ]]; then
  rf_dashboard_python="$VIRTUAL_ENV/bin/python"
  if [[ ! -x "$rf_dashboard_python" ]]; then
    echo "Active virtual environment has no executable Python: $rf_dashboard_python" >&2
    exit 1
  fi
else
  rf_dashboard_python=$(command -v python3) || {
    echo 'Python 3.10+ is required; activate a virtual environment or set RF_DASHBOARD_PYTHON.' >&2; exit 1;
  }
fi
"$rf_dashboard_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Dashboard launcher requires Python 3.10+")'
printf 'Dashboard host Python: %s\n' "$rf_dashboard_python"
rf_dashboard_image="${RF_DASHBOARD_IMAGE:-ghcr.io/wa200508/airsim-rf:dashboard-gpu}"
# Prefer updated checkout code so a launcher-only fix does not wait for image publication.
rf_dashboard_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$rf_dashboard_repo/src/airsim_rf/dashboard.py" && -f "$rf_dashboard_repo/scripts/launch_dashboard.py" ]]; then
  exec "$rf_dashboard_python" "$rf_dashboard_repo/scripts/launch_dashboard.py" --pascal-compat --rf-image "$rf_dashboard_image" "$@"
fi
rf_dashboard_cache="${XDG_CACHE_HOME:-$HOME/.cache}/airsim-rf-dashboard"
mkdir -p "$rf_dashboard_cache"
for rf_dashboard_argument in "$@"; do
  if [[ "$rf_dashboard_argument" == --replay && -f "$rf_dashboard_cache/dashboard.py" && -f "$rf_dashboard_cache/dashboard_recording.py" && -f "$rf_dashboard_cache/source_recording.py" ]]; then
    exec "$rf_dashboard_python" "$rf_dashboard_cache/dashboard.py" "$@"
  fi
done
command -v docker >/dev/null
# Keep the source container identifiable even if interrupted before `create`
# returns. A background child plus wait lets Bash handle TERM/HUP immediately.
rf_dashboard_source="airsim-rf-dashboard-source-${UID}-$$-${RANDOM}"
rf_dashboard_child=''
rf_dashboard_cleanup() {
  if [[ -n "$rf_dashboard_child" ]]; then
    kill "$rf_dashboard_child" 2>/dev/null || true
    wait "$rf_dashboard_child" 2>/dev/null || true
    rf_dashboard_child=''
  fi
  docker rm -f "$rf_dashboard_source" >/dev/null 2>&1 || true
}
rf_dashboard_docker() {
  docker "$@" &
  rf_dashboard_child=$!
  local rf_dashboard_status=0
  wait "$rf_dashboard_child" || rf_dashboard_status=$?
  rf_dashboard_child=''
  return "$rf_dashboard_status"
}
trap rf_dashboard_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
rf_dashboard_docker pull "$rf_dashboard_image"
rf_dashboard_docker create --name "$rf_dashboard_source" --entrypoint python "$rf_dashboard_image" -c pass
rf_dashboard_docker cp "$rf_dashboard_source:/opt/airsim-rf/src/airsim_rf/dashboard.py" "$rf_dashboard_cache/dashboard.py"
rf_dashboard_docker cp "$rf_dashboard_source:/opt/airsim-rf/src/airsim_rf/dashboard_recording.py" "$rf_dashboard_cache/dashboard_recording.py"
rf_dashboard_docker cp "$rf_dashboard_source:/opt/airsim-rf/src/airsim_rf/source_recording.py" "$rf_dashboard_cache/source_recording.py"
rf_dashboard_docker cp "$rf_dashboard_source:/opt/airsim-rf/src/airsim_rf/dashboard_static" "$rf_dashboard_cache/"
rf_dashboard_cleanup
trap - EXIT INT TERM HUP
exec "$rf_dashboard_python" "$rf_dashboard_cache/dashboard.py" --pascal-compat --rf-image "$rf_dashboard_image" "$@"
