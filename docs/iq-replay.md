[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Capture once, develop RF skills without rerunning the simulation

Dashboard runs save the **exact complex float32 voltages sent to the RF
skill**, after propagation and receiver noise, gain, filtering and ADC modeling.

For the default radar demo, the saved stream contains **target scattering +
terrain clutter + receiver noise**, combined before ADC modeling. Noise is
currently enabled with `radios.radar.profile.noise_power_offset_db: -25`; it is
reduced for visibility, not omitted. Set the offset to `0` for the modeled
thermal-noise baseline. Disabling noise or clutter in a scenario changes future
captures, not data already saved.

The range–Doppler dropdown changes **color limits only**. Its narrow, medium
and wide scales all display the same combined receiver data; it does not select
noise-only, clutter-only or target-only recordings. Older displays call the
first two presets "Noise detail" and "Strong echoes" with the same behavior.
The standard `iq/` capture does not save separate component streams. Isolated
clutter/noise comparisons in the benchmark reports are separate controlled
experiments, not selectable layers of a normal mission archive.

The archive preserves every sample, inter-channel phase, amplitude, acquisition
timestamp, sample rate, carrier, clipping fraction and coherent window boundary.
Doppler and multipath evolution are already present in those samples. Replay
does not reconstruct a channel or substitute a new waveform.

This is separate from dashboard **video/diagnostic playback**. Old dashboard
recordings did not retain bulk samples; their waterfall cannot recover the I/Q.

For a GNU Radio "insert signal processing here" workspace, use the independent
[RF Skill Harness](https://github.com/wa200508/RF-Skill-Harness). It consumes the
complete `iq/` folder, preserves coherent channel samples and acquisition tags,
and supplies the captured receiver metadata to your processing hook. Its RF
acquisition timeline is constructed automatically for receive windows and
configured radar TX/ADC timing. No simulation or previous RF skill is required.

## Where the data goes

Bulk capture is enabled by default. Set `mission.record_iq: false` in your
[scenario package](scenarios.md) to disable it. Each new run writes:

```text
recordings/dashboard/replays/<run-id>/
  definition/                  frozen scenario inputs, for reproduction/evaluation
  iq/                          share this directory with skill developers
    manifest.json              format, status, channels, totals and sample format
    receiver-config.json       sample rate/carrier, array geometry and calibration
    windows.jsonl              acquisition timestamps, offsets, clipping, SHA-256
    site0_e0.sigmf-data         exact little-endian complex float32 volts
    site0_e0.sigmf-meta         standard SigMF datatype/rate/capture offsets/carrier
    ...                        one data/metadata pair for every array element
    view.grc                   GNU Radio Companion viewer with channel dropdown
    replay.grc                 stock-block coherent DSP starter flowgraph
  frames/ camera/ results/     source telemetry, video and original skill outputs
```

Copy **the complete `iq/` directory**, including the journal and configuration.
It contains no emitter waveforms, scenario/flight definition, source truth,
ray paths or original algorithm results. The recording adapter also accepts
hardware-facing `SampleBlock` data: it has no simulator or algorithm imports.
The wider mission archive retains the scenario snapshot separately for
controlled reproduction and evaluation.

Data is `cf32_le`: four bytes each for I and Q, **eight bytes per complex
sample per channel**. There is no normalization, decimation or additional lossy
quantization. Two four-element arrays at 2 MS/s require 128 MB/s of simulated
signal time: 15.36 GB for 120 seconds, 76.8 GB for ten minutes, plus metadata
and video. One 2 MS/s channel requires 16 MB/s. Count antenna channels, not
receiver sites. Disk writes take wall time and can limit a fast simulation;
the producer reports cumulative `iq_recording_wall_s` and `iq_recording_bytes`.
Preparation checks space for the rounded mission length plus 64 MiB headroom.
Space is not reserved; other processes can still fill the disk during a run.

The source appends each complete channel group before sending it to the live
consumer. An archive can include a generated group whose live consumer later
failed to acknowledge it. This records acquisition independently of whether
an algorithm processed it. The prepared T+0 group is recorded once and reused
when Launch mission is pressed.

## Inspect and replay into the existing skill

No GPU, AirSim server or Sionna scene is involved. In a checkout, a light Python
environment needs only NumPy for archive reading/replay:

```bash
python3 -m venv .venv-replay
source .venv-replay/bin/activate
python -m pip install numpy
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
iq_dir="$PWD/recordings/dashboard/replays/<run-id>/iq"
python -m airsim_rf.sample_recording inspect "$iq_dir" --verify
```

Start your RF skill with `iq/receiver-config.json` and a **fresh results
directory**, then feed its existing TCP v2 ingress:

```bash
# Your skill listens on localhost:8811 using the same ingress as live acquisition.
python -m airsim_rf.sample_recording replay "$iq_dir" --port 8811
# Original sample-time delivery pace, or twice that pace:
python -m airsim_rf.sample_recording replay "$iq_dir" --port 8811 --speed 1
python -m airsim_rf.sample_recording replay "$iq_dir" --port 8811 --speed 2
# A window subset: inclusive start, exclusive stop.
python -m airsim_rf.sample_recording replay "$iq_dir" --start-window 10 --stop-window 30
```

Run each command as a separate experiment with a fresh skill process/output
directory. Default `--speed 0` sends as fast as the consumer acknowledges.
Positive speeds set a maximum delivery pace; a slow consumer applies
backpressure and stretches wall time. **Samples and timestamps stay unchanged**
at every speed. No samples are dropped to catch up. Subsets retain their
original timestamps and sample values; TCP sample offsets begin at zero for
the new session. Seeking does not recreate algorithm state accumulated before
the selected interval, so include warm-up windows for stateful algorithms.

### All-container example: Direction Finding RF Skill plus replay source

The independent skill image also contains the source-neutral archive tool.
These two containers use no GPU and mount only receiver/sample data.
Set `iq_dir` to an absolute existing archive path in each terminal:

```bash
image=ghcr.io/wa200508/df-skill:sha-5e2420aa0c2bf49563db3f83fceda1e874fd2029
docker pull "$image"
docker network create rf-offline
# Run in one terminal. HTTP diagnostics are available on the host at :18812.
docker run --rm --name music-offline --network rf-offline \
  -p 127.0.0.1:18812:8812 \
  --mount "type=bind,src=$iq_dir/receiver-config.json,dst=/config/arrays.json,readonly" \
  "$image" --arrays /config/arrays.json --results-dir /tmp/offline-results
```

In another terminal, after the skill reports ingress ready:

```bash
# Set the same image and iq_dir values in this terminal.
docker run --rm --network rf-offline --entrypoint python \
  --mount "type=bind,src=$iq_dir,dst=/iq,readonly" \
  "$image" -m df_skill.sample_recording replay /iq --host music-offline
docker cp music-offline:/tmp/offline-results ./music-offline-results
# Stop the skill with Ctrl-C, then remove the private test network:
docker network rm rf-offline
```

No host networking or privileged mode is needed, including on rootless Docker.
Copy results out before stopping the `--rm` container. Choose a new host
results path for each experiment. For a custom consumer, use its image/arguments
and set `--port` to its declared I/Q ingress port. This is the project's
[TCP v2 contract](reference/iq-stream.md); a generic GNU Radio TCP source/sink does not
automatically implement its framing and acknowledgements.

## Python and other SDR development options

**For GNU Radio development, start with the generated `view.grc` or
`replay.grc` beside the saved samples.** See [the GNU Radio guide](gnuradio.md)
for opening, editing and native replay. No sample conversion is necessary.

| Option | Good fit | Relationship to this project |
|---|---|---|
| Native TCP v2 replay | Integration tests of a complete existing RF skill | Implemented here; same ingress as live acquisition, including window acknowledgements |
| Python block reader / NumPy memory mapping | Unit tests, notebooks, new DSP algorithms, deterministic regressions | Implemented block reader; raw channel files also open directly with NumPy |
| GNU Radio File Source or `gr-sigmf` | Develop a flowgraph from recorded samples, then replace its source with hardware | Standard `cf32_le` data is directly usable; synchronize channel offsets and retain journal timing when adapting into our contract |
| IQEngine / inspectrum | Inspect spectrum, phase, modulation and difficult signal intervals | SigMF viewers/analysis tools; not substitutes for skill transport or multi-array synchronization |
| MIT Haystack Digital RF | Large time-indexed datasets, HDF5 archives, Python/MATLAB/GNU Radio workflows | Alternative archive ecosystem; an export/reader adapter would be needed here |
| UHD/RFNoC Replay | Later tests through supported physical USRP hardware using onboard DRAM | Hardware replay, with device-format conversion and scaling; not required for offline skill development |

Use the channel-coherent reader for MUSIC or another array algorithm:

```python
from airsim_rf.sample_recording import iter_recorded_windows
import numpy as np

for blocks in iter_recorded_windows("saved-iq"):
    channels = {block.receiver: block for block in blocks}
    # Choose one site's channels using receiver-config.json.
    matrix = np.stack([channels[f"site0_e{i}"].samples for i in range(4)])
    # Pass matrix and neutral acquisition metadata to your DSP implementation.
```

For direct random access to one raw channel:

```python
samples = np.memmap("saved-iq/site0_e0.sigmf-data", dtype="<c8", mode="r")
chunk = samples[100_000:120_000]
```

The raw file has no header. Preserve its SigMF sidecar and journal for rate,
carrier, amplitude units and cross-channel timing. MATLAB can read the same
interleaved float32 pairs with `fread`; no simulator adapter is needed.
Changing flight, source waveforms, receiver hardware parameters or propagation
requires a new simulation; changing the downstream RF skill does not.

## Integrity and interrupted runs

`inspect --verify` reads all samples and checks their per-window SHA-256 values.
Replay checks each selected window's hashes, byte counts, channel layout and
continuity before sending it. Memory is bounded by a coherent window rather
than the full recording. Closed `complete` and deliberately `stopped` archives
can be replayed normally.

An interrupted/failed archive requires `--allow-partial`; only its published
prefix is used, and trailing unpublished bytes are ignored. Do not read an
actively changing archive: stop the source or copy a stable snapshot first.
Writes are flushed per window but not `fsync`ed. This supports process failure
diagnosis, not guaranteed power-loss recovery. Corrupt or truncated published
data fails closed; it is never silently replaced with zeros.

## Sources and scope

- [SigMF specification v1.2.6](https://sigmf.org/): open sample/metadata format;
  our per-channel files use its `cf32_le` datatype. Coherent acquisition timing
  is in the adjacent project journal, not assumed to be understood by viewers.
- [GNU Radio File Source](https://wiki.gnuradio.org/index.php/File_Source) and
  [SkySafe gr-sigmf](https://github.com/skysafe/gr-sigmf): file-fed flowgraphs,
  SigMF read/write blocks, and the separate `sigmf-play` hardware utility.
- [IQEngine](https://github.com/IQEngine/IQEngine) and
  [inspectrum](https://github.com/miek/inspectrum): open RF-recording inspection
  tools with SigMF support.
- [MIT Haystack Digital RF](https://github.com/MITHaystack/digital_rf): RF HDF5
  data/metadata libraries and GNU Radio integration.
- [Ettus RFNoC Replay application note](https://kb.ettus.com/Using_the_RFNoC_Replay_Block_in_UHD_4):
  device-DRAM recording/playback and supported UHD/USRP requirements.

The archive reader, TCP replay, unchanged MUSIC consumer and generated
stock-block GNU Radio graphs have integration tests. Digital RF, third-party
viewers and physical USRP replay remain documented options, without integration
qualification here.
See [the qualification report](../results/reviews/iq-replay-20261023/REPORT.md)
for exact-sample, real CPU-propagation and standalone-consumer evidence.

The radar scenario uses the same lossless cf32/SigMF archive, with
`receiver-config.json.acquisition` describing its chirp/ADC gates. Its voltages
are bias-subtracted **ADC volts**, after modeled IF gain, rather than SDR
input-referred volts. Zero-filled gate gaps retain their actual acquisition-clock
positions; remove/select them using that timing when developing radar processing.
See the [radar scenario guide](../scenarios/mmwave-radar/README.md).

For the standalone radar skill, replay needs no airsim-rf installation:

```bash
python -m radar_skill.sample_recording replay /path/to/iq --host 127.0.0.1 --port 8811
```

Start a fresh [Radar-skill](https://github.com/wa200508/Radar-skill) consumer with
`--replay` (no radio-control traffic) and
that archive's receiver configuration and a separate results directory first.
