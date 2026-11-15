# Ryan fixes: implementation handoff

Status: active handoff. Audited against main `fd5ec94` (PR #27 merged), 2026-11-15.
Prepared from local review notes, the private source plan PDFs and repository code/docs.
Give this document to a coding model one work package at a time. The local review note
and PDFs are not distributed with the public plan; obtain them from the team if needed.

## Current package status

| Package | State | Next action |
|---|---|---|
| 1 — repository protection | Merged, PR #26 (`8355532`). | Current-tree protection is done; historical cleanup requires a separate owner decision. |
| 2 — Windows execution/tests | Merged, PR #31 (`6ecf863`); the native Windows Python 3.11 CI job passed. | Done. Native Windows `make dev` stays unsupported (Docker Desktop or WSL). |
| 3 — runtime mounts/mode visibility | Merged, PR #27 (`fd5ec94`). | Narrow runtime mounts and startup messages are on main. |
| 4 — validation | Proposed policy only. | Agree the request/error matrix in `docs/DECISIONS.md` before changing behavior. |
| 5 — historical PDF recommendation | Pending shared-store handoff. | Coordinate snapshot semantics with Nergis. |
| 6 — offline vector retrieval | Merged, PR #34 (`60ea3f8`). | Follow-ups RAG-004/RAG-005 (empty-folder search, untracked bundle outputs) on `feature/ML-08-followups`. |
| 7 — documentation | Merged, PR #29 (`db5f8dd`). | Later corrections (tag status, ordering) on `feature/OPS-01-docs-followups`. |
| 8 — demo freeze | `demo-v1` exists (annotated, on `8f281d9`); later fixes need a new tag. | Agree the demo narrative, then tag `demo-v2` on an exact green SHA. |

## Baseline and findings

The initial inventory used main `8f281d9`, when the working checkout was the older
OPS-02 branch. Main subsequently acquired raw uploads in `b01b110`; PR #26 untracked
664 raw files plus two private PDFs after preserving local backups, and added guards.
PR #27 then narrowed mounts and announced mode at API startup. The table below retains
original findings as historical context; use the status table above for remaining work.
Start implementation from freshly fetched main in an isolated checkout and revalidate.
Never merge the raw-upload branch as an implementation base.

| Item in New fixes | Assessment and Ryan's responsibility |
|---|---|
| Invalid simulation inputs accepted | Confirmed: `ScenarioIn` has types but no numeric/domain constraints. Ryan owns schemas/API tests; Nergis owns the simulate router. Contract behavior changes need team agreement, already recorded as pending in OPS_NOTES. Package 4. |
| In-memory scenarios | Explicit BE-01 requirement, not an implementation defect. `store.py` belongs to Nergis, despite the note assigning this to Ryan. Keep one worker and document restart loss; persistence is a separate scope decision. |
| PDF recommendation recalculated | Confirmed and explicitly documented under BE-09. History rows remain recorded; the recommendation is labeled calculated at export time. This is a real dashboard/export consistency limitation, not an undisclosed bug. Package 5 requires a store handoff. |
| CSV/DOCX export missing | Neither is in the source plan's endpoint list; PDF is required. Defer until format, endpoint and ownership decisions are approved. |
| Native mock default | Intentional BE-06 default; Docker automatically selects real mode when artifacts exist. PR #27 added startup visibility and mode commands without changing defaults. Package 3 merged. |
| Windows entrypoint test failure | Reported, not reproduced on Windows here. Do not assume `os.execvp` is unsupported or replace Linux signal behavior based on that claim alone. Package 2 reproduces and diagnoses it. |
| Native launcher POSIX-only | Confirmed: `killpg`, sessions and POSIX signals; existing launcher tests explicitly skip Windows. Package 2 defines supported execution routes. |
| Docker lacks Chroma/cache | Confirmed: no vector-store or embedding-cache mount. `ml/ingest_rag.py` can download its local embedding model on first use, or use remote OpenAI embeddings. Ryan owns ingestion, fallback, evals and Docker. Package 6. |
| Whole data directory mounted | Historical broad mount followed OPS-02 literally. PR #27 now mounts only processed data, cited documents and artifacts read-only; this is a documented plan deviation. |
| Uploads can be staged | Fixed in PR #26: confirmed source directories and private plan names are ignored; index tests catch forced additions. Package 1 merged. |
| Public raw-upload branch | Joint repo-owner/data-owner issue. Inspected `origin/data/raw-uploads` has 692 files under data, about 150.9 MiB, including the normal pipeline files. The note's 491 MB/664 files/two oversized videos were not confirmed by this tree; inspect local files and reachable history before asserting those figures. Historical cleanup is still a separate owner decision. |
| Missing demo-v1 | Superseded: absent at the original audit, then created on 2026-11-15 as an annotated tag on `8f281d9` (PR #24 merge) after real-mode `make e2e` passed. Package 8 now tags `demo-v2`. |
| Duplicate/stale docs | Reconciled by package 7: current snapshot, corrected contract descriptions, distinct historical runs and pending-decision register. |
| Chat fallback is raw text; only ten eval questions | These match ML-10 and ML-09 respectively. Ryan owns them even though the note tags them Nergis. Improve only with an explicit additional requirement; do not call the planned behavior a missing feature. |
| Results synthetic provenance / agent_trace / POST report | Team contract decisions. Ryan coordinates schemas, API and tests; Nergis owns stored provenance; Nathan owns consumers. Package 7 records the decision without inventing fields. |
| FE-06 unmerged | Stale: PR #24 is already merged on the inspected main. No merge task remains. |

Historical repository exposure: private root plan PDFs and raw-upload files were tracked
before PR #26. They are absent from the current tree and ignored, but remain in history.
Do not attach the private documents to a public PR. Existing credential/account or local
disk issues need their respective owner's action; never put secret values in a handoff.

## Instructions every implementing model must follow

1. Read AGENTS.md, Project Overview, Implementation Tasks, SUMMARY.md, OPS_NOTES.md and
   CHANGELOG.md in that order. The PDFs are local/private. Preserve the user's work.
2. Fetch main and record the starting SHA. Check whether the assigned package has
   already landed. Work on one branch/task at a time; use explicit paths when staging.
3. Ryan owns the rest of backend, root scripts/config/CI, `ml/ingest_rag.py`,
   `backend/app/services/fallback.py`, and `ml/tests/test_evals.py`.
   Nergis owns simulate.py, store/predictor/rag/detector/suppressor services and training
   artifacts. Nathan owns frontend and the listed data pipelines/docs. Do not edit
   their files without a scoped handoff or exception. The earlier BE-11 exception
   permits only its cache integration and does not authorize new edits.
4. These are follow-ups under existing task IDs, not newly assigned plan IDs. Commit
   each independently with `TASK-ID: concrete change`; never combine unrelated work.
5. Contract changes require the team's recorded agreement, schemas/OpenAPI updates,
   frontend type regeneration and changelog updates together. Prepare the policy and
   examples first; do not silently tighten accepted requests or add row keys.
6. Run `make lint` and `make test` after each package. For frontend contract changes,
   also run typecheck, tests and build with the locked dependencies. Tests use synthetic
   fixtures and no real keys/network. Record environment failures separately; do not
   remove checks to manufacture a pass.
7. End with changed files explained in 1–2 sentences each, checks and their final
   output lines, unresolved decisions, and a reviewable diff. Publishing, merging,
   deleting remote branches, rotating credentials and rewriting history are separate
   actions requiring applicable user authorization; this plan does not request them.

## Package 1 — OPS-01: protect the public repository (merged PR #26)

Files: `.gitignore`, relevant root repository tests, optional root audit script;
tracked private PDF removals only after preserving local copies outside tracked paths.

- Inventory tracked, untracked and ignored paths without printing document contents
  or credentials. Enumerate actual upload directories, including BASS/BASS2 and any
  others discovered; do not confuse the branch name `data/raw-uploads` with a folder.
- Add narrowly scoped ignores for confirmed raw staging directories and root copies
  of the private plans. Keep processed demo data, NASA text corpus, model artifacts,
  `.env.example` and `data/raw/.gitkeep` trackable. Avoid a blanket `data/` ignore.
- Remove root private PDFs from the tracked tree while retaining private local copies.
  An ignore entry alone cannot untrack an existing file. Coordinate any already tracked
  raw uploads with Nathan; never delete the only source copy.
- Audit the proposed branch's tracked files and large blobs. For the already public
  branch/history, prepare a separate owner decision identifying affected refs. A new
  deletion commit does not erase history, and branch deletion does not guarantee removal
  from forks/caches. No force-push or history rewrite as part of this package.

Acceptance: `git check-ignore -v` proves intended exclusions and exceptions; tree checks
reject private plan copies and unintended raw uploads; `git diff --cached --stat` contains
only explicit changes. No giant files or private source text are added by this task.

## Package 2 — OPS-01 / OPS-02 / OPS-03: Windows execution and tests

Split the test/entrypoint fix (OPS-02), launcher work (OPS-01) and any CI expansion
(OPS-03) into separate commits. Files: `tests/test_container_startup.py`,
`docker/backend_entrypoint.py` only if needed, `scripts/dev.py`, `tests/test_dev.py`, CI.

- Obtain the exact native Windows traceback and invocation. Distinguish native Python,
  Git Bash, WSL and the Linux Docker engine. The current report alone is not a root cause.
- Keep mode-selection and invalid-config tests cross-platform. Test command dispatch
  with an injected/mocked exec boundary where appropriate; retain a real subprocess
  replacement/signal test on POSIX and in Linux Docker. Do not skip the entire file.
- Default supported Windows demo route: Docker Desktop Linux engine or WSL. Document a
  clear native-Windows launcher diagnostic and actionable command. If native Windows
  `make dev` support is required, implement a separate process-control strategy,
  resolving npm.cmd correctly and handling descendants, Ctrl+C and startup failures.
  Do not claim native support until exercised on Windows; mocked calls alone are insufficient.
- Add a Windows smoke CI job if needed for the chosen support policy, preserving existing
  required check names. Account for Make availability rather than assuming Ubuntu tooling.

Acceptance: mode tests pass on Windows and Linux; Linux container signals still reach
uvicorn; supported dev paths stop both servers and their reload/build descendants;
unsupported native execution exits clearly before launching partial stacks.

## Package 3 — OPS-02 / BE-05: runtime mounts and visible demo mode (merged PR #27)

Implemented in PR #27: `docker-compose.yml`, `docker/README.md`, Compose tests and
BE-05 lifespan mode announcement/tests. Startup visibility was placed in the app to
avoid editing Claude's launcher. The implementation checklist below records the target
that was met; it does not assign a new launcher edit. Strict backend 0/1 parsing remains.

- Inventory runtime readers on current main, then replace the broad data mount with
  read-only `data/processed` and `data/docs` mounts (plus any proven runtime need).
  Keep artifacts read-only and preserve missing-path/automatic-mode behavior deliberately.
  Record the narrower mounts as a change from the literal OPS-02 plan.
- Keep synthetic defaults for Phase 0. Make native and container startup messages say
  which mode is active without printing keys. Document explicit real-mode commands:
  `MOCK_MODE=0 make dev` on POSIX; `MOCK_MODE=0 docker compose up --build` on POSIX;
  PowerShell: `$env:MOCK_MODE='0'; docker compose up --build`.
- Verify precedence for shell variables and optional .env. Do not load .env in tests or
  forward backend secrets to the frontend. A visible mock mode is not evidence of a
  scientifically valid real-data demo.

Acceptance: a separate Compose project/unused ports passes health and the real E2E loop;
raw uploads are unavailable inside the backend; docs/processed data remain available;
explicit mocks and automatic missing-artifact fallback still work. Stop only the test stack.

## Package 4 — BE-05 / BE-12: validated simulation requests (team gate)

Prepare a short accepted/rejected request matrix for team agreement before changing code.
Recommended policy: finite O2 10–40 inclusive, finite flow 0–40 inclusive, positive finite
pressure, three finite direction components with nonzero norm, and material present in
the current real `/meta` catalog. Do not silently restrict to training min/max: valid
inputs outside observed data must still produce the planned extrapolation warning.
Do not invent a pressure upper bound or require unit-length vectors without a decision.

Files: `backend/app/schemas.py`, validation helper if needed, API tests and contract docs.
Nergis supplies/approves the real simulate-router hook; Nathan owns generated frontend types.

- Put static constraints in the schema, without importing data/model loaders there.
- Validate dynamic material names against the same catalog as `/meta` in real mode;
  agree case/whitespace policy. Recommended unknown-material status: 422. Distinguish
  unavailable/malformed catalog (503) from a user's unknown material.
- Keep fixed mock mode independent of real artifacts. Agree its semantic material policy;
  apply shared static schema validation consistently. Do not add real model/data imports
  to the mock path.
- Check every suppression action's generated `new_inputs` against proposed constraints
  before enforcing them: ScenarioIn is nested in response models too. Invalid requests
  must not create scenarios, append rows or call prediction/LLM services.

Acceptance: boundary and just-outside cases, NaN/Infinity representations, invalid vectors,
unknown materials, valid extrapolated inputs, missing data and all action outputs are
covered. Schemas/OpenAPI/types/tests/docs change together after recorded agreement.

## Package 5 — BE-09: export the recorded recommendation (shared store handoff)

Current export-time calculation is explicitly labeled; preserve that honesty until a
replacement exists. Do not describe the current results-history table as recomputed.

- Agree which recommendation the PDF should show: latest successful `/suppress` response
  at its original input snapshot, with any subsequently applied action shown separately.
- Nergis adds an internal store snapshot API for the returned `SuppressOut`, input snapshot
  and ordering/version metadata. Ryan's suppress router records exactly what it returns;
  PDF/export reads one consistent snapshot. Avoid a second global recommendation cache.
- Do not append invented `/results` row fields or change row ordering. Internal metadata
  can stay internal; any public shape change needs the contract gate.
- When no ranking has been requested, report that explicitly rather than manufacturing
  a historical recommendation. Stop calling the ranker from export once snapshots exist.

Acceptance: rank -> apply -> export retains the originally returned recommendation and
inputs, records the applied action separately, leaves history untouched, and performs no
new prediction/LLM/ranking call. Cover no ranking, repeated ranking, missing scenario and
snapshot isolation. Existing PDF honesty, escaping and source-label tests remain green.

## Package 6 — ML-08 / ML-10 / OPS-02: reproducible offline retrieval

Files: `ml/ingest_rag.py`, `services/fallback.py` if needed, eval tests and Docker tooling.
Nergis owns changes to rag.py/config paths; Nathan supplies corpus text and citations.

- Define the demo retrieval mode explicitly. Recommended target: prebuilt local-embedding
  Chroma plus its matching embedding-model cache, provisioned before the offline run.
  Keyword fallback remains available if the bundle is absent. Record this choice in OPS_NOTES.
- Record embedding kind/model/version and corpus fingerprint; never open a local index
  with a different embedding provider merely because an API key appeared in the environment.
  Remote OpenAI embeddings are additional network calls beyond the LLM; document them.
- Package the prepared DB and cache through a reproducible setup/build step or explicit
  optional Compose configuration. Keep the default fresh-clone startup usable when neither
  exists. Verify Chroma's write requirements as the non-root container user: do not assume
  a read-only SQLite directory will work. Prefer a writable disposable copy/volume of a
  prepared store, with corpus/artifacts still read-only.
- Prevent an offline query from triggering first-use model downloads; exercise missing or
  incompatible cache/index and coordinate a graceful keyword fallback with Nergis.
- Keep the prescribed ten-question eval and report denominator/pass rate honestly;
  test retrieval modes separately instead of allowing fallback to mask broken vector search.

Acceptance: prepared container serves cited chat/retrieval with outbound traffic blocked,
no download attempts and no keys; missing bundle has a tested fallback; incompatible
provider/cache is diagnosed. Run vector tests with Chroma actually installed. The previously
observed missing-local-chromadb test failure is an environment issue, not an FE regression.

## Package 7 — OPS-01: reconcile documentation and decision register (this update)

Files: `docs/OPS_NOTES.md`, `docs/CHANGELOG.md`, `docs/contract.md` as needed. Ask Nathan for
README/UI changes. Keep AGENTS.md and CLAUDE.md byte-identical if either needs updating.

- Preserve dated historical decisions; label superseded statements and identify the current
  behavior. Repair duplicate headings and distinguish successive test counts by commit.
- Record current retrieval modes, native-vs-Docker mock defaults, single-worker/restart-loss
  limits, actual results row shape, PDF recommendation semantics and supported platforms.
- Decision register: validation policy; historical recommendation storage; result-source
  synthetic provenance; optional CSV/DOCX; agent_trace/POST report; any persistence requirement.
  Each needs owner, proposed behavior, affected consumers and status. Do not implement future
  agent APIs or a persistence migration merely because they are listed here.
- Note that the broad raw mount, in-memory store and top-chunk offline answer follow the
  task plan. Mark deliberate improvements as new decisions rather than retroactive errors.

Acceptance: every current assertion maps to code or a recorded team decision; outdated
statements remain clearly historical; no private source documents or key values enter docs.

## Package 8 — OPS-04 / OPS-05: honest release candidate and freeze

Run last, after required fixes land. Ryan owns integration/release checks; Nergis owns
labels, training correctness and metrics; Nathan owns working controls/verdict/actions/chat.

- Select the real demo scenario with the team. Current OPS notes use Heptane at 30% O2,
  zero flow, which yields no detector alarm. Do not claim this demonstrates the planned
  burning-solid/airflow-detection sequence or fabricate cable-insulation evidence.
- Exercise real API simulate -> detect -> suppress -> apply -> results -> export and chat,
  with no keys and then the separately authorized provider smoke test. Rehearse the intended
  UI loop; a green endpoint suite alone does not establish model correctness or UI readiness.
- Verify artifacts/corpus provenance, fresh-clone startup, offline behavior, no raw/private
  files in the release tree, lockfiles, all required CI and `make lint`/`make test`.
- Record the tested SHA and known limits. Only after release authorization, create the next
  annotated tag on that exact green main commit and publish it: `demo-v2`, because `demo-v1`
  already exists on `8f281d9`. Recheck the remote tags first; never move an existing release tag.

Acceptance: reproducible run instructions, exact SHA and checks, approved demo narrative,
release tag only after all agreed gates pass. Missing scientific evidence remains a blocker
for claims that rely on it even if the software starts successfully.

## Suggested assignment order and reusable model prompt

Packages 1 and 3 are merged; Claude owns package 2. Review this package 7 update, then
advance package 6 or the prepared decisions for 4/5 within ownership boundaries. Run 8
only after agreed release gates. Separate models may take isolated
branches, but shared root docs/Compose/contracts need an explicit integrator and file ownership
to avoid concurrent edits. No model should execute another package as incidental cleanup.

> Read docs/RYAN_FIXES_PLAN.md and implement package <number> only, starting from current
> origin/main. Revalidate its findings and read the source-plan/ownership instructions first.
> Follow that package's allowed files, dependencies and acceptance checks. If a team decision
> is missing, prepare a concrete policy/patch proposal and tests for review without silently
> changing the contract or another owner's files. Preserve unrelated work and secrets.
> Run make lint and make test, plus package-specific checks. Report the exact base SHA,
> changed files, test outputs, remaining gates and a suggested TASK-ID commit message.
> Do not publish, merge, rewrite history, delete remote branches or create a release tag
> unless the user has separately authorized that action.
