# airsim_rf SigMF extension

Version: **0.1.0**. Namespace: `airsim_rf`. Used with core SigMF 1.2.6.
This local extension is optional for reading integer sample codes. It is required
to interpret simulator epochs, model input-referred volts and clipping diagnostics.
It is not a physical calibration certificate or a registered standard extension.

## Capture fields

| Field | JSON type | Meaning |
| --- | --- | --- |
| `airsim_rf:sim_time_ns` | integer | Simulator timestamp of the capture's first complex sample, in nanoseconds; not UTC |
| `airsim_rf:volts_per_count` | number, positive | Multiply signed I and Q codes separately by this value for quantized model input-referred volts |
| `airsim_rf:clipped_component_fraction` | number, 0–1 | Fraction of I and Q components clipped before storage, over this capture window |

Each field is repeated at every capture. Its segment ends at the next capture's
`core:sample_start`, or the dataset end. Files use `ci16_le`: signed 12-bit codes
in little-endian int16 containers. A complex sample occupies four bytes.

New recordings declare this extension in `core:extensions` with `optional: true`.
Older recordings have identical fields but lack that declaration. The bundled
reader accepts both. Other SigMF readers can ignore the extension and read raw
codes, but their normalized output is not automatically volts. Simulation epochs
must remain integers until subtracting a reference epoch.

See the [SigMF extension rules](https://sigmf.org/) and
[scenario-to-I/Q guide](../scenario-to-iq.md) for usage.
