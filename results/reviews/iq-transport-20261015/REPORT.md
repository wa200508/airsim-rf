# Separate-process I/Q transport — capture 15 October, published 16 October 2026

The experimental TCP adapter delivered real Runtime/GPU samples to a separate
CPU consumer container. Both the single-receiver and two-receiver cases completed
with explicit consumer acknowledgement. Each receiver delivered **72,000 complex
samples spanning 0.036 simulated seconds** at 2 MS/s. The two receivers run
concurrently: elapsed simulation remains 0.036 seconds, with 144,000 aggregate
complex samples across six network frames.

## Scenario and checks

The generated stationary starter uses a directional `tr38901` TX and isotropic
RX, flat RF ground and specular propagation. The second receiver shares Drone2
with the first but has a (0, 0.5, 0) m body mount offset. Both receiver IDs stay
separate through transport and readback. [Configuration](radios-multi.json).

The consumer hashes little-endian complex64 post-ADC voltage samples. Re-reading
the local SigMF recordings produces **identical hashes**, separately for both
receivers: [comparison](multi-check.json). The source and consumer are separate
containers/processes communicating over host loopback TCP, not separate hosts.
The real Runtime server and GPU execute in the producer workflow.

The initial exact comparison exposed a one-rounding-step reader discrepancy:
ADC scaling used float64 before returning complex64, while the reader scaled in
complex64. The reader now follows the ADC model's precision order. A dedicated
regression compares its output exactly with the quantizer. This does not change
recorded codes or physical model parameters.

Tests cover independent receiver offsets, large integer epochs, explicit final
acknowledgement, early EOF, malformed frame lengths/types, sequence errors and
time gaps. A disconnect during a recording callback marks the recording failed
and retains saved data; a consumer that does not acknowledge completion times
out. **223 tests passed, 157 skipped** with SigMF available.

## Reproduce

Use the [two-terminal transport walkthrough](../../../docs/iq-stream.md). After
both processes finish:

```bash
python scripts/check_iq_transport.py recordings/network-run recordings/consumer.json \
  --output recordings/network-check.json
```

The consumer's summary must say complete and the producer must report consumer
acknowledgement. A complete local recording alone does not prove delivery.
Capture used the P100-compatible image and real Runtime; the consumer used the
CPU image without GPU access. The [single summary](single-consumer.json),
[multi summary](multi-consumer.json), per-case manifests,
SigMF metadata and [regression log](standard-tests.log) are retained here.
Temporary producer/consumer console logs expired before publication; retained
completion summaries and exact sample comparisons provide the delivery evidence.
The regression suite was rerun for publication. Raw I/Q stays in ignored local recordings and is compared via its reconstructed
complex64 hashes.

## Scope

This is a bounded, synchronous, project-specific protocol with TCP backpressure,
not native AMS-GRA/SoapySDR/UHD/GNU Radio integration. There is no automatic
reconnection, resumption, multicast, authentication or encryption. Examples bind
loopback by default; use a trusted link or tunnel for remote hosts. Cross-host
network behavior and throughput are not qualified.

Each frame carries receiver ID, sample offset, integer simulator epoch, rate,
carrier, units and clipping fraction. End-of-stream totals are acknowledged only
after the consumer exhausts processing. Local sample writes precede the send.
Callback send time belongs to per-window service time; connection setup and the
final acknowledgement do not. Backpressure slows controlled simulation, so this
test does not establish real-time delivery. A consumer's acknowledgement does
not guarantee durable storage of its own processing outputs.
