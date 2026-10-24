# Open standards for the geometry broker — 18 October 2026

**Follow-up selection:** the [ASE/Open Arsenal review](ase-standards-selection-20261018.md)
selects AMS GRA RF MEL, OMS/UCI/CAL and DIS for ecosystem interoperability.
OpenUSD remains a supplementary geometry choice. FMI/HLA/DDS are deferred.
Use that review for the current broker direction.

Status: researched recommendation, not implemented conformance. This review
used primary sources and did not access the GPU or running simulator.

## Recommendation

Use **OpenUSD as the proposed external scene interchange foundation**, with a
small documented RF extension/profile. Keep source and target adapters separate.
Treat the newly added JSON geometry format as a provisional internal normalized
snapshot, not a competing long-term public scene standard.

There are three distinct concerns: scene meaning, simulation coordination and
data transport. None of the reviewed standards supplies a ready-made, complete
AirSim-to-Sionna broker including RF materials, sample timing and runtime state.
The ranking below is an engineering judgment based on the documented scopes.

## Candidates

| Candidate | Relevant scope | Recommendation for this project |
| --- | --- | --- |
| OpenUSD | Scene composition, geometry, transforms, time-sampled attributes and extensible schemas | First choice for scene interchange. Define a supported subset and RF profile; retain a conversion adapter for Sionna. |
| glTF 2.0 | Portable scene/asset delivery, meshes, node transforms and animation | Useful asset import option. Prefer USD for the authoritative composed scene and separate RF overrides. |
| FMI 3.0 Co-Simulation | Model interfaces, lifecycle, communication steps and clocks | Candidate for a later external co-simulation adapter. Do not make FMU packaging a prerequisite for the geometry milestone. |
| IEEE HLA | Distributed simulation federation and runtime infrastructure interfaces | Revisit if users need federation with existing simulation systems. It does not replace scene asset interchange. |
| ASAM OSI / OpenSCENARIO / OpenDRIVE | Driving sensor/ground-truth interfaces, scenario behavior and road networks | Optional domain adapters when required by a consumer. Too specialized to define this general RF scene bridge. |
| OMG DDS | Typed publish/subscribe communication with QoS | Potential transport for state updates; does not supply geometry or RF semantics. Selecting it does not eliminate the need for a scene/time contract. |

