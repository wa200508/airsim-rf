# Rootless dashboard infrastructure qualification — 2026-10-22

A real rootless Docker daemon reproduced the old bind-mount permission failure
and passed the corrected UID mapping and network tests. The test used a private
0700 host directory, with no chmod-777 workaround.

| Check | Result |
| --- | --- |
| Passing host UID 1000 as the container UID | PermissionError reproduced |
| Namespace UID 0 can read and update the host marker | Passed |
| Host can read the result and retains UID 1000 ownership | Passed |
| Simulator stand-in runs as non-root namespace UID 10001 | Passed |
| Separate containers communicate by private bridge/DNS alias | Passed |
| Host reaches the service through loopback port publishing | Passed |

Reproduce on an existing rootless context with
`sh scripts/check_rootless_dashboard.sh`. The diagnostic starts only temporary
CPU test containers and a task-owned network, then removes them. No GPU or
daemon reconfiguration is needed. The production launcher separately checks
shared-directory access, GPU passthrough, OptiX, real scene I/Q, camera and skill
readiness before allowing a mission.

This was an isolated Docker-in-Docker test lab. Its outer provisioning container
needed privileges for nested user namespaces/TUN; the rootless daemon itself ran
as user 1000 and the diagnostic service containers used no privilege flags.
This is not a full NVIDIA/rootless dashboard mission qualification: no GPU is
available in this workspace. Actual GPU/driver/runtime compatibility is checked
on the user's host at launch, with explicit failures and no CPU fallback.

[Environment and source hashes](environment.json). [Diagnostic output](smoke.log).
