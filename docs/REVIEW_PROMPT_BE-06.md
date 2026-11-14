# Claude Code review prompt: BE-06 mock API

Copy the prompt below into Claude Code in the BE-06 worktree.

---

Review BE-06 (Phase 0 mock API) for FireTwin, NASA Space Apps 2026, "Flame in Freefall".

Work in `/home/ota/firetwin` on `feature/BE-06`. This is a READ-ONLY repository review.
Do not edit repository files, stage, unstage, stash, commit, push, open PRs, install packages,
or switch branches. Tests may create their normal temporary fixtures outside the repository.
Do not start servers or run setup/data/train targets. Do not modify or run tests in the separate
`/home/ota/firetwin-BE-01` worktree. Do not print secrets or read real `.env` contents.

Read context first, in this order:
1. `AGENTS.md`.
2. `docs/plan/FireTwin — Project Overview.pdf`, then
   `docs/plan/FireTwin — Implementation Tasks (2).pdf`. These private PDFs are the source of truth.
   Read the overview and the shared contract, BE-05/BE-06, ownership and phase sections of Tasks.
3. `docs/plan/SUMMARY.md`, `docs/OPS_NOTES.md`, `docs/CHANGELOG.md`, `docs/contract.md`, and
   `backend/app/mocks/README.md` from this worktree.
   Do not report documented decisions as newly discovered deviations. Do assess whether a
   documented choice is wrong or risky, and explain why if you disagree.

Start with `git status --short --branch`, `git branch -vv`, `git log --oneline -10`,
`git diff --stat HEAD`, `git diff --cached`, `git diff`, and
`git ls-files --others --exclude-standard`.
Review the complete on-disk BE-06 implementation, including untracked mocks, PDF and tests.
Do not assume BE-06 has been committed. If it has, compare its commits against its BE-05 base
as well as any pending changes. Do not use an old OPS-01 commit as the sole review baseline.

Task acceptance from the plan: when `MOCK_MODE=1`, every planned endpoint responds with a fixed
mock response, and `/docs` shows every contract schema so the frontend can build against it.

Scope:
- `.env.example`, `backend/app/config.py`, and `backend/app/main.py` changes for mock mode.
- All of `backend/app/mocks/`, including `responses.py`, `router.py`, `export.pdf`, and README.
- `backend/tests/test_mocks.py` and the added mock-mode cases in `test_config.py`.
- BE-06 entries in the changelog/decision notes and free-form field definitions in `docs/contract.md`.
- Existing schemas and tooling only as needed to check compatibility. Do not reopen the entire
  OPS-01/BE-05 review unless something there specifically blocks BE-06.

Verify these behaviors independently, using the plan rather than treating tests as the specification:

1. Mode selection and app setup
   - Default mode matches `.env.example`; `0` and `1` work, whitespace behavior matches the docs,
     and malformed flags fail app construction instead of silently choosing a mode.
   - Each `create_app()` captures its settings; creating another app with a different flag does
     not change the first app's routes. Check global `app` startup/import behavior too.
   - `/health` is defined once in `main.py` and works in both modes. The feature mock router is
     mounted only in mock mode, without duplicate paths or mock code in real feature services.
   - With mode `0`, the currently unimplemented feature routes are absent and health remains.
     Do not demand later real endpoints as a condition of completing BE-06.
   - No `.env`, API key, data table, ML artifact, vector store or network service is needed for mocks.

2. Endpoints and validation
   - Exercise the full table: GET /meta, POST /simulate, POST /detect, POST /suppress, POST /apply,
     GET /results/{scenario_id}, POST /chat, GET /export/{scenario_id}.pdf, and GET /health.
   - Bodies use ScenarioIn, ScenarioRef, ApplyIn and ChatIn as appropriate; responses use the
     contract models. Missing required fields, invalid action names and malformed direction
     vectors must fail validation even though valid request values are ignored.
   - Fixed IDs, unknown-ID behavior, ignored action choices and stateless results must match the
     README and OPS_NOTES. Do not require dynamic scenario storage or model predictions in mocks.
   - Check that repeated requests and changing valid inputs do not accidentally mutate fixtures.
     Check the synthetic simulate -> detect -> suppress -> apply -> results/export handoff for
     consistent IDs, materials, inputs, probabilities, recommendations and source references.
   - `/suppress` contains all five action Literal values, is sorted by its fixed scores, and
     recommends an action actually in the list. Do not interpret placeholder scores as NASA results.

