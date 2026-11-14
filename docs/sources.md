# Sources

All retrieved 2026-11-11. Only single figures are quoted, with citation; no text or tables are
reproduced from government pages. Source IDs are referenced from `inputs/cost_inputs.yaml`.

| ID | Source | Where | What is used |
|---|---|---|---|
| S1 | "Designing Coordinated Services Tunnels for Environmental Health and Safety", CIB conference paper (Department of Building, National University of Singapore), CIB document DC25818. <https://www.irbnet.de/daten/iconda/CIB_DC25818.pdf> | Printed p. 257, section "Estimated overall cost" | Marina Bay CST phase 1: 1.4 km, about S$81M (completed); phase 2: 1.6 km, about S$137M (estimate at time of writing); paper's average S$72.66M/km. The model uses 218 / 3.0 = 72.67 (the paper truncates). |
| S2 | HM Treasury, *The Green Book (2026)*, HTML edition, page updated 28 Oct 2026 ("changes to the approach to discounting"). Open Government Licence v3.0. <https://www.gov.uk/government/publications/the-green-book--2/the-green-book-2026> | Chapter 6, "Discounting" | Real social time preference rate 3.00% for years 1-30, 2.50% for 31-75, 2.25% from 76. Base-case discounting. |
| S3 | "A Critical Review of the Sustainability of Multi-Utility Tunnels for Colocation of Subsurface Infrastructure", *Frontiers in Sustainable Cities* 4 (2022), doi:10.3389/frsc.2022.847819. <https://www.frontiersin.org/articles/10.3389/frsc.2022.847819> | Sections "Additional Underground Construction" and "Indoor Environment" | Tunnels reported about 80% (Barcelona) and about 50% (Pamplona) dearer to build than open-cut; 70-80% fewer maintenance interventions. The review itself says these figures are not transparently derived. Used only to shape the ranges of `db_capex_ratio` and `cst_event_reduction`. |
| S4 | Ministry of Transport, written parliamentary reply on minimising repeated road re-excavation and the feasibility of CSTs for new HDB towns, 4 Nov 2025. <https://www.mot.gov.sg/news-resources/newsroom/efforts-at-minimising-practice-of-roads-being-resurfaced-or-re-excavated-for-different-works--feasibility-of-common-services-tunnel-for-new-hdb-towns-and-major-redevelopment-zones-/> | Reply text | One-year no-opening rule on newly resurfaced roads (schedule interface); CSTs described as suited to areas with high infrastructure loads, utility-specific ducts as more suitable for HDB estates (frames the two load scenarios). No cost figures. |
| S5 | URA circular URA/PB/2021/01-DSG, 1 Mar 2021, CST Act 2018 for the Marina Bay CST Area. <https://www.ura.gov.sg/guidelines/circulars/dc21-01/> | Circular | Act in operation 7 Jan 2021; prior written approval needed for works in the CST protection zone and for laying utility services in the CST area (approvals activity in the schedule). |

## What could not be verified

- **Price year of the Marina Bay costs (S1).** The paper does not state it and its publication year is not
  shown in the extracted text (its newest references are dated 2010). Phase 2 was an estimate, not an
  outturn. No primary URA or agency page with the CST cost was found. The `escalation` assumption covers this;
  no construction cost index was applied.
- **Network length.** Other public material describes the Marina Bay network as longer than S1's 3.0 km
  (later phases); the per-km cost uses S1's own lengths and costs consistently.
- **Encyclopaedia figures.** Wikipedia's Marina Bay article repeats the S1 figures without an inline citation;
  it is not used as a source.
- **A widely cited lifecycle study of multi-utility tunnels** (Tunnelling and Underground Space Technology,
  vol. 39, 2014, doi:10.1016/j.tust.2012.02.001) could not be read: the publisher and repository PDFs returned
  HTTP 403. None of its numbers are used.
- **Singapore discount rate.** No published Singapore public-sector social discount rate was found in the time
  available; the UK Green Book is used as a cited, documented convention and the flat rate is swept 1.5-7%.
- **S3 licence.** The fetched page text did not show the licence statement; only single figures are cited.
- **Everything in `inputs/cost_inputs.yaml` with `kind: assumption`**, every schedule duration and every
  interface severity is the author's scenario assumption, not data.

## Utility corridor clearance rules (added 2026-11-14)

The corridor module's rules, each with document, clause and sourced/assumption status, are listed in
[corridor_rules.md](corridor_rules.md), generated from `inputs/corridor.yaml`. All documents were retrieved
on 2026-11-14 and read as worded; only single figures are quoted.

