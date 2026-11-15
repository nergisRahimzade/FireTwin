# Pending decisions and implementation boundaries

Audited against main `fd5ec94` (PR #27 merged), 2026-11-15. This is a proposal register,
not an approval record. None of these entries changes schemas, validation, stored rows,
frontend types or endpoint behavior. Record the decision, participants and date here
before implementing an agreed contract change, then update all consumers under rule 3.

| Decision | Current behavior / proposed next step | Owners and affected consumers | Status |
|---|---|---|---|
| Simulation validation | Typed `ScenarioIn` accepts values beyond the commented ranges and unknown materials. Agree the request/error matrix below, then constrain static inputs and validate material against real `/meta`. | Ryan: schemas/API/tests; Nergis: simulate router and action outputs; Nathan: controls/generated types. | Proposed, team agreement not recorded. Package 4. |
| Historical PDF recommendation | Export recomputes a labeled recommendation from current inputs. Proposed: preserve the exact latest successful `/suppress` response and its input snapshot; export it separately from later applied actions. If no ranking was requested, say so. | Nergis: internal store snapshot; Ryan: suppress/export/PDF; Nathan: displayed recommendation. | Pending shared-store handoff and agreed semantics. Package 5. |
| Results synthetic provenance | `sources` is a list of test-ID strings, not `TestRef` objects. IDs alone do not reliably carry synthetic status. Choose full references, a row flag, or an explicit provenance lookup before changing consumers. | All three: stored rows, mocks, results/PDF and frontend badges. | Open contract decision; naming conventions are insufficient. |
| Other inline provenance fields | Contract text intends synthetic flags for citation/detector dictionaries, but real producers omit them; detectors also include `time_s`. Decide how to label derived/illustrative values and whether to align producers with the documented keys. | Nergis: detector/RAG; Ryan: contract/API regressions; Nathan: labels/badges. | Confirmed implementation gaps, not an approved field removal. |
| Offline vector provisioning | Default Docker runs keyword fallback; no index/cache is mounted. Prepare a compatible local-embedding index/cache before offline use, preserving a working missing-bundle fallback. | Ryan: ingest/Docker/fallback/evals; Nergis: RAG/config integration; Nathan: corpus. | Proposed bundle/runtime policy. Package 6. |
| Durable/multi-worker scenarios | BE-01 explicitly uses process memory. Keep a single API worker and disclose restart/reload loss. Select persistence only if product scope requires it. | Nergis: store; Ryan: deployment/API/cache semantics. | Additional scope; no persistence migration approved. |
| CSV/DOCX export | Plan requires PDF, which exists. Agree format, provenance, route and response behavior if additional formats are wanted. | Ryan: export; Nathan: download UI; team: scope/contract. | Deferred additional scope. |
| agent_trace / POST report | No such public field or endpoint exists. Internal pipeline stages are not an HTTP contract. Define payload, access, sources, failure behavior and consumers before proposing an API change. | Team: contract; Nergis: pipeline behavior; Ryan: API; Nathan: UI. | Proposed future scope; not approved by this register. |
| Suppression ordering and risk assumptions | Code/schema/frontend comment now agree on data-backed-first ordering with water mist last. Confirm scientific assumptions separately; documentation agreement does not validate illustrative risk weights. | Nergis: ranker/assumptions; Ryan: API/export tests; Nathan: ordering and labels. | Implemented ordering documented; any policy/tuning change needs team review. |
| Real demo narrative and release | `demo-v1` exists on `8f281d9`. Since the solid-model fix (main `20bf3a9`), PMMA rod at 21% O2 and 10 cm/s runs the whole flow on real data: burning (p = 0.96, strong trust), `vent_fwd` alarm at 40 s, `fans_off` recommended, extinguished (p = 0.13); the e2e loop now defaults to it. Heptane 30% O2 fans off remains a no-alarm example. | Nergis: labels/model/evidence; Nathan: UI; Ryan: E2E/release. | Full flow verified in code; team confirmation of the narrative and `demo-v2` authorization pending. |
| Private plan PDFs in the public `demo-v1` tag | `demo-v1` points at a commit that still contains both private root plan PDFs (no raw uploads); GitHub serves tag source archives publicly. Options: keep; delete the tag and tag a clean commit as the demo (copies already fetched or cached remain); make the repository private. | Nergis: plan author; repository owner. | Owner decision pending; no action taken. |

## Proposed simulation validation matrix (package 4)

This table is an implementation handoff for agreement. These are **proposed** responses,
not a description of existing validation. Request numbers must remain distinguishable
from model predictions and dataset bounds.

| Case | Proposed result | Required check / unresolved detail |
|---|---|---|
| Finite O2 10 or 40%, finite flow 0 or 40 cm/s, known material, positive pressure, nonzero finite 3-vector | Accept static boundaries; run prediction. | Do not imply that all combinations have direct NASA evidence. |
| O2 below 10 or above 40; flow below 0 or above 40 | HTTP 422 before prediction/store writes. | Update schema/OpenAPI/type generation and all nested action outputs together. |
| Pressure zero, negative or nonfinite | HTTP 422. | No invented pressure maximum; any additional physical bounds need agreement. |
| Nonfinite O2/flow/vector components | HTTP 422, including invalid numeric encodings where parsed. | Cover NaN/Infinity input and ensure no nonfinite result escapes JSON serialization. |
| Zero vector, wrong-length vector, nonfinite component | HTTP 422. | Non-unit finite vectors remain valid unless the team explicitly chooses normalization/restriction. |
| Material absent from real `/meta` catalog | HTTP 422 before creating a scenario or invoking predictor/LLM. | Agree case/whitespace handling; use the same catalog source as `/meta`. |
| Real catalog unavailable or malformed | HTTP 503, distinct from unknown material. | Never invent a fallback material or turn server data failure into user input error. |
| Valid API-domain inputs outside observed training bounds | Accept and return existing extrapolation/trust behavior. | Do not reject merely because `/meta.ranges` or training support is narrower. |
| Mock request | Shared static validation; no dependency on real catalog/artifacts. | Agree whether mocks enforce their own material name or keep ignoring valid material strings. |
| Suppressor-generated `new_inputs` and `/apply` output | Must remain representable under agreed schemas. | Review all actions before constraining the shared request/output model; do not silently clamp actions. |
| Extra request fields | Preserve current behavior until explicitly decided. | `extra="forbid"` is a separate pending policy; do not add it incidentally. |

Record agreement here with date, participants, accepted matrix changes and implementation
PR. No entries above currently assert that all three teammates have agreed. Implementation
must include error, boundary, catalog, no-side-effect and action-compatibility checks.

### Verified findings before agreement (2026-11-15, real mode, code as on main)

| Request to `POST /simulate` | Result today |
|---|---|
| `o2_pct` = `NaN` or `Infinity` (JSON literal) | 422 from `model.burn_probability` ("not a finite number") |
| `o2_pct` = 150 | 200, burning, p = 0.9999999999 |
| `flow_speed_cm_s` = -3, `flow_dir` = `[0, 0, 0]`, `material` = `"Nope"`, `pressure_kpa` = -1 | 200 with a verdict |

- **Action outputs vs request bounds.** `ScenarioIn` is also the type of `SimulateOut.inputs` and
  `ActionResult.new_inputs`. CO2 lowers O2 by `CO2_O2_DROP_PCT` = 6 (`ml/pipeline/stages.py`), so a
  request at O2 10-16 yields CO2 outputs at O2 4-10. With bounds on the shared model, Pydantic
  doesn't re-check `model_copy(update=...)` results, so the API would return 200 with values that
  break its own published schema. Options: (1) bounds on the `/simulate` request model only
  (recommended; contract change, needs the simulate router signature); (2) an O2 floor that covers
  action outputs; (3) floor CO2 output at 10 (a science/ranking change).
- **Side effects.** `routers/simulate.py` calls `store.create()` before predicting, so the 422
  requests above still create an empty scenario. "No side effects" needs validation (including the
  material check) before `store.create()`.
- **Material check location.** The schema must not import data loaders, so the catalog check needs a
  simulate-router hook calling the same catalog as `/meta`; unknown material (422) stays distinct
  from an unavailable catalog (503).
- Open questions for agreement: which option above; whether the router validates before
  `store.create()`; material matching (exact or case/whitespace-insensitive).
