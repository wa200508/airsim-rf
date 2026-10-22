# Primary localhost RF dashboard — qualification

The dashboard is the primary README use case, implemented and periodically pushed
on `main`. Checkpoints include a1b16f7 (priorities 1–3), 5e0e96f (launcher),
85b3f58 (actual circular flight/rendering), 0b46957 (full-orbit audit and transport
completion) and f2f50f7 (shared demo terrain and radio-tracking camera).
Ordinary main pushes test code; container publication requires a version tag.

The initial actual-rendered 90-second orbit passed all 16 acceptance checks:
750 coherent windows, 11.52 GB independently received ADC I/Q, eight acknowledged
sample totals, 389 actual camera frames, 8.04 radians of left-hand travel, radius
249.83–250.54 m, and 154 both-blocked/no-detection windows. RF exited normally.
Pause held the actual clock and received-byte counters while all three processes
remained alive. See [acceptance evidence](../../results/reviews/dashboard-20261021/acceptance.json).

The user requested the terrain from the other RF examples. The primary scene now
uses `demo_terrain()` with its same hills and drainage valley: horizontal scale
four, vertical scale three, 800 m width and 90 m relief above RF base 100 m.
The 250 m orbit commands RF altitude 200 m. Identical triangles are exported to
Unreal and Sionna. Natural hills replace the artificial ridge. A gimballed Chase
camera tracks actual drone and ground receiver positions, with projected TX/RX
labels and ground radio location beacons. No airborne beacon is placed in the
flight path. Final terrain/camera qualification evidence is recorded separately.

The CPU skill image passes valid-completion, incomplete-group/no-ACK, failed-stream
HTTP 503 and ingress-bind-failure HTTP 503 checks. SQUALL gRPC status and fixed
profile validation are exercised. Coherent framed TCP remains a documented
metadata extension; native MEL/VITA conformance, hardware calibration, generic
multipath-robust MUSIC and real-time operation are not claimed.

During integration we corrected Unreal software Vulkan startup, imported mesh
UV/tangent visibility, native path yaw mode, a long-command wall deadline,
read-only image buffers, and explicit camera/object pose frame IDs. Earlier probe
logs and local diagnostic captures remain outside the maintained report set.
