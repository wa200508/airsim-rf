# Project quality assessment — 9 October 2026

## Verdict and scope

AirSim-RF is a credible, instrumented research prototype with useful RF observables and substantially improved timing documentation. Its current documentation is not yet a consistently reliable product guide. The most important defects concern scenario reproducibility, stale scientific claims, and unexplained missing plotted data. These should take precedence over cosmetic redesign or further performance claims.

This assessment covers revision `1e9c2934593c410f99a22e69e2cd1f1f37dd2192`, present on both `main` and `profiling/p100` when reviewed. It inventories all 115 tracked Markdown files, checks their local file links, and examines the 16 maintained Markdown documents, current sensing gallery, relevant generators, benchmark fixtures, raw figure data, setup/live workflow, and published measurement checks. Historical reports were sampled and structurally checked; this is not a line-by-line scientific revalidation of every archived experiment or a complete source-code audit.

No source code, existing documentation, or published figure was changed. New review artifacts contain the assessment and numerical evidence. The ten current sensing/scenario figures were regenerated into a temporary directory from the committed recordings. No new propagation simulation, real ProjectAirSim session, fresh installation, physical SDR experiment, or full test-suite run was performed in this review. Regeneration was sufficient to reproduce the plotting defect; a new propagation run would not repair its interpretation.

Priorities: **P1** means address before relying on the affected claim or repeating the affected experiment; **P2** means address before presenting this as a polished, reproducible workflow; **P3** means a useful presentation improvement. No P0 release-blocking safety or data-loss finding was established.

## What is already good

