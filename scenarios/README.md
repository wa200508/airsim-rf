# Scenario catalog

Only scenario inputs and their documentation live here. Containers, acquisition
code and RF algorithms live outside this directory. Each child is a complete,
copyable input package; no assets are resolved through another scenario.

| Select with `--scenario` | Scenario | Receiver application |
|---|---|---|
| `drone-orbit` | [Current direction-finding example](drone-orbit/README.md): 915 MHz QPSK emitter flying over two fixed arrays | [Direction Finding RF Skill](https://github.com/wa200508/DF-Skill), MUSIC |
| `mmwave-radar` | [77 GHz FMCW radar](mmwave-radar/README.md): flying racetrack radar observing three stationary ground targets with varied locations, sizes and RCS, with terrain masking | Independent CPU FMCW range/Doppler skill |

```bash
python3 scripts/launch_dashboard.py --list-scenarios
bash scripts/run_dashboard.sh --scenario drone-orbit --open
bash scripts/run_dashboard.sh --scenario mmwave-radar --open
```

The dashboard also has a **Scenario** selector. Stop the current mission before
changing scenarios. Selection pulls/verifies the appropriate images and prepares
all services again; Launch mission remains disabled until the actual initial
I/Q window has been processed. Saved runs retain their original frozen inputs.

To make another scenario, copy a whole child directory and pass its path:

```bash
cp -r scenarios/mmwave-radar ~/my-radar
python3 scripts/launch_dashboard.py --scenario ~/my-radar --check-scenario
bash scripts/run_dashboard.sh --scenario ~/my-radar --open
```

A new child containing a `scenario.json` appears automatically in a checkout's
catalog. The wheel and published images ship the two maintained packages; add
new package data entries when publishing additional examples. See the
[scenario schema guide](../docs/scenarios.md).
