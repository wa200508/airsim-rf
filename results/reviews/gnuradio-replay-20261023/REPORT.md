# Native GNU Radio capture interoperability

Bulk receiver I/Q remains lossless per-channel SigMF `cf32_le`: the same
headerless interleaved float32 I/Q that stock GNU Radio Complex File Sources
consume. No extra sample format, conversion, normalization or duplicate data
files were introduced. See [the GNU Radio guide](../../../docs/gnuradio.md).

Closed bulk captures now include generated `replay.grc` and `view.grc` files.
The first is an editable headless DSP starter; the second adds a Qt spectrum
viewer and channel chooser. Existing archives can add these graphs with
`python -m airsim_rf.sample_recording gnuradio PATH`.

## Native qualification

[Tests](native-tests.txt) ran in Debian bookworm with **GNU Radio 3.10.5.1**,
system Python 3.11, NumPy 1.24 and the stock `grcc` compiler. Results:
**15 passed, 2 skipped** across native GNU Radio and existing archive tests.
The skips are optional SigMF-library and MUSIC-library tests in that light
environment; all six GNU Radio/export tests passed, without native-test skips.

- Both generated graphs compile using stock blocks and no project-specific
  GNU Radio plugin.
- Every complex sample from four independent, phase/frequency-evolving channels
  matches its original bytes after native File Source playback.
- A common nonzero start offset reproduces exactly the selected suffix on
  every channel; moving the archive to a path with spaces does not break it.
- The generated headless command runs to EOF without an interactive prompt.
- The Qt graph opens offscreen, selects a channel, produces that channel's exact
  samples, and accepts a dropdown change after scheduler initialization.
- Regenerating graphs for an existing archive leaves sample files unchanged.
- [Architecture boundaries](architecture.json) and maintained documentation
  links pass. A dedicated native GNU Radio CI job gates container publication.

## Clock and scope

All channels share one vector Throttle between Streams to Vector and Vector to
Streams. Playback pacing changes wall time; it does not resample or change
physical sample rate, phase, Doppler or amplitude. File Sources use a common
offset/length and do not repeat. The graphs are source-neutral and do not run
MUSIC or import the simulator.

Stock File Sources do not reconstruct acquisition/window stream tags from
JSON. Original timestamps/window boundaries remain in `windows.jsonl`, and
array geometry/calibration remain in `receiver-config.json`. Tag-dependent
algorithms require an adapter; TCP replay retains that acquisition metadata.
The GUI's FFT display is not a calibrated RF instrument. No GPU flight,
physical SDR or human visual-inspection claim is made here.
