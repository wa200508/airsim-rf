# Send I/Q to a separate processor

The experimental TCP adapter forwards the same post-ADC complex volts as the
live callback, while retaining the local SigMF recording. One connection carries
one or more receiver streams. It is a project-specific transport, separate from
the AMS-GRA radar worker and physical SDR drivers.

## Two-terminal first run

Start the [Runtime server and prepare inputs](scenario-to-iq.md). In the CPU
analysis environment, start the consumer first:

```bash
python examples/receive_iq_stream.py --summary recordings/consumer.json
```

In the CUDA capture environment, run:

```bash
python examples/send_live_iq.py --config recordings/my-scenario/radios.json \
  --output recordings/network-run --updates 10
```

Use the P100 launcher and `--pascal-compat` when required by the environment.
Both commands default to loopback port 8765. Edit `process(block)` in the consumer
example to call your algorithm. `block.samples` contains complex64 I+jQ volts;
other fields give receiver ID, sample offset, integer simulator epoch, sample
rate, carrier and clipping fraction. Keep processing state separately per receiver.
The consumer can use a separate Python environment with NumPy and this package's
source on `PYTHONPATH`; it never imports the live simulator or GPU module.

Compare received sample hashes against the retained recording:

```bash
python scripts/check_iq_transport.py recordings/network-run recordings/consumer.json \
  --output recordings/network-check.json
```

For multiple receivers, add radio mappings to the scenario. They share elapsed
simulation time: two streams of 0.120 seconds are still 0.120 simulated seconds,
not 0.240. [Actual one-/two-receiver evidence](../results/reviews/iq-transport-20261015/REPORT.md).

## Delivery and failure behavior

The callback sends synchronously while the simulator is paused. A slow consumer
creates TCP backpressure and slows wall execution; samples are not intentionally
dropped. The OS may buffer several blocks, so a successful `send` does not mean
the consumer has processed that block yet. After the final block, the producer
waits for an acknowledgement that the consumer exhausted the stream and its
processing function returned. Do not stop iterating early if completion is needed.

Socket timeouts default to 60 wall seconds and apply to individual socket
operations. Increase `--timeout` if compilation or processing can exceed this;
this is not a total session deadline. The reference consumer handles one producer
session and exits. There is no automatic reconnect, replay, resumption or fan-out.

A mid-recording send error propagates through the callback, fails the recording
and retains already saved data. A lost final acknowledgement occurs after local
recording completion: the sender exits with an error, while the local manifest
can correctly remain complete. Check both the sender's acknowledgement and the
consumer summary before claiming delivery. Receipt is not a guarantee that a
consumer persisted its processing output to durable storage.

Per-window service time includes callback send/backpressure. Connection setup
and final acknowledgement occur outside the recorder's timer. Neither those
timings nor controlled stepping imply real-time network throughput.

The default endpoint is local. The protocol is plaintext and unauthenticated;
use a trusted link or SSH tunnel for another host. Binding a public listener is
not required for the local workflow. Cross-host transport, network congestion,
and remote failure recovery have not been qualified.

## Version 1 wire contract

A frame begins with two unsigned 32-bit big-endian lengths: UTF-8 JSON header
bytes, then payload bytes. The header is at most 16,384 bytes; payload is at most
16,000,000 bytes (two million complex samples). Receivers reject larger sizes
before allocating the payload. JSON declares `version: 1` and `type`:

| Type | Fields and payload |
| --- | --- |
| `iq` | `sequence`, `receiver`, `sample_start`, `samples`, `sim_time_ns`, `sample_rate_hz`, `carrier_hz`, `clipped_component_fraction`, `dtype: "cf32_le"`, `units: "volts"`; payload is little-endian float32 I,Q pairs |
| `end` | Next `sequence` and `sample_totals` keyed by receiver; no payload |
| `ack` | Same sequence and totals as `end`; no payload |

Sequence starts at zero and increments per I/Q frame across all receivers.
Sample offsets start at zero independently for each receiver and count complex
samples. Integer nanosecond epochs must be contiguous per receiver; rate and
carrier cannot change mid-stream. The consumer rejects invalid types, sequence
gaps, time gaps, nonfinite samples and unexpected EOF. Each receiver window must
span an integer number of nanoseconds. There is no pickle or executable payload.

Wire samples differ from the recording representation: TCP contains reconstructed
complex float32 volts (eight bytes per complex sample); SigMF contains 12-bit
ADC codes in int16 I,Q containers (four bytes), with per-window scale metadata.
The project reader reconstructs the exact float32 values sent on TCP.
