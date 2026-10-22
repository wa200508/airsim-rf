# Project-specific usage plan — 19 October 2026

> Historical planning snapshot. Priorities 1 and 2 resumed and closed on 20 October;
> see the [closure evidence](../../results/reviews/priority1-20261020/REPORT.md).
> Priority 2 acceptance is [recorded separately](../../results/reviews/priority2-20261020/REPORT.md).
> Saved allowance readings and estimates below are dated, not current account state.

Project execution remains paused. This is planning and read-only usage analysis.
This plan supersedes treating the earlier active-hour estimates as calendar or
Astra-inference forecasts. Those hours were not calibrated to model throughput
or this account's allowance; multiplying them by an assumed minutes-per-window
would compound that uncertainty. The user's “11 minutes” was illustrative,
not a fixed measured budget.

## Measured project baseline

The local session records identify GPT-6 Astra with medium reasoning for the
following completed work. [Extracted counters](project-usage-baseline-20261019.json)
retain token totals and first/last allowance readings without copying chat text
or account identifiers.

| Completed work | Aggregate input tokens | Cached input | Output tokens (includes reasoning) | Five-hour allowance increase | Weekly allowance increase |
| --- | ---: | ---: | ---: | ---: | ---: |
| ASE standards research | 2,215,699 | 2,148,992 | 7,276 | 27 points | 5 points |
| OpenUSD implementation | 3,204,724 | 3,160,192 | 20,507 | 40 points | 6 points |
| Shared-scene GPU qualification | 4,999,152 | 4,756,736 | 17,372 | 59 points | 9 points |
| Priority estimate documentation | 288,116 | 283,904 | 1,794 | 3 points | 1 point |

Aggregate input counts include repeated context on successive calls. They are
not unique project text or entirely fresh tokens. Reasoning is already included
in output; do not add it twice. Usage readings are rounded account-wide counters,
can lag, and may include concurrent work. These are useful empirical ranges,
not precise per-turn billing attribution or a published token-to-quota formula.