3. Contract and OpenAPI fidelity
   - Compare `schemas.py` against the PDF: models, fields, types, required nullable fields,
     defaults and Literal values. Determine whether BE-06 changes any HTTP contract behavior.
     Also check ScenarioRef, ApplyIn, ChatIn, HealthOut and the ActionName alias against the table.
   - Verify `/docs` is served and `/openapi.json` exposes all 13 named models: TestRef, ScenarioIn,
     SimulateOut, DetectOut, ActionResult, SuppressOut, ResultsOut, ChatOut, MetaOut, ScenarioRef,
     ApplyIn, ChatIn, HealthOut. ActionName is a Literal alias; it need not be a separate component.
   - Inspect endpoint request/response references and methods, not only the set of component names.
   - Do not add validators for ranges mentioned only in comments or require `extra="forbid"`;
     those remain unapproved proposals in OPS_NOTES.
   - Treat the dictionaries documented in `docs/contract.md` as a frontend handoff to review:
     verify actual keys and types, their consistency with the plan, and any undocumented assumptions.
     Fixed Pydantic schemas alone do not validate the contents of `list[dict]` and `dict` fields.
   - Check the training key `flow_cm_s` versus request key `flow_speed_cm_s`. Assess the documented
     open question about ML-03's per-fuel ranges without requiring BE-07's real transformation now.

4. Recent handoff changes and synthetic honesty
   - Results rows use exactly step, inputs, state, probability, trust, detection_s, action, sources.
     Steps are numbered 1, 2, 3. Detection has no new verdict: its state/probability/trust are null.
     Verify the mock shape matches the documented BE-01 output shape; do not require its store
     implementation to be present or imported in this worktree.
   - Results rows currently have no row-level is_synthetic flag. Every row, including detection,
     carries synthetic sources, and the documented badge rule derives row status from those sources.
     Evaluate whether that representation preserves the plan's honesty rule; do not silently
     assume a row-level flag exists or demand extra keys merely to match an older fixture version.
   - Every TestRef must set is_synthetic=true. Check synthetic flags on other free-form fixture
     dictionaries and explicit labels on verdicts, detector notes, actions, chat and PDF output.
   - Verify fixture sources are clearly placeholders rather than fabricated NASA citations,
     and weak trust, extrapolation and unsupported action data are honestly represented.
   - The frontend prototype exists but is owned separately and is not wired by BE-06. Review
     backend badge signals and the handoff instructions; do not require frontend implementation here.

5. PDF, layers, tests and documentation
   - Export must return a valid, nonempty PDF fixture with application/pdf and an attachment header.
     Inspect the PDF structure beyond its extension and make sure its visible content is labeled
     synthetic and consistent with the sample outcomes. OpenAPI must document PDF rather than JSON.
   - This is a fixed asset; do not require a ReportLab renderer or per-request PDF generation (BE-09).
     Confirm the mock PDF is eligible for Git while private docs/plan PDFs remain excluded/untracked.
   - Mock code stays in mocks/. Services never import FastAPI, data scripts never import backend,
     and imports use app..., not backend.app.... Judge ownership using the reviewed worktree's notes.
   - Check docs against actual code, including shared health, numbered steps, source-derived badges,
     default/disabled mode and fixed responses. Treat documented decisions as reviewable, not exempt.
   - Assess the default-on mode's documented deployment risk without turning this review into OPS-02.
   - Check tests prove behavior with no network, real keys or new packages. Identify important
     missing BE-06 cases, but do not request the later comprehensive real-mode BE-12 test suite.
   - Check AGENTS.md and CLAUDE.md are byte-identical and the pending change adds no secrets,
     personal email addresses or private plan PDFs to this public repository.

Run the required checks with existing dependencies and no repository caches:

```sh
cd /home/ota/firetwin
UV_NO_SYNC=1 UV_NO_CACHE=1 UV_OFFLINE=1 RUFF_NO_CACHE=true PYTHONDONTWRITEBYTECODE=1 make lint
UV_NO_SYNC=1 UV_NO_CACHE=1 UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' make test
```

Report environmental limitations honestly. Earlier sandbox runs hung on Python asyncio thread
wakeups even without FireTwin; the same tests passed outside that sandbox. Do not assume such
a hang is an application defect, install packages, or weaken tests to get a passing result.

Output:
- One line each for git state, lint result and test result, with the checks' final output lines.
- Findings in severity order: blocker / should-fix / minor, file:line, the defect, a concrete
  failure scenario, and a suggested fix. Do not apply fixes or invent issues to fill categories.
- A short status/evidence list for the recent shared-health, results-shape and free-form-contract changes.
- A separate "Plan deviations not in OPS_NOTES.md" list.
- Agree/disagree verdicts on the BE-06 decisions in OPS_NOTES, with reasons for disagreements.
- Explicitly state when a category has no findings. End with whether BE-06 is ready for handoff.
- Recheck git status and confirm the review caused no unintended repository changes.
