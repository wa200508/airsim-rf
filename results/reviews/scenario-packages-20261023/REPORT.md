# Editable scenario package qualification

The dashboard now reads its physical inputs and consumer wiring from the
portable [drone-orbit scenario](../../../scenarios/drone-orbit/README.md).
See [the scenario guide](../../../docs/scenarios.md) for copying, editing,
validation and launch commands. Runtime code and container images are reusable
across supported scenario inputs; generated run files are not edit points.

## Validation

- [CPU suite](cpu-tests.txt): 339 passed, 171 skipped, 3 subtests passed.
- [Scenario tests](scenario-tests.txt): 8 passed, including altered carrier and
  sample rate, multiple actor compilation, file waveforms and real CPU Sionna
  propagation through the production receiver adapter.
- [Architecture audit](audit.json): source/application boundaries passed.
- [Default input validation](validation.json): portable manifest/assets accepted.
- Seven JavaScript dashboard presentation tests passed.
- [Installed-wheel qualification](wheel.json) passed outside the checkout, including default
  scenario discovery, relocated geometry and CPU propagation/consumer checks.
- [Independent skill qualification](skill.json) passed: real TCP I/Q ingestion,
  MUSIC results and control configuration at 433 MHz / 1 MS/s using environment
  port selection, without simulator dependencies or scenario/truth access.

Input snapshots, SHA-256 hashes and pinned deployment image IDs accompany each
dashboard recording. RF consumers receive receiver configuration and samples;
scenario inputs, source truth and emitter waveforms are not mounted into them.

This is CPU/component qualification. It does not claim a local GPU multi-actor
flight, hardware capture, new AMS-GRA conformance or real-time performance.
The dashboard currently uses fixed receiver arrays; moving transmitters support
circle, waypoint and hold plans. New model capabilities require runtime adapters.

## Preceding pipeline repair

The earlier camera check compared an asynchronously delivered image with the
latest platform pose. Commit `38094d4` instead compares it with independently
recorded platform truth at the image timestamp and checks epoch alignment.
[Run 39889754236](https://github.com/wa200508/airsim-rf/actions/runs/39889754236)
passed and published the images: measured chase distance was 5.000001389 m and
camera/body epoch difference was 0 ns. This is the preceding camera-fix run,
not a publication claim for the subsequent scenario refactor.