| ID | Source | What is used |
|---|---|---|
| C1 | LTA, *Code of Practice for Works on Public Streets*, April 2026 Edition | cl. 6.4.1 Table 6.1 minimum depth of utilities (1.0 m carriageway, 1.2 m sidetable); cl. 6.4.2(d) no service laid over another; cl. 6.5.1 no new manholes, chambers or valves on the road. The March 2022 edition gives the same Table 6.1 figures. |
| C2 | PUB, *Code of Practice on Sewerage and Sanitary Works*, 3rd Edition, March 2025 | cl. 1.2.5(a) utilities 1 m horizontally from a sewer edge when parallel and 1 m vertically when crossing; cl. 3.2.1(d) minimum sewer depth 1.5 m. |
| C3 | PUB (WSN)/PUB (CWD) *Advisory Note - Prevention of Damage to Water Pipes*, Revised Edition January 2025 | Appendix 1 para 3.A minimum cover of 1 m; para 3.C services must undercross water pipes with 1 m clearance all round. |
| C4 | PUB, *Code of Practice on Surface Water Drainage*, 7th Edition with Addendum No. 3 (April 2025) | cl. 5.5.1 services 300 mm from drainage structures; cl. 5.5.2(a) undercross a lined drain 1.0 m below invert. |
| C5 | IMDA, *Code of Practice for Info-communication Facilities in Buildings* (COPIF 2018) | cl. 11.3.1(q)(ii) 300 mm of earth between telecom pipes and power cables; cl. 11.3.1(e),(j) 110 mm nominal pipes; cl. 11.4.1(a) lead-in pipes 1 m below the roadside drain. |
| C6 | SP PowerGrid (agent for PowerGas), *Letter of Requirements for Earthworks - Gas (Low Pressure)*, form GDP-24 (0923) | cl. 2.6.15 at least 0.3 m between a low-pressure gas pipe and other services; no services directly on top of and parallel to a gas pipe. |
| C7 | PowerGas, *Requirements for Distribution Gas Pipe Diversion Works* (found as Annex B of a Singapore Food Agency tender) | Construction Phase item 4: 300 mm between gas pipes and all other services or structures. |

### What could not be verified for the corridor

- **Parallel clearance to a water main.** C3 gives a 1 m all-round clearance for services *crossing* a water
  pipe and setback distances for *structures*; no public figure for a service laid parallel to a main was
  found. The model borrows the 1 m (rule `PUB-WATER-PARALLEL`, an assumption) and reports a 0.3 m sensitivity.
- **Power cables.** SP PowerGrid's public Letter of Requirements for Earthworks near electricity cables gives
  2 m clearances for piling, drilling and earth rods, which are construction-activity limits, not a separation
  between parallel services. No public design separation between power cables and other utilities was found
  apart from the telecom rule in C5; such pairs use the 0.3 m default assumption.
- **District cooling pipes.** No public clearance rule was found; default assumption.
- **Gas.** EMA's Gas Supply Code (October 2024) was searched and has no depth or clearance figures. The 0.3 m
  figure in C6 is written for earthworks near existing low-pressure pipes and in C7 for diversion works; it is
  applied here as the design clearance. PowerGas's notes for working near gas *transmission* pipelines
  (TPOM-12) tabulate larger separations (for example 1.0 m to small water or sewer pipes, 1.2 m to 22 kV
  cables and above); transmission pipelines are not modelled.
- **Where sewer depth is measured.** C2 cl. 3.2.1(d) says 1.5 m below ground without saying to what; the model
  takes it to the invert.
- **Road reserve cross-sections.** LTA's *Code of Practice on Street Works Proposals relating to Development
  Works* (Version 2.0, April 2019) could not be opened in the time available (file too large for the fetch
  tool), so the reserve and carriageway widths, the sidetable make-up and the drain position are scenario
  assumptions and were not checked against LTA standard cross-sections or PUB drain drawings.
- **Which utilities need chambers or valves**, all outer dimensions, and all unit rates are assumptions.
- **Fibre-optic cables.** C1 cl. 6.4.2 allows shallower alternative depths for fibre-optic cables under
  conditions; this alternative is not applied.
- **Waivers.** C1 bans new manholes and valves on the road, yet LTA publishes a checklist for waiver of manholes
  on the carriageway, and sewers and mains do run under carriageways in practice. The model counts a waiver
  instead of forbidding it outright; it does not know when one would be granted.
