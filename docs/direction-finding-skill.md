# Direction Finding RF Skill is a separate project

The receiver application is maintained in **[wa200508/DF-Skill](https://github.com/wa200508/DF-Skill)**.
Its product name is **Direction Finding RF Skill**. It currently uses MUSIC for
direction-of-arrival estimation; that algorithm name remains in scientific
documentation and the existing `music_db` observer field.

## Repository ownership

| Repository | Owns |
|---|---|
| airsim-rf | Scenario inputs, AirSim/Sionna acquisition, propagation/rendering, receiver front-end simulation, source sample archive and dashboard observer |
| DF-Skill | Receive-only direction finding application, numerical estimator, receiver I/Q adapter, HTTP/results/status interfaces, tests, container build and publication |

No live receiver algorithm is implemented in this repository's `skills/music.py`
or `processing/music.py`. Those files are legacy import/CLI re-exports of the
external package. Offline tracking examples retain their own orchestration;
their direction-finding estimates come from DF-Skill.

The default scenario selects `kind: direction-finding`, an immutable external
image and `revision_policy: independent`. Simulator/RF image revisions still
must match. The old `music` kind remains a schema alias for saved/copied inputs.

## Reproduce this integration

Pinned DF-Skill source: [5e2420aa0c2bf49563db3f83fceda1e874fd2029](https://github.com/wa200508/DF-Skill/tree/5e2420aa0c2bf49563db3f83fceda1e874fd2029).

```text
ghcr.io/wa200508/df-skill:sha-5e2420aa0c2bf49563db3f83fceda1e874fd2029
```

The package pin lives in `requirements-df-skill.txt`; the scenario's consumer
image lives with the scenario in `scenarios/drone-orbit/scenario.json`.
The optional `tracking` extra installs the external package for legacy offline
analysis. CPU container tests install that package without its optional DSP
dependencies; full dashboard/analysis environments retain their qualified locks.

`Dockerfile.dashboard --target skill` is a compatibility alias of the pinned
external image, not another copy of the receiver implementation. The legacy
`airsim-rf:dashboard-skill` publication tag remains an alias for existing users.
The canonical image and its tests/build are owned by DF-Skill.

The skill receives only read-only receiver geometry/calibration and post-ADC
samples, plus its own result output directory. It cannot read scenario input,
transmitter waveform, path data or truth. The acquisition producer does not
inspect or import the direction finding algorithm.

## Saved samples and GNU Radio

The bulk I/Q layout and sample stream are unchanged. Existing recordings can
be replayed into DF-Skill, or opened with their GNU Radio graphs.
For replay inside the external consumer image, use:

```bash
python -m df_skill.sample_recording replay /path/to/iq --host df-skill --port 8811
```

Host-side `python -m airsim_rf.sample_recording` remains available. Start a fresh
consumer/results directory per experiment. See [I/Q replay](iq-replay.md) and
[GNU Radio development](gnuradio.md).

## License

DF-Skill is **Apache License 2.0**, matching the starter kit's public RF skill:
[upstream RF FM Demod LICENSE](https://gitlab.com/open-arsenal/ams-gra/hello-world-sk/skills/rf-fm-demod/-/blob/main/LICENSE).
The public skills group currently lists RF FM Demod and IR Search and Track;
no separate ESM-named public project was found during verification.

The new repo retains original MIT attribution for transferred airsim-rf code,
and the Apache upstream Squall protocol notices. It does not claim Government
authorship. airsim-rf itself remains MIT licensed. No new native AMS-GRA
MEL/VITA/UCI conformance or hardware performance claim follows from this move.

## Existing copied scenarios

Saved GUI recordings still replay as before. When adopting the new external
consumer in an older copied scenario, set its `skill.kind` to
`direction-finding`, `skill.image` to the pinned image above, and
`skill.revision_policy` to `independent`. An explicit old `matching` policy
is not silently relaxed: it would incorrectly require independent repositories
to have the same Git commit. Simulator/RF revision matching is always retained.

## Skill-owned dashboard display

The skill's `display.py` defines its plots, labels, units, selectors and metric
bindings. `GET /display` exposes the description, and every timestamped result
carries it for synchronized live display and playback. See the
[RF Skill Display contract](skill-display.md) for extension instructions and the
[JSON schema](schemas/rf-skill-display-v1.schema.json). The dashboard's generic
renderer is `src/airsim_rf/dashboard_static/skill-display.js`; the observer replay
projection is `src/airsim_rf/skill_display.py`. Neither source nor simulator
selects a receiver algorithm or interprets its live result fields.
