# ASE / Open Arsenal standards selection — 18 October 2026

Status: selected design direction, not implemented conformance or certification.
This supersedes the generic broker recommendation in the earlier standards
survey. No GPU access, simulator calls, running-service changes, dependencies,
tests or benchmarks were involved. Packaging remains local; do not deliver.

## Selection

Make the bridge an **AMS GRA-facing simulated RF aperture with separate scene
and simulation-truth adapters**. The audience is RF/SDR engineers and algorithm
developers who should be able to substitute this source for a hardware or
starter-kit source without rewriting their processing algorithm.

| Responsibility | Selected alignment | Boundary |
| --- | --- | --- |
| RF capability, control and data access | AMS GRA v14 RF MEL IDD, common MEL and pinned interface headers | Skill-facing C++ MEL API and truthful capability metadata; AirSim/Sionna details remain behind it. |
| RF data packaging | RF MEL Jobs-based protocol first for scheduled captures; AMS-tailored VITA 49.2 for endpoints requiring that profile | Define one explicit endpoint profile and metadata semantics at a time. Generic VITA or DIFI compatibility is not sufficient evidence of the AMS profile. |
| Mission control/status and processed products | OMS/UCI through CAL; existing Sleet LA-CAL/OWP integration profile | Reuse the ecosystem's bus implementation. UCI is a message model; WebSocket/JSON is the starter-kit binding, not a universal UCI requirement. |
| Simulation truth exchange | DIS, retaining the project's v7 EntityState boundary and evaluating required emission PDUs | Match Supercell/Squall/Graupel interoperability; retain an explicit simulation-time contract. DIS entity updates do not supply the detailed RF mesh/material scene. |
| Scene assets and composition | OpenUSD with a small project RF profile | Selected supplementary geometry technology, not an ASE-endorsed or mandated format. Feed a version-specific Sionna adapter. |
| User packaging | AMS GRA Development Kit concepts and explicit compatibility profile | Interface libraries/profiles, runnable examples, setup, documentation, dependency/license inventory and conformance evidence. Prepare locally without publication. |
| Future autonomy-facing integration | A-GRA 6.0a's relevant UCI extensions and message interactions | Optional adapter for an actual consumer; do not claim a full A-GRA vehicle/autonomy implementation. |

FMI, HLA, DDS and ASAM interfaces are deferred. They remain possible adapters,
but adding them now would introduce another integration stack without evidence
that this starter-kit workflow needs it. Do not replace Sleet with a new broker.

## Evidence reviewed

Downloaded document/source hashes are saved in the
[source manifest](ase-standards-sources-20261018.json). Full downloaded documents
were kept in `/tmp/airsim-rf-standards-20261018` for this review; those temporary
copies are not a durable dependency. Repository commits and paths below identify
the reproducible sources.