Official [OpenAI pricing/usage documentation](https://learn.chatgpt.com/docs/pricing?codex-pricing-plans=individual)
gives an approximate 5–45 Astra local messages per five-hour Plus window and
says task/context/reasoning/caching affect usage. It does not supply a fixed
Astra Medium token allocation for this account. Credit/API prices must not be
used to convert the $20 subscription into a token balance.

At the latest account read: Plus; 96% five-hour used, 46% weekly used, no purchased
credits. Five-hour reset: Tuesday 20 October, 1:54 AM Eastern. Weekly reset:
Saturday 24 October, 7:51 PM Eastern. These are a dated snapshot, not future limits.
This analysis itself consumes allowance: the first read was 83% / 44%.

## Budget unit and available throughput

Use one completed implementation/qualification increment of comparable scope
to the observed examples as a **substantial batch**. Provisionally budget
40–60 five-hour percentage points and 6–9 weekly points per such batch.
These are forecasts from two relevant samples, not guaranteed ceilings.

Reserve 20 weekly percentage points for retries, planning and other usage:

- floor(80 / 9) = 8 expensive batches per week.
- floor(80 / 6) = 13 cheaper batches per week.
- Morning plus evening on five weekdays supplies 10 opportunities, provided
  the five-hour window has reset and weekly budget remains.
- Therefore plan for 8–10 substantial weekday batches, with possible weekend
  capacity if the batches are cheaper. Evening-only work supplies 5 opportunities.
- A single full five-hour window should normally cover one substantial batch
  with margin. Two are possible only near the low end; do not assume it.
- With 54% weekly remaining at the latest read and a 20-point reserve, 34 points
  remain for this project: about 3–5 more substantial batches before Saturday's
  reset, after the five-hour allowance recovers. This is not an instruction to resume.

GPU/CPU scripts without model/API calls can run for hours independently of this
budget. Their preparation, diagnosis, and model-read logs consume allowance;
the numerical execution itself does not require Astra inference. Jobs need
bounded duration, logs, result summaries, exit codes and persistence independent
of an active chat. Those operational properties must be prepared/checked before
assuming a job will finish while the user is away.

## Remaining work estimates by deliverable

These are new bottom-up planning judgments using the observed batch sizes.
They are not derived by dividing the former hour estimates by 11 minutes.
Use the high end when unknowns recur. Calendar ranges assume morning/evening
availability, most of the weekly allowance dedicated to this project, 20%
reserve, and no rebuild/lab-access blocker. Each row is an incremental duration,
not a promise that all priorities finish concurrently.

| Priority | Estimated batches | Weekly allowance equivalent | Provisional elapsed schedule | Appropriate next bite |
| --- | ---: | ---: | --- | --- |
| 1 Geometry | 6–9 substantial | 36–81 percentage points | 1–2 weeks | Implement one shared-triangle GLB adapter and its focused checks; then independently probe the runtime mesh/collision route. Subsequent batches cover moving-radio capture, revision handling and closure evidence. |
| 2 Usable local package | 6–10 mostly moderate | 18–60 points (assume 3–6 each) | 1–2 weeks | One complete setup/preflight/example path. Separate clean-install repair, interface docs, troubleshooting and acceptance matrix. No publication. |
| 3 Downstream results | 6–10 substantial | 36–90 points | 1–2 weeks | One modulated waveform and independent consumer baseline; then propagation integration, metrics and a reusable example. |
| 4 Dependable operation | 8–14 substantial | 48–126 points | 1–3 weeks plus run/retry delays | One bounded-memory or atomic-checkpoint change with fault checks. Run prepared one-minute/ten-minute cases unattended, then analyze summaries in the next batch. |
| 5 Independent accuracy | 10–20 substantial | 60–180 points | 2–4 weeks for numerical evidence | One independent reference and error budget at a time: delay/Doppler, amplitude/antenna, cadence, diffuse convergence. Hardware calibration remains a separate, access-dependent schedule. |
| 6 Performance | 8–16 substantial | 48–144 points | 1–3 weeks for initial assessment | One representative profile, then one measured optimization per batch. Achieving the full fleet/rate/budget target is still not estimable. |

Summing these provisional token budgets gives 246–681 weekly percentage points,
or about 3.1–8.6 weekly allocations at an 80-point project budget. That is a
quota-only calculation. Sequential dependencies, failed jobs, and limited
interaction make roughly 6–12 calendar weeks a more prudent initial envelope
for this set of scoped milestones. It excludes hardware calibration, a required
simulator rebuild, and guaranteed achievement of the full performance target.
Evening-only operation or competing account use can extend it substantially.
Re-estimate after the next two substantial batches; do not treat this envelope
as a commitment to finish the entire project in that time.

## Practical rhythm and calibration

- Evening: one bounded change or result analysis; save exact next action and
  prepare the next executable job. User's remaining evening time can review
  outputs/configuration without additional model calls.
- Before work: launch an already-prepared job directly, or use a fresh model
  window for one preparation batch. Numerical jobs run without continuous
  model supervision or repeated model-driven polling.
- Next evening: read a compact result summary, inspect failures only as needed,
  and decide the next change. A failed unattended job stops rather than consuming
  model allowance in an unbounded retry loop.
- Record five-hour/weekly percentages before and after each bounded batch,
  model/effort/speed, tokens, context size and the achieved deliverable. Compare
  like work, and avoid measuring across a reset or concurrent account activity.
- Keep a concise handoff and read only needed files/log excerpts. A focused new
  chat may reduce context but also starts with less cached context; savings are
  not automatic. No model or speed settings have been changed here.
- If using Fast or Ultrafast, verify that choice: official docs list 2.5x and
  8x included-allowance consumption versus Standard. Medium reasoning does not
  establish the speed setting. This plan assumes the observed workload continues
  under the same settings; it does not claim those settings were verified.
