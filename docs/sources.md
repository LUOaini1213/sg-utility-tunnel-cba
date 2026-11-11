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
