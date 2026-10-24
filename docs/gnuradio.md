[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Develop from saved I/Q in GNU Radio

New dashboard captures are saved directly in **GNU Radio Complex File Source
format**: little-endian float32 I, float32 Q, repeated, eight bytes per complex
sample. Each antenna element has its own headerless `.sigmf-data` file and a
SigMF JSON sidecar describing sample rate and carrier. No format conversion,
extra quantization or custom GNU Radio source block is needed.

At the end of a captured mission, its `iq/` directory also contains two editable
GNU Radio Companion starter graphs:

- **`view.grc`**: a spectrum viewer with an antenna-channel dropdown.
- **`replay.grc`**: a headless DSP starter with every channel exposed and
  connected to a named Null Sink. Replace those sinks with your own processing.

The graphs are generated for the recording's actual channels, sample count,
sample rate and carrier. They reference the existing sample files and do not
duplicate bulk data. Copying the entire `iq/` directory is enough; neither the
project's Python package nor its containers are needed to run the graphs.

## Open a capture

Install GNU Radio 3.10 with GNU Radio Companion. On Debian/Ubuntu:

```bash
sudo apt-get install gnuradio
cd /path/to/recordings/dashboard/replays/<run-id>/iq
gnuradio-companion view.grc
```

Press **Execute**. Choose an antenna element in the dropdown to see its
spectrum. The plot's frequency axis uses the saved carrier and sample rate.
Its FFT display is a development view, not a calibrated dBm/Hz instrument.

To build your algorithm, open `replay.grc`, use **Save As** for your working
flowgraph and connect your DSP to the `coherent_split` outputs. Channel IDs
appear in the source and sink names. `receiver-config.json` supplies antenna
geometry and complex calibration for array processing. Sources deliver the
saved post-ADC **complex volts** without changing their amplitude or phase.

For example, connect the four outputs named `site0_e0` through `site0_e3` to
your site's array processor, keeping that order. Substitute your configured
channel names for other scenarios.

Start Companion from the capture directory as above. Alternatively change the
graph's `recording_dir` parameter to the archive's current absolute path. No
container-only `/run/...` paths are embedded in a recording.

## Playback controls and alignment

Each graph has ordinary editable parameters:

| Parameter | Meaning |
|---|---|
| `recording_dir` | Directory containing the `.sigmf-data` files; default `.` |
| `start_sample` | Common sample offset for **every** antenna channel; default 0, must be below `sample_count` |
| `playback_speed` | Positive wall-time pacing multiplier; default 1 |
| `samp_rate` | Recorded physical sample rate; keep this unchanged when changing playback speed |
| `carrier_hz` | Recorded center frequency |
| `sample_count` | Published samples per channel; excludes any unpublished tail from a failed write |

The topology is stock blocks:

```text
one Complex File Source per channel
              ↓
Streams to Vector (all channels at the same sample index)
              ↓
one Throttle (vector size = number of channels)
              ↓
Vector to Streams → your per-channel or array DSP
```

There is one shared pacer rather than separate per-channel throttles. Every
source uses the same offset and length, with **Repeat disabled**. EOF ends the
headless graph. Starting at a different offset applies to all channels together;
it preserves their relative phase and sample alignment. Stateful algorithms
may need preceding samples as a warm-up interval.

Change `playback_speed` to accelerate development without resampling. For a
maximum-throughput headless experiment, bypass the shared Throttle in Companion.
Sample-index time remains `sample_index / samp_rate`; wall-clock pacing does
not alter the Doppler or modulation encoded in the samples.

The stock File Source does **not** create `rx_time`, `rx_freq`, `rx_rate` or
per-window tags from the adjacent JSON files. The exact original acquisition
timestamps and window boundaries remain in `windows.jsonl`; geometry and
calibration remain in `receiver-config.json`. Algorithms that require tagged
hardware timestamps need a tag adapter. Do not treat the GNU Radio scheduler's
wall clock as acquisition time. The project's [TCP replay](iq-replay.md)
preserves acquisition metadata when testing an unchanged RF skill.

## Run without Companion's GUI

Use the Python supplied with your GNU Radio installation, commonly
`/usr/bin/python3` on Debian/Ubuntu. A different virtual environment may not
have GNU Radio's Python bindings.

```bash
cd /path/to/iq
grcc -o . replay.grc
/usr/bin/python3 iq_replay.py --recording-dir "$PWD" --playback-speed 10
```

This default graph drains to Null Sinks. Add your processing to the `.grc`
file and regenerate its Python when ready. The generated program has no
AirSim, Sionna, project-specific source-block or GPU dependency.

## Existing captures and integrity

For an existing bulk `iq/` archive made before automatic graph generation, add
the starter graphs without copying its samples:

```bash
# From a project checkout, using a Python environment with NumPy:
PYTHONPATH=src python -m airsim_rf.sample_recording gnuradio /path/to/iq
PYTHONPATH=src python -m airsim_rf.sample_recording inspect /path/to/iq --verify
```

Regeneration replaces `replay.grc` and `view.grc`; keep your edited algorithm in
a separately named flowgraph. GUI-only recordings without raw I/Q cannot be
converted into sample captures.

Stock File Sources read bytes directly and do not check the journal's hashes.
Verify a shared dataset with `inspect --verify` before development. An
interrupted archive requires explicit `--allow-partial` when regenerating its
graphs; their common length limits playback to the published coherent prefix.
Use a stable, closed archive rather than an actively changing recording.

## References and validation

- [GNU Radio Complex File Source definition](https://github.com/gnuradio/gnuradio/blob/maint-3.10/gr-blocks/grc/blocks_file_source.block.yml):
  complex item size, common offset/length and repeat settings.
- [Streams to Vector](https://github.com/gnuradio/gnuradio/blob/maint-3.10/gr-blocks/grc/blocks_streams_to_vector.block.yml)
  and [Throttle](https://github.com/gnuradio/gnuradio/blob/maint-3.10/gr-blocks/grc/blocks_throttle.block.yml):
  standard channel grouping and one shared vector-rate limiter.
- [SigMF specification](https://sigmf.org/): the same bytes are represented by
  `cf32_le`, so other SigMF tools can also consume the channel files.

Native tests compile both graphs with `grcc`, compare every played sample with
the original input after relocating the archive, verify a common nonzero seek,
run the generated headless command to EOF, and open the Qt viewer offscreen
while checking channel selection. No physical SDR or new GPU flight performance
claim is made by that interoperability test.
See [the native qualification report](../results/reviews/gnuradio-replay-20261023/REPORT.md)
for the tested GNU Radio version and exact scope.
