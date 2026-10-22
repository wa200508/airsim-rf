#!/bin/sh
# Verify the dashboard's mount and network assumptions on the selected rootless daemon.
# No daemon reconfiguration, sudo, privilege flags or NVIDIA hardware are needed.
set -eu
rootless_security=$(docker info --format '{{json .SecurityOptions}}')
case "$rootless_security" in *rootless*) ;; *) echo 'Select your rootless Docker context first.' >&2; exit 2;; esac
rootless_work=$(mktemp -d)
rootless_name="airsim-rf-check-$(basename "$rootless_work" | tr '.' '-')"
rootless_image="${RF_ROOTLESS_TEST_IMAGE:-python:3.12-alpine}"
cleanup() {
  docker rm -f "$rootless_name-server" >/dev/null 2>&1 || true
  docker network rm "$rootless_name" >/dev/null 2>&1 || true
  rm -rf "$rootless_work"
}
trap cleanup EXIT INT TERM
printf 'host-wrote' > "$rootless_work/marker"
# Reproduce the old incorrect host-UID mapping, then require the correct mapping.
rootless_wrong_uid=$(id -u)
if [ "$rootless_wrong_uid" = 0 ]; then rootless_wrong_uid=1000; fi
if docker run --rm --network none --user "$rootless_wrong_uid:$rootless_wrong_uid" \
    -v "$rootless_work:/run" "$rootless_image" python -c \
    'from pathlib import Path; Path("/run/marker").write_text("wrong-user")' > "$rootless_work/wrong-uid.log" 2>&1; then
  echo 'Expected the private directory to reject the old UID mapping.' >&2; exit 1
fi
if ! grep -q PermissionError "$rootless_work/wrong-uid.log"; then
  cat "$rootless_work/wrong-uid.log" >&2; exit 1
fi
docker run --rm --network none --user 0:0 -v "$rootless_work:/run" "$rootless_image" python -c \
  'from pathlib import Path; p=Path("/run/marker"); assert p.read_text()=="host-wrote"; p.write_text("container-wrote")'
[ "$(cat "$rootless_work/marker")" = container-wrote ]
[ "$(stat -c %u "$rootless_work/marker")" = "$(id -u)" ]
docker network create "$rootless_name" >/dev/null
docker run -d --rm --name "$rootless_name-server" --network "$rootless_name" \
  --network-alias projectairsim --user 10001:10001 -p 127.0.0.1::9090 \
  "$rootless_image" python -m http.server 9090 >/dev/null
docker run --rm --network "$rootless_name" --user 0:0 "$rootless_image" python -c '
import time,urllib.request
for i in range(50):
 try:
  response=urllib.request.urlopen("http://projectairsim:9090/",timeout=2)
  assert response.status==200
  break
 except OSError:time.sleep(.1)
else:raise SystemExit("Rootless service DNS/bridge failed")'
rootless_address=$(docker port "$rootless_name-server" 9090/tcp)
if command -v curl >/dev/null; then
  curl --noproxy '*' -fsS --max-time 5 "http://$rootless_address/" >/dev/null
else
  if wget --help 2>&1 | grep -q 'BusyBox'; then
    wget -Y off -q -T 5 -O /dev/null "http://$rootless_address/"
  else
    wget --no-proxy -q -T 5 -O /dev/null "http://$rootless_address/"
  fi
fi
printf 'PASS: real rootless host/container writes, host UID ownership, non-root service, private DNS/bridge and loopback port publication. GPU not exercised.\n'
