[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Diagnose setup and capture failures

Start with `airsim-rf preflight --config <radios.json>` and the same `--updates`,
`--advance-ns` and `--max-samples` planned for recording. Add `--output` to check
the proposed new directory and disk space. Add `--gpu` only for a CUDA backend
check; include `--pascal-compat` in the qualified P100 environment. Preflight
does not contact, load, step or mutate a simulator.

The CLI returns exit code 0 on success and 2 for diagnosed input/setup errors.
Library functions raise descriptive exceptions. Preserve the full exception,
preflight JSON, package versions, recording manifest and task-owned server log
when investigating a failure. Never use an incomplete recording as completed data.

| Symptom/error | Meaning and corrective action |
| --- | --- |
| Use Python 3.12 | The lock is qualified on 3.12. Create that environment rather than combining the lock with another interpreter. |
| Existing dependency differs from the clean pin | Bootstrap found a different commit or local edits under `.deps`. Preserve those edits and use a separate clean checkout; bootstrap deliberately does not reset them. |
| `pxr` / OpenUSD missing | Install `requirements-geometry.txt` in the intended environment, or bootstrap with `--geometry`. The shared example requires USD; the ground-only example does not. |
| Missing NumPy/SciPy/Sionna/client/CuPy | Activate the intended virtual environment. CPU bootstrap supplies the pinned numerical/client stack; live CUDA additionally needs `.[live]` and the qualified CUDA libraries/image. The analysis-only SigMF example only needs NumPy/SigMF. |
| LLVM backend unavailable | Native CPU Sionna needs a supported LLVM shared library. Use the Docker CPU environment with `libllvm19`, or install the matching system library described in [setup](setup.md). Installing the Python wheel alone does not install the OS driver/runtime. |
| Unknown/missing JSON keys or invalid receiver setting | Correct the named field; compare a newly generated `airsim-rf example` configuration. Frequencies/rates/bandwidth are Hz, powers W, offsets metres. Do not silently rename simulator or radio IDs. |
| Robot absent / missing robot-config | The radio's `robot` must name a robot actor in the selected scene, and its robot-config path must exist relative to `sim_config`. Copy the complete generated input directory. |
| Waveform too short | Extend every TX's finite complex array for the planned actual signal duration plus interpolation margin, or reduce updates. Sources are zero outside the file; the runner now rejects accidental exhaustion before world loading. |
| Physics interval not sample-aligned | Choose a compatible steppable clock tick/sample rate. The actual nanoseconds × sample rate / 1e9 must be an integer. Merely rounding the requested update duration is insufficient. |
| Interval including overshoot exceeds `max_samples` | A 10 ms request with a 3 ms tick needs 12 ms. Shorten the request or deliberately raise the cap; default example needs 24,000 samples/window. |
| Output already exists | Choose a new recording/generation directory. Existing data is never silently overwritten. |
| CUDA unavailable / OptiX failure / NVRTC missing | Check host driver and NVIDIA Container Toolkit, expose the device with Docker `--gpus`, and use the matching dependency versions. `nvidia-smi` availability alone does not prove CUDA/OptiX/CuPy execution. Use the explicit GPU preflight. There is no CPU fallback for live recording. |
| P100 rejected by current Dr.Jit | Use the isolated P100 stack and explicit `--pascal-compat`; ordinary current Mitsuba/Dr.Jit do not provide that compatibility. Do not apply it to an unqualified version combination. |
| CUDA wheel libraries not found | Launch with `airsim-rf-cuda -m airsim_rf.live ...`, or the module form in the container quickstart. It exposes the CUDA runtime/NVRTC/cuFFT/cuBLAS wheels in the active Python environment. |
| Connection refused / client waits for server | The Python client does not start a server. Inspect your dedicated Blocks/Runtime logs and localhost ports 8989/8990. A generated shared GLB scene requires Blocks, not the flat-ground standalone Runtime. Use the documented server image and checksum-pinned assets. |
| Port already allocated | Another server owns the default ports. Use a separate host/session or arrange a dedicated server; do not stop an unrelated container. Custom port selection is not exposed in the current live JSON interface. |
| Spawn name collision / unreadable actor | Use a freshly loaded dedicated scene and unique object names. The GLB adapter detects upstream name-only failures. Inspect retained created names/server logs; partial placement is not automatically removed. |
| Geometry bundle content changed | Regenerate a complete new bundle from USD/profile. Do not patch PLY/XML/manifest files individually. |
| AirSim and static RF geometry differ / epoch changed | Stop concurrent stepping or actor edits. For an intended environment change, use a new revision, bundle, placement, RF scene, receiver and recording. Restoring the filename alone does not update cached geometry. |
| Delay/Doppler/path budget error | Retain the full error and scene parameters. Review physically required support and sampling/candidate budgets. Do not discard valid paths or lower fidelity to make the error disappear. |
| No clipping, but large I/Q error | Check RMS ADC counts. Weak signals can have substantial relative quantization error. Check source power, antenna pointing, propagation, noise and full-scale settings; no clipping alone does not prove useful resolution. |
| Timestamp/offset/file-size mismatch on read | Confirm the manifest is complete and files are immutable. A killed process, partial copy or consumer error can leave partial data. Preserve it for diagnosis; atomic recovery and live file tailing are not implemented. |
| Slow capture / callback stalls | Simulation is controlled by stepping, so wall time can exceed signal time. First-use compilation, GPU load, propagation and synchronous processing all contribute. Read `signal_seconds_per_receiver` separately from service timing; [performance limits](performance.md). |

For a reproducible report, retain the input directory and its hashes, exact
command/capture counts, `airsim-rf preflight` output, `manifest.json`, metadata,
server log and the relevant version-qualified environment. The
[capability matrix](capabilities.md) identifies behavior that remains outside
the qualified scope.
