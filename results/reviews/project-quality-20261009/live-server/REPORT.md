# Real ProjectAirSim Runtime → P100 SDR smoke qualification

The pinned ProjectAirSim Runtime (`cfb865f29f255b15ef28ec8fdcfaa01a6b66497f`)
was built in `Dockerfile.airsim-runtime` and run with loopback-published API ports.
The generated scene contains two stationary non-physics robots over flat ground.
The RF plane matches that host ground; no Unreal world mesh or vehicle dynamics
is implied. Sionna CUDA/OptiX propagation and CuPy I/Q rendering run on the P100
using the explicit compatibility stack. Existing services were left running;
this is interoperability/recording qualification, not isolated benchmarking.

The first real run exposed a response-schema bug: ProjectAirSim returns
`pose`/`twist` directly, whereas offline mocks supplied a `kinematics` wrapper.
The common mount adapter now handles both shapes, and radar, SDR and distributed
consumers use that normalization. The failed first recording remains a diagnostic;
no successful throughput is assigned to it.

After correction, ten requested 10 ms advances each completed at 12 ms under the
3 ms clock ticks. The recording contains **240,000 complex samples at 2 MS/s**,
or **0.120 signal seconds**. The ten service windows consumed **5.86977 wall
seconds**, including first-use rendering/compilation and RPC/data/checkpoint
writes: **48.9147 wall seconds per signal second**. Scene loading, connection
initialization and final checkpoint/disconnect are outside that service timer.
This cold small-run cost is not comparable to the warmed fleet benchmark.

The inspector passed byte count (960,000 bytes), sample offsets, consecutive
simulation timestamps and signed 12-bit range (observed components −21…+22).
The final-window PSD peak is **149,902.34 Hz**, within one 488.28 Hz FFT bin of
the +150 kHz source. All complex samples contain a nonzero component.

- [Capture manifest and input/backend provenance](manifest.json)
- [Recording inspection and data hash](inspection.json)
- [Receiver metadata](rx0.sigmf-meta)
- [Successful client log](client.log)
- [First-run schema failure](first-failure.log)

Reproduce with the [complete live recipe](../../../../docs/live-workflow.md).
Raw I/Q remains in the ignored `recordings/quality-live-server-v2-20261009`
directory; its hash is published in the inspection. The server was stopped after
qualification. Moving-vehicle physics, long-run recording, calibrated radio
hardware, and Unreal/RF mesh alignment are not established by this smoke test.
