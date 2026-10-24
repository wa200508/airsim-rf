[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Low-terrain demos and adjustable receiver noise

Both packaged demos now fly a terrain-aware path with **20 m minimum planned
clearance**. The direction-finding transmitter keeps its 250 m orbit; RadarDrone
keeps its 400 m-straight / 80 m-turn racetrack. Height changes are part of the
native ProjectAirSim path. RF uses actual position and velocity readback.

## Flight controls

Edit the actor's `flight` object in its scenario's `flight.json`:

```json
{
  "terrain_clearance_m": 20.0,
  "max_vertical_grade": 0.2
}
```

These fields accompany the existing circle/racetrack/waypoint fields. The
nominal starting/center height is now **120 m RF-up**, an absolute lower floor;
it is not the height commanded through the hills. The compiler raises and
smooths the route above the shared DEM. A grade of 0.2 limits planned height
change to 20 cm per horizontal metre, allowing the drone to anticipate hills
instead of making abrupt vertical climbs. It limits both ascent and descent;
at 20/25 m/s total path speed, the largest planned vertical speed is about
3.9/4.9 m/s. Native controller dynamics determine the achieved motion.

The compiler inserts intersections with terrain grid edges and triangle
diagonals. Between these points both the heightfield and planned route are
linear, so clearance is checked between the originally declared waypoints too.
A periodic altitude envelope preserves closed-loop continuity. Some sections
fly higher than 20 m AGL to prepare for a climb or descent. Spawn, settling,
mission flight and the dashboard route share these compiled coordinates.
`scenario-input/flight.json` preserves the authored nominal values;
`runtime.json.compiled_routes_rf_m` contains the absolute planned paths.
Remove both new fields to use an ordinary absolute-height flight plan.
Heightfield terrain is required for this option.

## Receiver-noise control

Both demos start with **`noise_power_offset_db: -25.0`** and thermal noise
still enabled. This is an explicit demonstration adjustment, chosen to make
terrain response visible; it is not a measured noise performance claim for a
physical PlutoSDR or IWR1843 board. The configured noise figure, temperature,
antenna, IF gain, scattering rules, RCS and ADC transfer remain their existing
model values.

| Scenario | Edit in `radios.json` |
| --- | --- |
| Direction finding | `receiver_profile.noise_power_offset_db` |
| FMCW radar | `radar.profile.noise_power_offset_db` |

| Value | Injected thermal-noise power relative to the receiver model |
| --- | --- |
| `0` | Original modeled `k × T × bandwidth × noise factor` |
| `-10` | One tenth of the modeled noise power |
| `-25` | About 1/316 of modeled noise power; demo default |
| `+10` | Ten times the modeled noise power |

Voltage standard deviation scales by `10^(offset/20)`; power scales by
`10^(offset/10)`. Accepted offsets are −120 through +60 dB. `noise_enabled: false`
omits thermal noise entirely. ADC quantization and clipping remain active.
The SDR noise-power diagnostic reports the power actually injected after the
offset. The dashboard shows the selected offset under **Receiver noise**;
recordings preserve it in the scenario snapshot. The receiver skills receive
I/Q and acquisition metadata, with no simulation or terrain controls.

Edit the files in the selected scenario package, then use **Prepare services**
for a new mission. No skill or container rebuild is needed to tune these values
once the updated runtime is installed. Existing copied scenario packages retain
their own settings; add these fields there to adopt the new defaults.

The [ADC tuning check](../results/reviews/low-terrain-demo-20261024/REPORT.md)
compares 0, −15 and −25 dB at four points on the planned radar route, checks all
eight direction-finding receiver streams, and documents the test's limits.

Direction finding uses one-way terrain **multipath**; radar uses first-order
terrain **backscatter/clutter**. Lower altitude and noise adjustment do not add
new scattering mechanisms or change either skill's detector or estimator.