The ASE affiliation is confirmed by the
[Open Arsenal about page](https://open-arsenal.gitlab.io/about/) and the
[Air Force release announcement](https://www.afmc.af.mil/News/Article-Display/Article/4558599/air-force-accelerates-warfighter-tech-releases-foundational-open-architectures/).
Public code, architecture publications and interface standards were considered
separately; a tutorial or working example is not itself a conformance assessment.

### Published architecture and interface documents

Read relevant sections of the following public documents from the
[AMS GRA repository](https://github.com/open-arsenal/ams-gra) at commit
`3645c6916761bd32ef0be8735fa6e741bada9a49`:

- `Interface_Description_Documents/RF_MEL_IDD.pdf`, v14.0, 24 April 2026:
  chapter 3 supports both Jobs-based and AMS-tailored VITA 49.2. Sections
  3.2.1–3.2.3 describe VITA 49.1 framing and profile tailoring. Direct External
  Access uses the tailored VITA path; other listed endpoint types allow both.
- `Architecture_Volumes/Software_Architecture.pdf`, v14.0, section 2.3:
  Development Kits support third-party development and differ from Starter Kits.
- `Architecture_Volumes/Time_Distribution.pdf`, v14.0, chapter 2:
  PTP, Distributed Guaranteed Time and OMS legacy timing serve distinct roles.
  Simulation epochs/sample clocks must remain explicit; do not start PTP or
  change host clocks merely to simulate this architecture.
- `Compliance_Artifacts/Compliance_Assessment_Approach.pdf`: inspected the
  assessment/tailoring discussion. Compatibility with an example library does
  not establish full architectural compliance. Document scope and deviations.

Read the A-GRA Start Here guide and relevant ICD sections from
[A-GRA](https://github.com/open-arsenal/a-gra) at commit
`aaabf2cd5c341002e6c62d1448460b55b5634931`. The 6.0a ICD section 3.3 places
onboard VI/MS interfaces on OMS CAL without prescribing a particular CAL or
serialization implementation. Its offboard C2/Peer interfaces specify EXI 1.0.
The architecture uses UCI plus autonomy extensions and defined interaction
sequences. Do not apply the starter-kit JSON binding indiscriminately to these
offboard interfaces, or mix published UCI/A-GRA schema versions without checking
their relationship. This was a boundary review, not an exhaustive review of
autonomy functions or all 6.0a interactions.

The [public UCI repository](https://github.com/open-arsenal/uci) publishes v2.5
and explains technology-independent messaging. Select the actual schema version
required by each pinned integration profile; newer is not automatically compatible.

### Open-source implementation

The [starter-kit architecture](https://open-arsenal.gitlab.io/ams-gra/hello-world-sk/getting-started/architecture.html)
uses DIS for truth, MEL for sensor data and OMS LA-CAL for UCI. Supercell supplies
truth; Squall generates sensor data; Sleet routes mission messages; Graupel and
Worldview visualize truth and perceived state. Its architecture page contains
unresolved notes about tick rates and RF metadata, so these are not treated as
verified wire-format requirements.

Fetched and read the following at the existing [source pins](../../../sources.json):

- Squall `interfaces/squall-rf-mel-impl/src/SquallDataMEL.cc` at
  `b3d4aa780de954e39bf2c6dbd7b0121f699822b4`: callback decodes bare little-endian
  interleaved ComplexINT16, constructs empty `ProductRxMetadata`, and supports
  only that sample type in this path. External RX endpoint registration is stubbed.
- Supercell `Cargo.toml` at `d46e0819f425faf09feecd453093c6f0d094a6e5`:
  DIS publisher using `dis-rs`.
- Sleet `README.md` at `e3c2d798a229766571ed7be1f5b28d2dcdb51868`:
  LA-CAL, OWP WebSocket operations and UCI schema validation.
- Worldview `README.md` at `efedd54301c76bde6795d3c4ec07ed55fe61dec1`:
  CesiumJS, DIS-derived CZML, UCI and offline map support. This is visualization
  evidence, not proof of a shared RF triangle/material format.

The [MFA tutorial](https://open-arsenal.gitlab.io/ams-gra/hello-world-sk/getting-started/tutorials/3-build-mfa.html)
illustrates VITA packetization, while the pinned decoder above implements a
simpler transport. Preserve the latter as an explicitly named starter-kit
compatibility mode. Do not insert packet headers into its datagrams, call it a
complete VITA implementation, or silently substitute it for the normative Jobs
protocol. A new standards-profile endpoint needs its own adapter and evidence.

Our existing integration already has a fixed-profile radar MEL backend and DIS
publication. It does not establish general continuous SDR integration, complete
platform UCI reports or full AMS/A-GRA compliance. The new bridge must build on
that boundary without overstating its current scope.

## Consequences for the geometry milestone

OpenUSD remains useful because the reviewed ASE documents and starter-kit sources
do not establish a detailed environment mesh/material interchange contract for
this use case. This is a limited finding, not a claim about every ASE publication.
USD should be an offline authoring/interchange layer, not the mission bus.

The geometry broker should maintain a mapping between source object IDs, USD
prim paths, DIS entity IDs, OMS/UCI system/subsystem identities and RF aperture
identities. Not every wall needs a DIS entity or UCI service. Associate moving
platform geometry with published entities; keep static environment assets in
the scene package. Use explicit geodetic anchor and NED/ECEF/RF transforms.

DIS updates supply state but not a global lockstep barrier or the complete RF
sample epoch. Preserve authoritative local snapshots and simulation time for
RF generation, and publish compatible truth outward. Define ownership to avoid
AirSim and Supercell simultaneously controlling the same entity. Future DIS
ingestion needs an explicit stale-data/interpolation policy.

Keep immutable environment geometry, dynamic transforms and RF configuration
separate. Update adapters independently when AirSim, Sionna or AMS interfaces
change. Reject unsupported semantics and preserve exact version/provenance data.

## Work order and acceptance

1. Continue geometry matching with shared assets and explicit frame/identity
   mappings; make the proposed USD profile compatible with these boundaries.
2. During consolidation, prepare a local developer kit with pinned MEL/OMS
   profiles, a capability matrix, examples and documented extension points.
3. Demonstrate a comms-oriented consumer through the selected MEL interface;
   keep mission reports on CAL and raw I/Q on its separate data interface.
4. Close timestamp/metadata, endurance and physical-validation gaps in the
   existing priority order. Performance remains last.

Before claiming conformance, map each supported interface to exact IDD sections,
record unsupported features, and exercise the relevant reference consumer. The
selection does not authorize delivering the package or interrupting the GPU job.
