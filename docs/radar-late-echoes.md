# FMCW echoes across pulse boundaries

This branch retains its existing propagation solver and rendering experiments.
FMCW acquisition now retains each emitted ramp's timestamp, waveform/power and
complex channel coefficients until its last delayed arrival. A receive window
can contain echoes from multiple earlier chirps; source samples are not reset
at a PRI or capture boundary. Mixing uses the current LO ramp, the original
delay, and Doppler phase advanced from emission. Carrier phase already belongs
to the branch's Sionna channel coefficient and is not applied a second time.

`transmit_enabled=False` stops new illumination while earlier returns and
receiver noise/ADC remain. Compact per-path descriptors expire at emission time
plus ramp duration plus path delay. Memory follows the propagation-delay horizon,
not total run length. Fractional arrivals and finite half-open ramp gates are
preserved. Direct calls must use increasing capture timestamps; call
`reset_history()` before an independent run or rewind. Worker session release
and new claims reset this history. Carrier/ramp changes with pending echoes
require a fresh session.

Geometry, delay, visibility and gains remain frozen at emission for a ramp;
narrowband Doppler advances its phase. The existing steady-state IF tone filter
does not model pulse-edge ringing. No new terrain model, path-depth policy,
GPU speed claim or shared-transmitter optimization is introduced by this fix.

`tests/test_fmcw_history.py` verifies the first pulse arriving during the fifth
receive window, fractional delay/Doppler, overlapping old and current returns,
TX-off arrivals, large epochs, finite support and bounded expiration. The
deliberately distant scatterer is a delay stress, not a hobbyist-range claim.
Existing power/beam/frame and distributed-worker tests remain in place.