- The main sensing page distinguishes two offline experiments, scripted terrain-following motion, simulated receiver processing, and conditional geolocation geometry. It does not claim an AirSim flight or a measured location fix.
- The current ESM waterfall genuinely uses consecutive windows from one contiguous I/Q capture. Its manifest records sample rate, window/hop/FFT sizes, duration, density units, bin spacing, and Hann equivalent noise bandwidth. It does not fill the 0.5 s gaps between independent captures.
- Radar profiles use total bistatic path length `cτ`, and the scenario illustration explains the geometry. The height-error result is explicitly conditional on the midpoint-height reference; it is not presented as field-validated terrain reconstruction.
- Current performance pages distinguish simulated signal duration, service wall time, and timer scope. The published timing-table checks passed. There is no basis here for calling those checked numerical tables fabricated or arithmetically inconsistent.
- Raw recordings, numerical products, source hashes, and visibility records make investigation possible. The current figures are much stronger than an unexplained collection of heatmaps.
- The live guide acknowledges frozen geometry within windows, physics overshoot, waveform duration, nominal-clock restrictions, and the absence of a qualified real-server session.
- GitHub Actions succeeded for the reviewed revision on both [main](https://github.com/wa200508/airsim-rf/actions/runs/38014170712) and [profiling/p100](https://github.com/wa200508/airsim-rf/actions/runs/38014168851). Passing CI is useful evidence, but it does not establish every scientific claim or qualify a live deployment.

## Findings and required changes

### Q01 — P1: the new terrain is incompatible with existing benchmark poses

**Evidence.** `benchmarks/scattering_scenario.py:14,25` still places transmitters at z = 10 m. Evaluating its default 100-transmitter row against the current terrain at epoch zero puts **31/100 below the terrain elevation**, with minimum clearance **−2.491 m**. `benchmarks/benchmark_end_to_end.py:165–176` loads the current terrain and creates seeded random positions with z in [20, 40] m. Reproducing its RNG sequence gives **3 below-surface transmitters in the 100 TX / 10 RX case**, minimum clearance **−1.868 m**. The smaller 2×2 and 10×4 cases are clear at epoch zero; this does not certify their entire trajectories.

**Impact.** Repeating an old benchmark command now changes the physical scene and can introduce invalid airborne placements. The demonstration generator's lifted/clearance-adjusted poses do not fix the shared timing fixtures. Historical timings collected with the earlier terrain remain historical evidence; they must not be silently reinterpreted as timings for the new scene.

**Required change.** Version and identify benchmark scenes independently of the presentation terrain. Choose explicitly between preserving the historical scene for matched comparisons and introducing a new physically valid benchmark. Validate pose clearance over every simulated trajectory, not just the first pose. Record source revision, mesh hash, scene ID, pose/trajectory definition, and propagation settings with each result. Rerun affected benchmarks only after this is resolved. This requires future source/fixture changes; none were made here.

**What should be shown.** Every performance table should identify its scene version. A new terrain benchmark should include a small clearance summary and a geometry/route view. Before/after optimization comparisons must use identical physical inputs.

**Acceptance.** All airborne radios satisfy the declared clearance over the full tested interval; a replay resolves the exact mesh used in its published record; historical and new-scene results are visibly separate.

### Q02 — P1: received-power claims describe the old terrain

**Evidence.** `docs/architecture.md:530–532` claims final received powers of about −60.3/−95.5 dBm at listener A and −63.5/−95.1 dBm at listener B. The current `docs/figures/pluto_esm_report.json` instead records the following at **t = 5.5 s**:

| Receiver | Beacon A link power | Beacon B link power |
|---|---:|---:|
| Listener A / Receiver 1 | −99.78 dBm | −95.00 dBm |
| Listener B / Receiver 2 | −65.89 dBm | −95.50 dBm |

The largest discrepancy is about **39.5 dB**. The visibility record reports that terrain blocks Beacon A's direct link to Receiver 1. Noise power is approximately −103.98 dBm per receiver; these link-power values precede adding that receiver noise.

**Required change.** Replace the prose with a table generated or checked against the current report, including capture epoch and scenario identity. Explain that the stronger transmitted beacon is weaker at Receiver 1 because the direct path is blocked and only other propagation contributions remain. Do not infer received strength from the 30 dB transmit-power difference alone.

**What should be shown.** The table above and a link-power-versus-epoch plot with direct-visibility status for each link. Use recorded per-link powers and visibility; do not imply that the 2 ms waterfall depicts the entire 5.5 s route.

**Acceptance.** Every displayed received-power number resolves to a specific record and agrees within its displayed rounding. The scenario diagram, spectra, and explanatory prose describe the same dataset.

### Q03 — P1: undefined 8-bit metrics disappear without explanation

**Evidence.** `benchmarks/generate_sensing_figures.py:130–133` divides peak PSD by median local PSD. Receiver 1's 8-bit control is all-zero in every capture; Receiver 2's is all-zero in the first ten of twelve captures. Thus **12/12** and **10/12** prominence values respectively are nonfinite. Fresh regeneration reproduces an invalid-division warning. The green series is absent from the first panel and appears only at the last two points in the second. In the final spectrum, Receiver 1's zero-valued control also lies below the displayed plotting floor.

**Impact.** A reader cannot distinguish missing computation, a hidden curve, and a quantizer that produced no nonzero samples. The figure's legend implies three available comparable series. This is an interpretation defect, not evidence that the entire simulation failed.

**Required change.** Represent the condition explicitly in numerical metadata and plot annotations: “all samples quantized to zero; peak/floor ratio undefined.” Show nonzero-code fraction or a separate quantizer-status strip over the epochs. Explain gain/full-scale calibration for this numeric control. Retain gaps for undefined values. Do not replace 0/0 with 0 dB, draw fabricated floor values as measurements, or infer the performance of a physical 8-bit radio from this one configuration.

**What should be shown.** Analog and 12-bit prominence curves, the two valid 8-bit points, and an unambiguous status band for all-zero captures. The spectrum should label why the 8-bit trace is not visible.

**Acceptance.** Every omitted value has a machine-readable reason and a visible explanation; regeneration handles the expected condition without an unexplained numerical warning.

### Q04 — P1: citation anchors can resolve to the wrong references

**Evidence.** `docs/references.md` contains two sets of explicit `ref1` through `ref10` IDs: the first spans lines 220–267, the second lines 727–773. For example, `ref1` appears at both lines 220 and 727. The consolidated bibliographies therefore do not provide unique targets for their citations.

**Required change.** Give references stable unique identifiers, preferably author/year/topic keys or distinct section namespaces, and update every corresponding citation after checking its intended source. Do not merely rename the second set without resolving inbound links. Add duplicate-ID and fragment-target checks to the documentation validation in a future implementation change.

**What should be shown.** Each scientific statement should lead to the intended original paper or technical reference, with unambiguous title/authors/year and a direct source link where available.

**Acceptance.** No duplicate explicit IDs; every citation resolves to the intended bibliography entry. This review identified structural citation ambiguity, not a finding that the cited papers themselves are fabricated.

### Q05 — P2: historical development status reads like current guidance

**Evidence.** `docs/rendering.md:21–27` introduces the basis renderer as a new separate CPU research implementation, while later sections discuss work still needed before complete receiver integration (`:164–166,265–280`). The historical qualification is present but the narrative still reads as an active roadmap. `docs/setup.md:431–439` says GPU/OptiX/P100 execution remains untested because the workspace has no GPU. Other sections document the later working GPU pipeline. Architecture/setup also retain branch-specific directions even though the reviewed content is on main.

**Required change.** Make the first section of each maintained guide describe current supported behavior. Move completed research steps and old environment limitations into explicitly dated history. Keep the algorithm derivation where useful, but label its experimental benchmark separately from the production receiver. Distinguish standard dependency installation, Pascal compatibility, and historical hybrid profiling recipes. Historical records should retain their original limitations rather than being retrospectively rewritten as successful GPU runs.

**What should be shown.** A compact capability/status table: workflow, propagation backend, renderer, validated environment, validation scope, and remaining limitation. Link each status to evidence. Hardware belongs here when it determines compatibility or performance.

**Acceptance.** A reader can choose a current installation and command without reconciling contradictory status statements. No archived “next step” appears to be an unfinished requirement when it has already been implemented.

### Q06 — P2: the live workflow is a contract, but not yet a complete first-run recipe

**Evidence.** `docs/live-workflow.md` correctly explains the operating contract, but its configuration points at user-supplied scene files and `tx0.npy` (`examples/config/live-radios.json`). There is no adjacent executable waveform-creation step or bundled matching AirSim/RF scene setup. `src/airsim_rf/live.py:88–94` requires CuPy, but `pyproject.toml` does not provide a GPU/live extra; the ordinary locked dependencies do not include it. The P100-specific requirements supply it. “Run inside the CUDA-enabled environment” leaves an important dependency choice unresolved for a new user.

**Required change.** Add one tested two-radio walkthrough with exact environment installation, ProjectAirSim client/server expectations, a waveform creation command, sample count/duration and declared frequency bounds, matching geometry/origin/units, robot names, recording command, and inspection commands. A future packaging extra may simplify dependency installation, but a complete documented environment is still necessary. Keep the real-server qualification disclaimer until a real session is completed.

**What should be shown.** Expected directory contents, a short manifest excerpt with actual samples/simulated duration/wall time, an I/Q or spectrum sanity check, and explicit success/failure criteria. Document what the program leaves paused. State that recordings are produced; do not imply a physical SDR transmission or wall-clock real-time stream.

**Acceptance.** A new user with the stated server/environment can execute the recipe without inventing a waveform or guessing dependency versions. A recorded real-server smoke test establishes geometry alignment, continuity, and output readability before this workflow is called qualified.

### Q07 — P2: older figure paths still expose deprecated presentation conventions

**Evidence.** Architecture links `pluto_esm_overview.png` and `pluto_esm_waterfalls.png` as earlier illustrations (`:365,549`). `examples/pluto_esm_drones.py:214–225` still renders spectra from separated captures as a continuous-looking image spanning their epochs. `benchmarks/generate_rf_waterfalls.py:136–161` generates channel-power delay/Doppler histograms and path-length-versus-time images named waterfalls. These are different products from the current contiguous-I/Q waterfall. The sensing page's statement about removal from the displayed/generated set needs a clearly limited scope while these routes remain available.

**Required change.** Designate a single current gallery and generation workflow. Inventory legacy assets by generating command, source dataset, scene version, and historical status. Remove obsolete images from the active instructional path or link them only from dated archives with limitations. Update future generator outputs so an example does not silently recreate a deprecated presentation.

**What should be shown.** Use frequency versus acquisition time for spectrum waterfalls. Use a conventional range–Doppler map only when its coherent acquisition supports it. Keep useful channel histograms as explicitly named diagnostics outside that gallery, preferably one-dimensional cuts under the user's current presentation convention. Terrain diagrams are physical scene context, not sensor response maps.

**Acceptance.** Following any current documentation command produces the current named products; a reader cannot mistake separated snapshots for continuous acquisition or an incoherent channel histogram for measured Doppler processing.

### Q08 — P2: the passive cuts hide the clock correction they compare

**Evidence.** `benchmarks/generate_sensing_figures.py:153–162` recenters raw and oracle-corrected frequency cuts around different centers before overlaying them. The raw center is about 13.725 kHz, whereas the corrected center is zero. The nearly overlapping curves show residual shape, not the absolute clock-frequency correction. The axis says “respective center,” but the correction is not visually intelligible. The rendered delay-axis labels are also crowded/overlapping.

**Required change.** Show raw and corrected cuts on a common absolute frequency axis, or use a full-frequency overview plus clearly labeled residual insets and an explicit center-offset table. Use distinct line styles and fewer delay ticks. Preserve independent cut normalization only with an explicit caption; peak-normalized curves do not establish recovered absolute signal power.

**What should be shown.** The raw frequency displacement and its removal using known simulated clocks, plus the poor delay discrimination of the narrowband signal. Continue calling the correction oracle-assisted; it is not an estimated synchronization solution or a demonstrated geolocation fix.

**Acceptance.** A reader can see both the frequency shift and what the residual comparison tests without reading generator code. No clipped or overlapping labels at the published display size.

### Q09 — P2: physical context needs an explanatory link between clearance, blockage, and received power

**Evidence.** The new 3D view is useful, but `benchmarks/generate_sensing_scenarios.py:117–131` draws all routes over the surface with explicit ordering. The title discloses this; it still makes depth/clearance difficult to judge. The blocked-link red cross in the plan view is placed at the link's midpoint (`:58–59`), not a computed terrain intersection. It labels blocked status, but cannot locate the blocking ridge.

**Required change.** Keep the 3D overview, add altitude and terrain height along each route (or clearance versus epoch), and provide a side section for the blocked link. If an intersection is marked, compute its location; otherwise explicitly label the cross as a status symbol. Use visibility-aware drawing or distinguish obscured route segments. Reduce repeated explanatory text inside the illustration and preserve readable labels.

**What should be shown.** Terrain elevation, radio altitude, minimum clearance, the obstructed line segment/ridge at the selected capture, and the corresponding link-power history from Q02. Mark the trajectory as scripted, not a demonstrated collision-avoidance controller.

**Acceptance.** The figure lets the reader explain why Beacon A is shadowed at Receiver 1 while all four radios remain above ground. Diagram, power trace, and waterfall share an explicit capture epoch.

### Q10 — P2: published hardware-neutral interpretation is still inconsistent

**Evidence.** `docs/architecture.md:361–363` still describes the SDR figures as P100 propagation/direct CUDA rendering, despite the hardware-neutral sensing page. The scope text in `sensing_products.json` and `sensing_scenarios.json`, and their generators, also embeds “P100” as though it defines the scientific dataset.

**Required change.** Describe the scenario, model, receiver settings, and acquisition in interpretive prose. Move execution device/backend information into provenance fields and retain it in setup, compatibility, performance, and reproducibility sections where it matters. Do not erase backend records needed to reproduce a run.

**What should be shown.** Backend-neutral plot titles/captions and explicit provenance fields. State numerical equivalence within a declared tolerance when established, rather than promising bit-for-bit equality across CPU/GPU implementations.

**Acceptance.** Scientific meaning does not depend on the rendering hardware label. Current review regeneration found 32 of 34 numerical products exactly equal (including matching NaNs); the two CAF power arrays differed by only about 1.4×10⁻⁸ of reference peak, with identical peak indices. This supports consistency of this postprocessing run, not equivalence of complete propagation simulations on all devices.

### Q11 — P2: documentation quality checks miss the defects a reader encounters

**Evidence.** All four existing documentation/timing checks passed. Nevertheless the review found duplicate IDs, unexplained nonfinite plotted values, stale power prose, and the broken `docs/architecture.md:462` link to `README.md#attach-to-an-airsim-vehicle`. No missing local file targets were found across the 115 tracked Markdown files, so this is specifically a fragment/content-validation gap.

**Required change.** Extend future checks to unique IDs and fragment targets, expected finite/explicitly undefined plot products, consistency of reported scientific scalars with source data, and source-hash validation. Exercise both current figure generators. Keep a visual review checklist for readable labels, legend entries without visible measurements, physical units, acquisition duration, and common normalization. Numeric checks cannot replace rendering inspection.

**What should be shown.** A short validation summary distinguishing link checks, numerical consistency, visual review, offline tests, device qualification, and real-server qualification. Do not reduce all of these to “CI passed.”

**Acceptance.** The broken anchor and duplicate bibliography IDs fail checks; expected all-zero control data pass only with explicit status; stale copied numbers cannot silently pass. New rules should avoid indiscriminately rewriting immutable historical results.

### Q12 — P3: consolidation reduced file count without fully simplifying the reading path

**Evidence.** Maintained documents contain approximately 7,046 lines, including a 1,232-line architecture page, 931-line rendering page, 835-line reference page, and 738-line setup page. Current guidance, initial research, benchmark protocols, and historical constraints still compete in the same reading path.

**Required change.** Organize by reader task: first offline example; first live recording; scientific assumptions/observables; implementation architecture; performance/reproduction; dated research history. Keep one canonical explanation per concept and link to it. Do not create another parallel general-purpose guide. Introduce a clear glossary separating simulation epoch, continuous acquisition duration, update interval, service wall time, and warm/cold timing.

**What should be shown.** A short navigation table with purpose and prerequisites, and a capability table distinguishing implemented, offline-tested, device-tested, and live-qualified behavior. Retain the existing precise timing conventions.

**Acceptance.** A new reader can identify the relevant workflow and its limitations from the entry page without reading research history first.

## Figure-by-figure disposition

These recommendations concern the ten figures currently embedded in `docs/sensing-plots.md`. “Keep” means the plotted observable is sensible, not that it establishes general system accuracy.

| Figure stem | Disposition | What the revised figure/caption should show |
|---|---|---|
| `sensing_esm_scene_3d` | Revise context (Q09) | Terrain and routes with intelligible depth; add a clearance/altitude profile. Retain the vertical exaggeration and scripted-motion disclosures. |
| `sensing_esm_scenario` | Revise context (Q09) | Actual plan geometry and capture timeline; distinguish a blocked-link status marker from an actual obstruction location. Pair with a side section. |
| `sensing_radar_scenario` | Keep, minor polish | Actual elevation profile, fixed 40 m RF altitude, projected 2 m baseline, and explicitly illustrative bistatic paths. Keep site colors consistent with the delay profiles. |
| `sensing_esm_waterfall` | Keep, improve standalone context | Contiguous approximately 2.048 ms capture starting at simulation epoch 5.5 s, nominal 915 MHz carrier, frequency offsets, A/B markers, shared dBm/Hz scale, and acquisition/window settings. It cannot show the full 5.5 s motion. |
| `sensing_radar_delay_profiles` | Keep | 20/200 MHz responses on the same traced channels against total path length `cτ`. Explicitly retain the per-site normalization so readers do not compare absolute strength across sites. |
| `sensing_radar_error` | Extend diagnostic explanation | Existing estimate/reference scatter and absolute-error ECDF, plus signed error against route distance. Mark the worst case at 134.2 m; investigate it against slope and multipath before assigning a cause. |
| `sensing_esm_spectrum` | Revise (Q03) | Explicit all-zero 8-bit annotation, expected tone markers, epoch, receiver/calibration context, and PSD-density units. |
| `sensing_esm_line_prominence` | Revise (Q03) | Show undefined intervals as quantizer status, not missing unexplained curves. Describe this as local peak prominence, not detection probability or calibrated SNR. |
| `sensing_passive_cuts` | Revise (Q08) | Common absolute frequency context for raw/oracle correction, readable delay ticks, explicit normalization, and poor narrowband delay discrimination. |
| `sensing_passive_geometry` | Keep with stronger scope/ambiguity explanation | Epoch-zero truth-derived loci conditional on known emitter altitude/velocity and calibrated clocks. Explain that these differ from the final-epoch recordings in other panels. The plotted loci visibly admit another crossing; discuss ambiguity rather than imply a unique estimated fix. |

For the radar error figure, the committed data give mean signed error **+0.107 m**, RMSE **0.913 m**, and maximum absolute error **4.065 m** over this route. These describe the current peak-based equivalent-height observable versus the DEM midpoint reference. They are not sensor-wide accuracy specifications, independent repeated trials, or a confidence interval.

Do not add an ROC curve, localization error ellipse, or convincing-looking range–Doppler map without the corresponding experiment. A useful future radar acquisition would record coherent successive pulses with declared PRF, pulse count, observation duration, waveform, bandwidth, receiver model, and target/terrain truth. Conventional range–Doppler processing uses fast time within pulses and slow time across pulses; see the [MathWorks processing description](https://www.mathworks.com/help/phased/ug/range-doppler-response.html). Retain the distinction between PSD density and power per bin in the ESM plots; [SciPy's Welch documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html) specifies the density normalization.

## Timing and optimization claims

The existing timing normalization is a substantial improvement and should be preserved. A headline measurement should identify: workload/scene ID; number of TX/RX; samples and nominal sample rate; continuous signal duration per receiver; update count/interval; timer boundary; propagation/rendering backend; warm/cold treatment; repetitions and statistic; and wall seconds per signal second. Separate initialization and finalization whenever excluded from the service timer. Do not multiply signal duration by receiver count without labeling that as an aggregate receiver-sample workload.

This review did not establish that the basis optimizations are merely hard-coded to one scenario. The rendering documentation includes broader delay/Doppler qualification and explicit bounds. It also does not establish universal speedup or correctness. The terrain/fixture mismatch in Q01 illustrates why a performance suite needs stable physical inputs. Future claims should separate algorithmic equivalence within a declared operating envelope from speed on selected workloads. Keep out-of-range failures visible and compare against the direct reference over independent waveforms, clocks, delays, Dopplers, path counts, and geometry classes before extending the qualification claim.

## Verification record

Performed for this assessment:

1. Checked tracked-file inventory and repository state; preserved the existing untracked profiling directory.
2. Verified successful GitHub Actions runs for the reviewed main and profiling revisions.
3. Ran `scripts/check_docs.py`, `scripts/update_timing_context.py --check`, `scripts/update_runtime_docs.py --check`, and `scripts/update_profiling_breakdown.py --check`: all passed. The timing-context check covered 137 recorded cases.
4. Audited local file links across 115 tracked Markdown files and maintained-document fragment/explicit-ID structure. The supplemental fragment parser is heuristic; the reported broken fragment and duplicate explicit IDs were directly inspected.
5. Recomputed final link powers, quantizer-zero counts, nonfinite plot-array counts, radar error statistics, and benchmark fixture clearance from recorded inputs/current terrain. No new ray tracing was involved.
6. Regenerated all seven sensing-analysis figures and three physical-scenario figures in an isolated temporary output directory using the existing scientific Python container with the repository mounted read-only. Both generators completed; the analysis generator emitted the reproduced prominence warning described in Q03.
7. Compared all 34 numerical analysis arrays with the committed products: 32 were exactly equal including matching NaNs; the two CAF power arrays had maximum absolute differences of 3.20×10⁻⁹ and 3.14×10⁻⁹, approximately 1.39×10⁻⁸ and 1.35×10⁻⁸ of their respective reference peaks. Both retained the same peak index. This was NumPy postprocessing of existing recordings, not a test of CPU/GPU propagation equivalence.
8. Inspected current rendered figures for geometry clarity, units, normalization, missing data, and label layout. Older generation paths were inspected for consistency with the current gallery convention.

The figure checks can be repeated without overwriting published assets (use the configured scientific Python environment and an empty output directory):

```bash
python -B benchmarks/generate_sensing_figures.py --data-dir docs/figures --output-dir /tmp/airsim-rf-review-figures --backend numpy
python -B benchmarks/generate_sensing_scenarios.py --data-dir docs/figures --output-dir /tmp/airsim-rf-review-figures
```

Machine-readable evidence:

- [Numerical and physical-scenario audit](../../results/reviews/project-quality-20261009/data_audit.json)
- [Markdown structure/link audit](../../results/reviews/project-quality-20261009/links.json)
- [Fresh postprocessing comparison](../../results/reviews/project-quality-20261009/regeneration_comparison.json)

## Recommended implementation order

1. Resolve scene versioning/clearance and correct the stale power claims; these are prerequisites for trustworthy new measurements.
2. Explain the all-zero controls and repair citation targets. Regenerate affected figures only after the intended metric/status semantics are explicit.
3. Reconcile current versus historical setup/rendering guidance and provide the complete two-radio live recipe.
4. Revise the passive comparison and physical scenario context; retire obsolete products from active documentation paths.
5. Add content/anchor/figure checks, then perform a fresh environment smoke test and real-server qualification when the server is available.

The recommended work includes documentation edits, future generator/fixture changes, and operational qualification. This assessment implements none of those fixes; it provides the evidence and acceptance criteria needed to review them deliberately.
