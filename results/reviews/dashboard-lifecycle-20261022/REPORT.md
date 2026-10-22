# Dashboard restart and cleanup regression — 2026-10-22

Two lifecycle defects caused failures on reopening the dashboard:

- `dashboard_scenario.prepare()` reused `bundle`, but the generic geometry
  exporter intentionally calls `mkdir(..., exist_ok=False)`. A second preparation
  failed on existing files even after every container had exited.
- SIGTERM/SIGHUP handling did not cover bootstrap. Temporary Docker preparation
  processes were also outside the service-process cleanup list. A terminated
  startup could leave containers or a private network behind.

Preparation now exports into a fresh staging directory and replaces only the
generated bundle after a successful export. An old partial bundle is replaced
on the next preparation; logs and recorded data are retained. The generic
geometry exporter's fresh-directory contract remains unchanged.

The host installs shutdown handling before bootstrap, cancels active Docker
commands, removes owned preparation/probe and service containers, reaps their
client processes and removes the private network. A run-directory filesystem
lock prevents concurrent preparation. Run-scoped Docker labels allow a future
launcher holding that lock to recover leftovers after an untrappable SIGKILL.
Cleanup never performs global Docker pruning. The HTTP port is reserved by the
host before bootstrap, and the Prepare services action no longer rejects that
same listener as a port conflict.

Validation:

- Full CPU suite: **293 passed, 168 skipped**, plus three signal subtests. Skips
  cover unavailable optional backends/dependencies, including GPU hardware.
- Host subprocess regressions cover SIGINT, SIGTERM and SIGHUP during bootstrap,
  startup exceptions, termination during the Prepare worker, process cancellation
  and reaping, lock release, HTTP socket release and cleanup-command failures.
- The standalone Bash extraction path is interrupted during `docker cp`; its
  active client is reaped and its named source container is removed.
- [Real Docker lifecycle results](lifecycle-check.json): repeated scene export
  in one directory; three running CPU service stand-ins plus an active probe;
  cancellation and cleanup; no owned containers/networks left; reopen and export
  again; label-scoped recovery of injected stale resources; preserved recording.
- Documentation links, shell syntax and whitespace checks passed.

The Docker check used the managed rootful daemon with `vfs`, a local CPU runtime
image overlaid with the current scenario source, and the small Python Alpine
image for service stand-ins. It is not a full RF/GPU mission or a new rootless GPU
qualification. CI runs the same lifecycle check with its freshly built CPU image
before publishing dashboard images.

Reproduce with a published image containing the fix:

```bash
python3 scripts/qualify_dashboard_lifecycle.py \
  --image ghcr.io/wa200508/airsim-rf:dashboard-gpu \
  --report results/local-dashboard-lifecycle.json
```

The script uses the selected Docker context and only its own temporary files and
resources. It does not require a GPU or change the daemon configuration.
