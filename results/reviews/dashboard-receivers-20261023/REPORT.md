# Receiver selection, circular MUSIC and close chase view

The I/Q panel now selects Site 0 or Site 1, displaying element 0 of that
four-channel array. The skill independently computes both spectra; per-site
spectra and waterfall rows survive recording and seeking. Switching receivers
does not change the displayed camera or acquisition epoch. Older archives that
contain only Site 0 disable the unavailable Site 1 option.

MUSIC now computes a full −180°…+180° spatial spectrum at 0.1° spacing and plots
it on a circle. Radius represents −65…0 dB relative pseudospectrum. The scalar
cone-angle candidate searches −90°…+90°, removing the former ±70° cutoff.
Linear-array front/back lobes remain ambiguous and are explicitly described;
this is not unique 360° direction finding. Old partial searches are drawn as
partial arcs and labeled with their stored coverage. Eigenvalue and phase axes
now show their units, with integer rank/element ticks.

The chase boom is 5 m long, slightly above/behind the drone, aimed at the two
receivers' midpoint. Terrain visual color/emission are darker without changing
RF geometry or dielectric properties. TX/RX labels use the native image's camera
pose plus the applied relative camera mount to locate anchors at image time.
An independent shared-mesh visibility check hides terrain-obstructed anchors.
Labels are recorded in the camera image and their metadata; no processing
results enter the source or its camera labels.

Validation performed locally:

- [66 source/dashboard checks passed](source-tests.txt), 5 optional cases skipped,
  with 3 passing subtests.
- [36 receiver/analysis checks passed](receiver-tests.txt), 3 scene-preparation
  cases skipped in the independent analysis environment. Tests distinguish the
  two receivers using 10 kHz and −35 kHz tones, detect an 80° arrival outside the
  old cutoff, verify identical physical 80°/100° ULA lobes and the ±180° seam,
  check both receiver histories after replay/seek, and verify a blocked RX label
  disappears while the TX anchor tracks a moved/rotated camera body correctly.
- Seven JavaScript presentation tests pass, including receiver changes while
  the acquisition epoch/image hold, old-archive behavior and circular closure.
- [Real Chromium replay check passed](browser.json) on desktop and mobile:
  spectrum and waterfall canvas pixels change on receiver selection, switching
  back restores identical pixels, camera/time remain unchanged, no horizontal
  overflow or JavaScript errors. This uses presentation fixtures and an older
  camera image, not a newly rendered flight.
- [Independent skill-image qualification passed](skill-qualification.json)
  without simulator code/dependencies, at 433 MHz and 1 MS/s.
- Architecture and maintained-document checks pass.

The native Unreal camera qualifier now also checks a close chase distance and
aim within 5° of the receiver midpoint. That extended native render check runs
in publication CI; it was not executed locally in this change. No local GPU
mission or new native-image brightness measurement is claimed.

After the updated three service images publish, restart the dashboard launcher
and prepare a **new mission** to obtain the close camera, labels, both recorded
spectra and full MUSIC search. Existing recordings retain their original image
and data. See the [dashboard guide](../../../docs/dashboard.md).
