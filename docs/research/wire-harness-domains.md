# Wire harness design domain survey

Scope: what a wire harness authoring agent must do, based on the task
taxonomy of commercial harness tools and the standards ecosystem. This is
the domain reference for `docs/adr/` and the v0.x roadmap.

## Task taxonomy

Harness design splits into six phases; the phases are sequential but feed
each other.

| Phase | Name | Tasks | Typical owner in industry |
| --- | --- | --- | --- |
| 0 | Requirements | electrical (voltages, currents, signal classes), environmental (temperature, sealing, vibration), physical (product geometry), compliance (IPC class, OEM specs) | system engineering |
| 1 | Logical design | system wiring diagram, net list, connector selection, cavity assignment, wire type/gauge selection (ambient + bundle derating), voltage drop, insulation rating, fuse coordination, shielding / twisted pair, splices | electrical engineering |
| 2 | Routing / 配策 | topology segmentation (trunk + branches), 3D path against product volume, clip/grommet/fixture seats, bundle diameter packing, static and dynamic bend radius, slack/service loops, signal-class segregation, flex endurance, abrasion/edge protection | mechanical engineering |
| 3 | Manufacturing | flattened harness drawing, formboard/nailboard 1:1 layout, cut/strip/crimp data per wire, BOM, variants/options | harness supplier |
| 4 | Verification | connectivity completeness, cavity uniqueness, ampacity, voltage drop, insulation rating, bend radius, segregation, keying, terminal compatibility, DFA review | independent authority |
| 5 | Release | continuity tester programs, work instructions, exchange-format export (KBL/VEC), revision control | production engineering |

Phases 0–1 are contract work; phase 2 needs product geometry; phase 3 is a
second deterministic projection of the same contract; phases 4–5 are
gates + release projections. A single data model can carry 0–4; phase 2's
3D path data is the only phase that needs an external geometry authority.

## Commercial tool landscape

| Tool | Logical | Routing | Manufacturing | Notes |
| --- | --- | --- | --- | --- |
| Zuken E3.series (+formboard, +topology) | yes | yes | yes | E3.cable/E3.formboard pair |
| Siemens Capital / VeSys | yes | yes | yes | aerospace + automotive |
| PTC Creo Cabling | partial | yes | partial | inside Creo MCAD |
| Siemens NX Routing | partial | yes | partial | inside NX MCAD |
| CATIA Electrical Harness (EHI) | yes | yes | yes | 3DEXPERIENCE |
| EPLAN Harness proD | yes | partial | yes | formboard focus |
| Cadonix ARCADIA | yes | partial | yes | cloud |

The industry's standard split mirrors the taxonomy: an ECAD owns the
logical layer, an MCAD owns the 3D routing layer, and a formboard tool owns
the manufacturing layer. No single tool derives authority for all three;
they exchange data through KBL/VEC or proprietary syncs. wire-agent takes
the same position: it owns phases 0–1 and 3–5 and *consumes* phase-2
geometry as a declared contract, rather than owning a 3D kernel.

## Standards and exchange formats

- **IPC/WHMA-A-620 + IPC-D-620** — workmanship acceptance and design
  classes (1/2/3); the contract records the target class.
- **USCAR-21 / LV214** — crimp performance and terminal qualification.
- **ISO 6722 / LV112, JASO D611, AVS/AVSS, FLRY, TXL** — automotive wire
  specifications: temperature class, insulation thickness, bend behavior.
- **SAE AS50881, MIL-STD-5088** — aerospace wiring practice (spacing,
  clamping, derating).
- **KBL (VDA 4964 "Kabelbaumliste")** — XML harness list exchange;
  KBL 2.4 is the bridge to VEC.
- **VEC (VEC 2014)** — VDA successor model covering modules, connections,
  topology, and variants; the long-term export target.

## What an agent layer adds

Commercial tools assume an operator clicks through each phase. An agent
turns phase 0 into a conversation, phases 1–3 into deterministic
projections of a single contract file, and phase 4 into fail-closed gates.
The LLM's role is limited to authoring and repairing the contract — the
JSON verdicts, not model opinion, decide pass/fail.