OpenUSD supports layers, references, mesh/transform schemas and domain extension.
This would let RF assignments live separately from environment assets, with
explicit binding and provenance. [OpenUSD introduction](https://openusd.org/release/intro.html).
AOUSD published Core Specification 1.0 as an open standard; that core must not
be confused with blanket standardization or interoperability of every higher-level
geometry/physics schema and application plugin.
[AOUSD announcement](https://aousd.org/news/core-spec-announcement/).

glTF is a credible alternative for exchanging meshes and animations. Our
preference for USD is based on scene composition and overrides, not a claim
that glTF cannot represent moving objects or extensions.
[glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html).

FMI defines model packaging and interfaces, including co-simulation stepping
and clocks. It would need actual wrappers and capability declarations; using
similar method names would not establish compliance.
[FMI 3.0.2 specification](https://fmi-standard.org/docs/3.0.2/).
HLA defines federation architecture and RTI interfaces; the IEEE listing offers
the normative text through purchase/subscription, unlike freely readable FMI.
No claim of complete HLA requirements review is made here.
[IEEE HLA](https://standards.ieee.org/ieee/1516/6687/).

ASAM's scopes are documented in its
[OSI guide](https://www.asam.net/fileadmin/Standards/OSI/ASAM_OSI_User-Guide_v3.5.0.html),
[OpenSCENARIO scope](https://openscenario.asam.net/ASAM_OpenSCENARIO_DSL/current_dsl_v2.x/scope.html)
and [OpenDRIVE overview](https://www.asam.net/standards/detail/opendrive/).
The cited OSI guide is version 3.5.0 and used for scope, not a claim about the
latest version. DDS provides communication services and QoS, rather than a
domain-specific RF world model.
[OMG DDS](https://www.omg.org/spec/DDS/),
[OMG overview](https://www.omg.org/intro/DDS.pdf).

## Fit with the two upstream projects

Unreal documents USD Stage and Python workflows, including source-file updates.
Its documentation labels the feature Beta. This establishes an available
integration route, not proof that the currently installed ProjectAirSim/Blocks
build includes the plugin or preserves every property we need. Check the exact
engine/build and collision geometry behavior before selecting an adapter.
[Epic USD documentation](https://dev.epicgames.com/documentation/unreal-engine/universal-scene-description-in-unreal-engine).

Sionna RT 2.2.0 documents Mitsuba XML scene loading. Therefore the proposed route
is USD → validated normalized geometry → version-specific Sionna adapter.
Do not assume native USD loading. Its loader can merge shapes sharing materials
by default: preserve moving-object identity by explicitly selecting merging
behavior and maintaining a source-ID-to-target-object mapping.
[Sionna scene API](https://nvlabs.github.io/sionna/rt/api/scene.html).

The existing PLY/XML exporter can remain a target adapter. It has not been
runtime-qualified and must not be presented as an implemented USD bridge.

## The RF extension still needed

I did not identify a ratified, general RF material interchange schema in the
reviewed USD/glTF sources. This is a bounded research finding, not proof that
none exists. Optical PBR properties are insufficient evidence for microwave
material behavior; do not derive RF conductivity from visual metallicness or
diffuse scattering coefficients from a texture's roughness value.
[Khronos PBR description](https://www.khronos.org/gltf/pbr).

Define a versioned project RF profile with material bindings, permittivity and
conductivity models, frequency units and validity ranges, provenance and explicit
scattering-model identifiers/parameters. Support model references or sampled
tables without embedding arbitrary executable callbacks in scene assets.
Sionna's materials expose frequency-dependent parameters and scattering options,
which the adapter must translate with explicit unsupported-feature errors.
[Sionna radio materials](https://nvlabs.github.io/sionna/rt/api/radio_materials.html).

Initially this profile can use documented namespaced USD attributes or a
sidecar keyed by stable source IDs. It is our extension, not an AOUSD-approved RF
standard. A formal applied schema can follow once the semantics are exercised.
Preserving extension data through an Unreal import/export cycle is a required
check; namespacing alone does not guarantee preservation.

## Broker responsibilities that remain ours

- Declare stage units/up-axis and an explicit world-to-NED mapping. USD unit
  metadata does not automatically reconcile differently scaled references.
  [USD linear units](https://openusd.org/release/api/group___usd_geom_linear_units__group.html).
- Specify collision versus render geometry, selected LOD, triangulation,
  instances, winding, transform composition and supported deformation.
- Preserve stable logical IDs across asset revisions and adapter-generated
  names; USD prim paths alone are not guaranteed persistent through edits.
- Assign state authority: simulator owns dynamic poses, the source asset owns
  topology, RF configuration owns electromagnetic properties.
- Associate each complete snapshot with simulation epoch/time, scene revision,
  pose state and material revision. Reject mixed or stale revisions before
  tracing; distinguish simulation time from wall time.
- Declare supported versions/capabilities and migrations. An upgrade must
  surface unsupported semantics rather than silently omit them.

## Proposed next increment

1. Document a narrow USD profile: static triangular meshes, instances, rigid
   transforms, explicit units/axes, stable IDs and RF material bindings.
2. Add an optional CPU-only USD importer into the existing normalized snapshot.
   Preserve source identities and report unsupported features explicitly.
3. Build a shared example and CPU conformance checks for transforms, winding,
   materials, revisions and data loss. Do not require users to author raw USD.
4. Determine the exact Unreal/ProjectAirSim source-adapter route using local
   build information, without contacting or changing the active simulator.
5. Qualify both runtime adapters when resources are available. Keep live
   scheduling separate; adopt FMI/HLA only for a concrete integration need.

No dependencies were installed and no runtime code was changed for this review.
The existing priority order remains geometry, usable packaging without delivery,
downstream results, endurance, physical accuracy, then performance.
