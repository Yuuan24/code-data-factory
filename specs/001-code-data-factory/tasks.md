---

description: "Dependency-ordered implementation tasks for Code Data Factory"
---

# Tasks: Code Data Factory

**Input**: Design documents from `specs/001-code-data-factory/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, and
`.specify/memory/constitution.md`

**Tests**: Tests are included because the specification explicitly requires unit, contract, integration,
fail-closed, equivalence, and evidence-level validation. Within each user-story phase, write the listed tests first,
confirm that they fail for the intended reason, then implement the corresponding behavior.

**Organization**: Tasks are grouped by user story so each story has an independently reviewable output and test.
`US` means user story（用户故事）; `[P]` means the task can run in parallel with other `[P]` tasks in the same
wave because it writes different files and depends only on completed earlier phases. `MVP` means minimum viable
product（最小可行产品）. `CPU` and `GPU` mean central processing unit（中央处理器）and graphics processing
unit（图形处理器）. `SFT` means supervised fine-tuning（监督微调）; `RL-ready` means the data has a
replayable reward contract but does not imply reinforcement learning was executed.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel after the phase prerequisites are complete
- **[Story]**: Maps implementation work to `US1`–`US5` from `spec.md`
- Every checklist item names the exact repository path it creates or changes

## Path Conventions

- Python package: `src/code_data_factory/`
- Automated tests and fixtures: `tests/`
- Versioned runtime policy: `configs/`
- Generated contract schemas: `schemas/`
- Reproducible data pipeline: `dvc.yaml` and `dvc.lock`
- Challenge, decision, and evidence journal: `docs/evidence-journal.md`
- Runtime artifacts: `data/`, `artifacts/`, and `reports/`（not committed except explicit fixtures or examples）

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish a reproducible Python project and repository boundary before any evidence-bearing work.

- [ ] T001 Initialize Git version control and ignore generated, credential, model, cache, `.codex/`, `data/`, `artifacts/`, and `reports/` content in `.gitignore`
- [ ] T002 Create the package and test directory skeleton with import markers in `src/code_data_factory/__init__.py`, `src/code_data_factory/py.typed`, and `tests/__init__.py`
- [ ] T003 Define Python 3.12, the `cdf` console entry point, runtime dependencies, development dependencies, Ruff, mypy, pytest, and coverage settings in `pyproject.toml`
- [ ] T004 Resolve and freeze the Linux-compatible dependency graph, including Ray Data 2.58.0, in `uv.lock`
- [ ] T005 Initialize Data Version Control（DVC）and declare placeholder source/build/publish dependencies without generated outputs in `.dvc/config` and `dvc.yaml`
- [ ] T006 Record the owner-approved GPU budget scope, separate Ray CPU/storage cap placeholder, evidence defaults, and local paths without implicit monetary defaults in `configs/project.yaml`

**Checkpoint**: `uv sync --frozen`, `uv run cdf --help`, and `dvc version` can be executed without creating a claim or external run.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement the shared contracts, deterministic serialization, artifact handling, and command envelope used by every story.

**⚠️ CRITICAL**: No user-story implementation starts until this phase passes its contract tests.

- [ ] T007 [P] Write failing tests for canonical JSON, SHA-256 identifiers, UTC timestamps, integer-fen money, contract-version rejection, and immutable terminal states in `tests/contract/test_common_contracts.py`
- [ ] T008 [P] Define evidence, governance, verification, run, finding, usage-scope, dataset-status, task-package, candidate-generation, and reward enumerations in `src/code_data_factory/contracts/enums.py`
- [ ] T009 [P] Implement `ArtifactRef`, content-addressed identifier helpers, UTC timestamp validation, and command response models in `src/code_data_factory/contracts/common.py`
- [ ] T010 [P] Implement source, sample, transformation, quality, deduplication, contamination, slice, dataset, membership, task-package, candidate-generation, reward, and deletion-ledger models in `src/code_data_factory/contracts/data.py`
- [ ] T011 [P] Implement executor preflight, verification attempt, verification summary, and test-strength models in `src/code_data_factory/contracts/verification.py`
- [ ] T012 [P] Implement SFT experiment plan, model selection, single-GPU calibration, budget, training-run, evaluation-run, finding, and data-action models in `src/code_data_factory/contracts/experiments.py`
- [ ] T013 [P] Implement Ray cluster preflight, data-pipeline run, operator metric, Ray budget, and scale-benchmark models in `src/code_data_factory/contracts/distributed.py`
- [ ] T014 [P] Implement published-claim, lineage-index, research-source, and reproduction-run models in `src/code_data_factory/contracts/evidence.py`
- [ ] T015 Implement canonical JSON/YAML encoding, row-level Parquet logical hashing, blob hashing, and atomic manifest commit helpers in `src/code_data_factory/contracts/serialization.py`
- [ ] T016 Generate versioned Pydantic JSON Schema and PyArrow schema snapshots with a compatibility check in `src/code_data_factory/contracts/schema_export.py` and `schemas/1.0.0/`
- [ ] T017 Implement append-only artifact writing, hash verification, attempt-prefix staging, and artifact-index generation in `src/code_data_factory/evidence/artifact_store.py`
- [ ] T018 Implement typed YAML configuration loading, environment-only secret resolution, project-relative path validation, and fail-closed defaults in `src/code_data_factory/config.py`
- [ ] T019 Implement the `cdf` command group, common options, JSON-only standard output mode, structured standard-error logging, exit-code mapping, and dry-run envelope in `src/code_data_factory/cli.py`
- [ ] T020 Complete the foundational contract and command-envelope tests, including unknown-major-version and conflicting-output-path failures, in `tests/contract/test_cli_contract.py`

**Checkpoint**: Foundational tests pass; generated schemas match contracts; no command can silently overwrite a hash-mismatched artifact.

---

## Phase 3: User Story 1 - 构建可追踪的代码数据版本 (Priority: P1) 🎯 MVP

**Goal**: Build immutable, governed Python code datasets with complete lineage, deterministic local/Ray execution, and bounded multi-node scale evidence.

**Independent Test**: Freeze one fixed-license Python fixture repository, generate candidates, run governance and deduplication, build and publish a dataset, trace accepted/rejected samples end to end, prove local/single-node-Ray logical equivalence, and either produce valid 1/2/4-node Ray evidence or an explicit unmet multi-node result.

### Tests for User Story 1

- [ ] T021 [P] [US1] Write failing source-freeze contract tests for full 40-character revisions, license allowlists, symlink/path escape, file limits, and deterministic file manifests in `tests/contract/test_source_freeze.py`
- [ ] T022 [P] [US1] Write failing governance and generation tests for parent lineage, license rejection, secret/PII canaries, scanner failure, and zero-findings wording in `tests/integration/test_generation_governance.py`
- [ ] T023 [P] [US1] Write failing deduplication and contamination tests for raw/AST hashes, MinHash candidate verification, hot buckets, cluster-safe splitting, and blocked evaluation overlap in `tests/integration/test_dedup_contamination.py`
- [ ] T024 [P] [US1] Write failing dataset publication tests for immutable manifests, membership counts, data-card sections, lineage acyclicity, and `BENCHMARK_ONLY` rejection in `tests/contract/test_dataset_publication.py`
- [ ] T025 [P] [US1] Write failing local-versus-Ray tests that ignore file/row ordering but compare schema, sample IDs, decisions, counts, and logical content hashes in `tests/integration/test_local_ray_equivalence.py`
- [ ] T026 [P] [US1] Write failing Ray benchmark tests for cluster-session preflight, actual node distribution, idempotent retries, metric-unavailable nulls, budget stops, five-trial completeness, and claim-state decisions in `tests/integration/test_ray_scale_benchmark.py`

### Implementation for User Story 1

- [ ] T027 [P] [US1] Define the bounded Python source allowlist, exact revisions, path/size limits, and license expectations in `configs/sources/python.yaml`
- [ ] T028 [US1] Implement Git/local-fixture acquisition, license snapshotting, file hashing, symlink blocking, and `SourceSnapshot` output in `src/code_data_factory/sources/freezer.py`
- [ ] T029 [P] [US1] Define versioned data-transform, quality-repair, and pipeline-debug task templates plus bounded Python/CLI tool schemas with stable identifiers in `src/code_data_factory/generation/templates.py`
- [ ] T030 [US1] Implement the OpenAI-compatible generator adapter, deterministic request manifest, parent links, response hashing, and failure records in `src/code_data_factory/generation/client.py`
- [ ] T031 [US1] Convert frozen source/input-dataset/task inputs and generator responses into lineage-bearing `DataSample`, `TaskPackage`, and `TransformationRecord` batches in `src/code_data_factory/generation/service.py`
- [ ] T032 [P] [US1] Implement SPDX-style license allowlist decisions and review-required quarantine records in `src/code_data_factory/governance/licenses.py`
- [ ] T033 [P] [US1] Integrate detect-secrets with mandatory synthetic canaries and raw finding preservation in `src/code_data_factory/governance/secrets.py`
- [ ] T034 [P] [US1] Integrate structured Presidio recognizers with high-confidence blocking and ambiguous-result review routing in `src/code_data_factory/governance/pii.py`
- [ ] T035 [P] [US1] Implement exact and near evaluation-contamination lookup against a frozen read-only index in `src/code_data_factory/governance/contamination.py`
- [ ] T036 [US1] Compose license, secret, PII, and contamination checks into fail-closed quality assessments and quarantine output in `src/code_data_factory/governance/service.py`
- [ ] T037 [P] [US1] Implement Python parsing, formatting-insensitive abstract-syntax-tree normalization, raw hashes, AST hashes, token shingles, and parse evidence in `src/code_data_factory/dedup/normalization.py`
- [ ] T038 [P] [US1] Implement datasketch MinHash signatures, versioned band keys, hot-bucket limits, and exact Jaccard/containment verification in `src/code_data_factory/dedup/minhash.py`
- [ ] T039 [US1] Build deterministic connected duplicate clusters, representative selection, and cluster-atomic train/development/test assignment in `src/code_data_factory/dedup/clustering.py`
- [ ] T040 [P] [US1] Compute declared quality dimensions and multi-label skill/source/difficulty/length/generator/test-strength slices without a global acceptance score in `src/code_data_factory/datasets/quality.py`
- [ ] T041 [US1] Compose reusable Arrow record-batch business operators for generation, governance, normalization, deduplication, quality, and slicing in `src/code_data_factory/datasets/operators.py`
- [ ] T042 [P] [US1] Implement the deterministic in-process adapter over the shared Arrow operators in `src/code_data_factory/distributed/local_adapter.py`
- [ ] T043 [P] [US1] Implement the thin Ray Data adapter with `map_batches`, task/actor compute strategies, fixed resources, shuffle stages, and no untrusted-code execution in `src/code_data_factory/distributed/ray_adapter.py`
- [ ] T044 [US1] Implement attempt-scoped pipeline orchestration, decision counts, output equivalence fields, raw `Dataset.stats()`, retry history, and atomic publish gating in `src/code_data_factory/distributed/pipeline.py`
- [ ] T045 [US1] Implement `Clean` and generic draft dataset assembly, stable membership/exposure records, lineage graph validation, and evaluation-index blocking in `src/code_data_factory/datasets/builder.py`
- [ ] T046 [US1] Implement immutable dataset publication, quality/diversity summaries, required data-card sections, and DVC references in `src/code_data_factory/datasets/publisher.py`
- [ ] T047 [US1] Implement append-only deletion/correction/license-revocation impact traversal across samples, datasets, runs, and claims in `src/code_data_factory/governance/deletion.py`
- [ ] T048 [US1] Wire `cdf source freeze`, `cdf governance scan`, `cdf dataset build`, and `cdf dataset publish` to their services and contract gates in `src/code_data_factory/cli.py`
- [ ] T049 [P] [US1] Define clean, governance, deduplication, publication, and tokenizer policy with explicit thresholds and reason codes in `configs/quality/clean.yaml`, `configs/quality/governance.yaml`, and `configs/quality/publish.yaml`
- [ ] T050 [US1] Implement deterministic 1 GiB/64 GiB benchmark replay with stable replica IDs and hard `BENCHMARK_ONLY` isolation in `src/code_data_factory/benchmarks/prepare.py`
- [ ] T051 [US1] Implement Ray cluster topology, private-port, version/lock, homogeneous-resource, head-zero-CPU, and shared-storage read/write probes in `src/code_data_factory/benchmarks/preflight.py`
- [ ] T052 [US1] Implement Ray Jobs submission, per-node task evidence, operator metrics, bounded system retries, attempt-prefix output, and worker-process fault injection in `src/code_data_factory/benchmarks/runner.py`
- [ ] T053 [P] [US1] Implement Ray head/worker/storage/network price projection, approval-cap enforcement, and actual-billing reconciliation in `src/code_data_factory/benchmarks/budget.py`
- [ ] T054 [US1] Implement 1/2/4-node trial validation, median/range/bootstrap intervals, speedup/efficiency, correctness equivalence, and negative bottleneck outcomes in `src/code_data_factory/benchmarks/summarize.py`
- [ ] T055 [US1] Wire `cdf benchmark prepare`, `preflight`, `ray-data`, `budget`, and `summarize` with required artifacts and exit codes in `src/code_data_factory/cli.py`
- [ ] T056 [P] [US1] Freeze the 1/2/4-node topology, block/batch strategy, randomized five-trial order, retry limit, storage URI placeholder, and metric definitions in `configs/distributed/ray-scale-v1.yaml`
- [ ] T057 [US1] Run the complete US1 fixture workflow, preserve the local/Ray single-node equivalence result plus real multi-node evidence or explicit `INCOMPLETE` downgrade in `artifacts/acceptance/us1/`, and contemporaneously update a real `CH-###` entry or add a US1 checkpoint receipt in `docs/evidence-journal.md`

**Checkpoint**: A reviewer can reconstruct a published dataset and every decision; Ray scale claims are impossible without real node/task/cost evidence; the checkpoint is incomplete without its journal update or no-new-challenge receipt.

---

## Phase 4: User Story 2 - 获得可信的代码执行证据 (Priority: P1)

**Goal**: Execute untrusted generated Python only in a verified gVisor boundary, preserve every attempt, and fail closed when the environment or test strength is insufficient.

**Independent Test**: Run correct, wrong, timeout, out-of-memory, network, privilege, nondeterministic, and weak-test fixtures with and without a passing preflight; verify exact outcomes, two-run consistency, negative-control strength, and downgrade behavior.

### Tests for User Story 2

- [ ] T058 [P] [US2] Write failing preflight tests for expired/missing inspection, wrong runtime, privilege, network, writable-root, device, Docker-socket, and resource-limit violations in `tests/contract/test_executor_preflight.py`
- [ ] T059 [P] [US2] Create deterministic correct/wrong/timeout/OOM/network/nondeterministic fixture programs and expected outcomes in `tests/fixtures/execution/manifest.yaml`
- [ ] T060 [P] [US2] Write failing execution integration tests for repeated attempts, bounded logs, raw exit/resource evidence, flaky aggregation, and no `runc` fallback in `tests/integration/test_secure_execution.py`
- [ ] T061 [P] [US2] Write failing generated-test strength tests proving that weak tests cannot reject known mutants or reach `NEGATIVE_CONTROL_REJECTED` in `tests/integration/test_test_strength.py`

### Implementation for User Story 2

- [ ] T062 [P] [US2] Build a digest-pinned, non-root, offline Python executor image with no runtime dependency download in `docker/executor/Dockerfile`
- [ ] T063 [P] [US2] Define gVisor `runsc`/`systrap`, read-only mounts, tmpfs output, dropped capabilities, no-new-privileges, no network/devices, and CPU/memory/PID/file/time limits in `configs/execution/gvisor.yaml` and `configs/execution/python.yaml`
- [ ] T064 [US2] Implement host-side gVisor installation/runtime inspection, image-digest checks, policy canaries, expiry, and `executor_preflight.json` emission in `src/code_data_factory/verification/preflight.py`
- [ ] T065 [US2] Implement the Docker Engine plus `runsc` execution runner with immutable inputs, bounded output, resource sampling, termination classification, and no cloud credentials in `src/code_data_factory/verification/runner.py`
- [ ] T066 [US2] Persist each compile/test attempt, stdout/stderr hash, exit status, duration, resource usage, and infrastructure/sample failure distinction in `src/code_data_factory/verification/attempts.py`
- [ ] T067 [US2] Aggregate at least two attempts into execution pass/fail/flaky/blocked states without deleting recovered failures in `src/code_data_factory/verification/service.py`
- [ ] T068 [US2] Implement deterministic mutation/known-wrong negative controls and independent test-strength classification in `src/code_data_factory/verification/test_strength.py`
- [ ] T069 [US2] Wire `cdf verify preflight` and `cdf verify run` with fail-closed policy and preserved blocked artifacts in `src/code_data_factory/cli.py`
- [ ] T070 [US2] Implement the `Verified` recipe so only governance-accepted, execution-passed, sufficiently tested samples enter membership in `src/code_data_factory/datasets/verified.py`
- [ ] T071 [US2] Execute the US2 fixture matrix on the isolated Linux gVisor host, or record dependency-unavailable downgrades without local execution substitution, in `artifacts/acceptance/us2/`; update the relevant `CH-###` trade-off and result or add a US2 checkpoint receipt in `docs/evidence-journal.md`

**Checkpoint**: `EXECUTION_VALIDATED` cannot be produced without a current passing host preflight, two consistent attempts, raw logs, adequate generated-test evidence, and the required journal review.

---

## Phase 5: User Story 3 - 用评测短板驱动数据迭代 (Priority: P2)

**Goal**: Turn development-set item failures into auditable findings, data actions, a matched ClosedLoop dataset, and a recorded retest outcome without exposing the final test split.

**Independent Test**: Feed a frozen development evaluation fixture into the feedback command, publish a ClosedLoop draft, verify every non-random change links to a finding/action/retest plan, compare it with RandomMatched from the same candidate pool, and reject any test-item reference.

### Tests for User Story 3

- [ ] T072 [P] [US3] Write failing feedback-contract tests for item-level evidence, finding states, action reason codes, retest plans, and development-only metadata in `tests/contract/test_feedback_contract.py`
- [ ] T073 [P] [US3] Write failing integration tests for test-split leakage, unmatched candidate pools, covariate imbalance, orphan actions, and improved/unchanged/regressed closure in `tests/integration/test_feedback_loop.py`

### Implementation for User Story 3

- [ ] T074 [P] [US3] Implement immutable evaluation-item ingestion and a versioned capability/error taxonomy in `src/code_data_factory/feedback/ingest.py`
- [ ] T075 [P] [US3] Compute multi-label slice diagnostics across length, difficulty, source, generator, test strength, duplication, and quality without reading test data in `src/code_data_factory/feedback/diagnostics.py`
- [ ] T076 [US3] Convert stable failure patterns into prioritized `EvaluationFinding` records with evidence item IDs and confidence in `src/code_data_factory/feedback/findings.py`
- [ ] T077 [US3] Implement finding-driven add/repair/regenerate/reselect/downweight/delete/review actions and retest plans in `src/code_data_factory/feedback/actions.py`
- [ ] T078 [US3] Build `SFT-ClosedLoop` and `SFT-RandomMatched` task-answer memberships from the same Verified pool with task type/source/difficulty/input size/test strength/baseline-success matching and balance reports in `src/code_data_factory/datasets/matching.py`
- [ ] T079 [US3] Record the data-sensitivity discover→explain→decide→retest chain and its improved/unchanged/regressed outcome in `src/code_data_factory/feedback/sensitivity.py`
- [ ] T080 [P] [US3] Define frozen feedback priorities, matching fields, balance tolerances, and action policies in `configs/quality/feedback-v1.yaml` and `configs/quality/random-matched.yaml`
- [ ] T081 [US3] Wire `cdf feedback build` and closed-loop dataset publication with development-only gates in `src/code_data_factory/cli.py`
- [ ] T082 [US3] Run the complete fixture-driven finding→action→SFT-ClosedLoop/SFT-RandomMatched→retest workflow, save its bidirectional lineage in `artifacts/acceptance/us3/`, and update the actual closed-loop trade-off/result or add a US3 checkpoint receipt in `docs/evidence-journal.md`

**Checkpoint**: One complete feedback loop and its journal review exist; lack of improvement remains a valid, visible outcome and final test data never influences selection.

---

## Phase 6: User Story 4 - 量化数据对模型能力的贡献 (Priority: P2)

**Goal**: Run or safely downgrade a minimal fixed-budget SFT data-attribution experiment over one-shot end-to-end data-engineering task success, repair, held-out task/dataset generalization, inference cost, general capability, and security.

**Independent Test**: With synthetic fixtures, prove task/answer/verifier lineage, optional RL-ready reward replay, preregistration, equal effective tokens, failure preservation, claim downgrading, and metric recomputation; with approved GPU access, freeze a 7B–8B Instruct model after smoke/calibration, run both SFT task-selection recipes over all required seeds, evaluate them in an isolated environment, and publish only conclusions supported by real artifacts.

### Tests for User Story 4

- [ ] T083 [P] [US4] Write failing preregistration tests for immutable hypotheses, exact seeds, one data-selection difference, matched task-answer pools, one frozen training method, equal effective tokens/steps/exposure, common single-GPU topology, frozen suites, and pre-result budget exceptions in `tests/contract/test_experiment_plan.py`
- [ ] T084 [P] [US4] Write failing task/answer/verifier/training-run tests for model/data/config hashes, full-parameter/LoRA/QLoRA method-gate decisions, RL-ready hard-gate and replay violations, padding-excluded token accounting, checkpoint reload, failed terminal records, cost capture, and mixed-method/topology rejection in `tests/integration/test_training_runner.py`
- [ ] T085 [P] [US4] Write failing evaluation/statistics tests for versioned external-benchmark protocol bindings, protocol-deviation reports, one-shot final-artifact assertions, task-template/repository/input-dataset-disjoint splits, repair fixtures, inference-cost metrics, security references, paired bootstrap intervals, seed variation, and guardrail regressions in `tests/integration/test_evaluation_statistics.py`
- [ ] T086 [P] [US4] Write failing model-effect decision tests covering positive, interval-crossing-zero, negative, unequal-budget, missing-seed, failed-run, and software-only cases in `tests/contract/test_model_effect_gate.py`

### Implementation for User Story 4

- [ ] T087 [US4] Implement ordered 7B–8B Instruct model-candidate identity/license/revision/chat-template checks, baseline task-success references, SFT smoke results, memory margin, checkpoint reload, and pre-result selection freeze in `src/code_data_factory/experiments/model_selection.py`
- [ ] T088 [P] [US4] Implement padding-excluded effective-loss-token, optimizer-step, exposure, GPU-second and monetary accounting with exact cross-recipe equality assertions in `src/code_data_factory/experiments/tokens.py`
- [ ] T089 [US4] Implement a thin external Transformers/TRL `SFTTrainer`/PEFT/Accelerate adapter limited to loading frozen manifests, invoking the upstream trainer, collecting checkpoints/logs, environment fingerprinting, and terminalizing failures; do not implement an optimizer, RL trainer, generic rollout platform, or distributed trainer in `src/code_data_factory/experiments/trainer.py`
- [ ] T090 [P] [US4] Implement local-only MLflow run indexing that references canonical hashed artifacts without becoming a second fact store in `src/code_data_factory/experiments/tracking.py`
- [ ] T091 [US4] Implement the pre-result full-parameter/LoRA/QLoRA feasibility gate using actual single-GPU backward pass, memory margin, finite-loss, throughput, checkpoint reload, six-run cost, added-infrastructure rejection and frozen candidate order; select one method without publishing an algorithm comparison in `src/code_data_factory/experiments/method_selection.py`
- [ ] T092 [US4] Implement calibration-derived GPU-hour/cost projections, 15% reserve, 5,000/10,000 CNY gates, permitted exception reasons, and result-insensitive allocation checks in `src/code_data_factory/experiments/budget.py`
- [ ] T093 [US4] Implement immutable SFT preregistration receipts, plan hashes, matched-task/verifier/evaluation readiness checks, exact token-budget gates, and status transitions in `src/code_data_factory/experiments/preregister.py`
- [ ] T094 [US4] Implement one-shot data-transform, quality-repair, and pipeline-debug evaluation with final-artifact assertions, task-template/repository/input-dataset-disjoint splits, inference-cost, safety, and external benchmark binding outputs in `src/code_data_factory/evaluation/runner.py`
- [ ] T095 [P] [US4] Integrate the frozen external benchmark adapters selected in `research.md`, preserve their official metric semantics and item-level canonical outputs, and emit explicit protocol deviations instead of presenting project subsets as full leaderboard scores in `src/code_data_factory/evaluation/external.py`
- [ ] T096 [US4] Implement per-seed deltas, mean/standard deviation, paired-bootstrap 95% intervals, guardrail decisions, and negative/inconclusive preservation in `src/code_data_factory/evaluation/statistics.py`
- [ ] T097 [US4] Wire `cdf experiment select-model`, `select-training-method`, `calibrate`, `budget`, `preregister`, `run`, optional `cdf reward replay`, and `cdf evaluate run` to all preflight and evidence gates in `src/code_data_factory/cli.py`
- [ ] T098 [P] [US4] Define ordered 4B-smoke/7B–8B model gates, full-parameter/LoRA/QLoRA feasibility order, one selected SFT method, two-recipe matrix, seeds, effective-token tiers, optional RL-ready reward export, and guardrails in `configs/experiments/model-selection.yaml`, `configs/experiments/training-method-selection.yaml`, `configs/experiments/sft-main.yaml`, and `configs/experiments/reward-export-v1.yaml`
- [ ] T099 [P] [US4] Define versioned external benchmark bindings, official metrics and protocol deviations plus project development/test task environments, generated-program contract, task-template/repository/input-dataset-disjoint fixtures, final-artifact assertions, repair cases, metric formulas, and contamination inputs in `configs/evaluation/external-code-v1.yaml` and `configs/evaluation/data-engineering-v1.yaml`
- [ ] T100 [US4] Run the 3B–4B software-chain smoke, 7B–8B Instruct model gate and full-parameter/LoRA/QLoRA method feasibility gate, including real parameter updates, checkpoint reload, final-task evaluation and optional reward replay before formal results; freeze one method and preserve every rejection in `artifacts/acceptance/us4/model-gates/`
- [ ] T101 [US4] Run both recipes under one seed, freeze equal effective-token/step/exposure budgets from actual OpenBayes price and throughput, and preregister all six SFT runs before viewing formal results in `artifacts/acceptance/us4/preregistration/`
- [ ] T102 [US4] Execute and preserve terminal records for all six formal `SFT-RandomMatched`/`SFT-ClosedLoop` runs in `artifacts/runs/training/`; do not add CPT, RL, algorithm comparisons, or extra model sizes to the formal matrix
- [ ] T103 [US4] Evaluate the shared initial checkpoint and every completed formal checkpoint on the frozen external benchmark layer and project data-engineering extension, preserve protocol deviations/predictions/final artifacts/item outputs/costs, produce comparison-ready statistics without publishing claims, and update the actual training/evaluation trade-off or US4 checkpoint receipt in `docs/evidence-journal.md`

**Checkpoint**: Real model-effect evidence exists only if all frozen comparisons pass; otherwise the same pipeline produces explicit software-only, negative, regressed, failed, or inconclusive results. The training/evaluation journal review is mandatory in either case.

---

## Phase 7: User Story 5 - 独立审阅和复现实验证据 (Priority: P3)

**Goal**: Let an external reviewer trace and reproduce software, distributed-data, safe-execution, research-method, and model-effect statements without relying on oral explanation.

**Independent Test**: Select one claim of each available type, verify its required evidence and reverse lineage, deliberately remove or corrupt one artifact to prove fail-closed downgrading, and independently rebuild at least one representative dataset/claim from frozen inputs.

### Tests for User Story 5

- [ ] T104 [P] [US5] Write failing claim-verifier tests for every claim type/level, missing/contrary artifacts, stale research evidence, incomplete Ray trials, missing seeds, unequal budgets, and forbidden automatic upgrades in `tests/contract/test_claim_verifier.py`
- [ ] T105 [P] [US5] Write failing lineage/reproduction tests for forward/reverse traversal, hash corruption, unavailable dependencies, deterministic equality, declared tolerance, and invalidation propagation in `tests/integration/test_reproduction.py`

### Implementation for User Story 5

- [ ] T106 [P] [US5] Implement research-query/source snapshots, large-model date gating, component-maintenance review, supersession checks, and supported-claim links in `src/code_data_factory/evidence/research.py`
- [ ] T107 [US5] Build canonical claim→artifact and artifact/source/dataset/run→claim indexes across DVC and MLflow references in `src/code_data_factory/evidence/lineage.py`
- [ ] T108 [US5] Generate static Markdown plus canonical JSON reports from artifacts, including limitations, contrary evidence, failures, missing runs, costs, and no-result states in `src/code_data_factory/evidence/report.py`
- [ ] T109 [US5] Implement strict and downgrade-mode validation for software, distributed, safe-execution, research-method, and model-effect claims in `src/code_data_factory/evidence/verify.py`
- [ ] T110 [US5] Implement claim-driven environment restoration, DVC retrieval, command replay, logical-hash comparison, tolerance diffing, and reproduction terminal records in `src/code_data_factory/evidence/reproduce.py`
- [ ] T111 [US5] Wire `cdf report build`, `cdf evidence verify`, and `cdf reproduce` with non-overwriting report and reproduction bundles in `src/code_data_factory/cli.py`
- [ ] T112 [US5] Perform the independent claim walkthrough, corruption negative control, and one full representative reproduction, preserve all outcomes in `artifacts/acceptance/us5/`, and update the real reproduction difficulty/trade-off or US5 checkpoint receipt in `docs/evidence-journal.md`

**Checkpoint**: Every published statement has a stable claim ID, exact evidence level, supporting/contrary artifacts, limitations, reverse lineage, a runnable reproduction entry point, and a contemporaneous journal review.

---

## Phase 8: Polish & Cross-Cutting Validation

**Purpose**: Finish the public project documentation and prove that all selected stories satisfy shared governance without broadening project scope.

- [ ] T113 [P] Document the implemented architecture, local/Ray boundary, gVisor trust boundary, data-to-training feedback loop, and unproven external dependencies in `docs/ARCHITECTURE.md`
- [ ] T114 [P] Write a reviewer-first project guide with exact setup, smallest demo, evidence-level legend, cost warnings, and links to canonical reports in `README.md`
- [ ] T115 Run Ruff, mypy, pytest with coverage, schema compatibility checks, `uv lock --check`, DVC status, and package build; save machine-readable results in `artifacts/acceptance/software-gates/`
- [ ] T116 Execute every currently available step in `specs/001-code-data-factory/quickstart.md`, record unavailable external steps as dependency-limited rather than passed, and save the checklist in `artifacts/acceptance/quickstart/`
- [ ] T117 Audit public-facing reports for unsupported model gains, unsafe-execution claims, fake multi-node scale, omitted negative results, stale research, and excluded reference-requirement scope in `reports/final/claim-language-audit.md`
- [ ] T118 Build the final source/wheel package and a non-sensitive evidence manifest, then document exact artifact retrieval rather than committing large outputs in `dist/` and `reports/final/artifact-manifest.json`
- [ ] T119 Trace all requirements including FR-017a, FR-027a, FR-031a and FR-001–FR-043, plus SC-001–SC-015, to tasks, tests, artifacts, and actual evidence levels in `reports/final/requirements-traceability.md`
- [ ] T120 Consolidate the maintained challenge/solution log, promote only evidence-backed candidate summaries, add actual metrics and artifact/commit links, and prepare concise and detailed public evidence summaries in `docs/evidence-journal.md`

**Checkpoint**: The package builds, software checks pass, external gaps are explicit, and no report exceeds its actual evidence tier.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 — Setup**: No dependencies; starts immediately.
- **Phase 2 — Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 — US1**: Depends on Phase 2; delivers the dataset, lineage, local/Ray execution, and Ray benchmark substrate.
- **Phase 4 — US2**: Depends on Phase 2 for contracts; can use fixtures independently, but producing the real `Verified` dataset depends on US1 candidate data.
- **Phase 5 — US3**: Depends on Phase 2 for contracts; its fixture test is independent, while the real SFT-ClosedLoop/SFT-RandomMatched release depends on US1 plus US2's Verified pool.
- **Phase 6 — US4**: Software tests depend only on Phase 2; real attribution runs depend on US1 datasets, US2 verification, US3 matched feedback datasets, approved GPU spend, and a frozen evaluation suite.
- **Phase 7 — US5**: Core verifier/reproducer code can start after Phase 2; final acceptance depends on whichever US1–US4 evidence is being published.
- **Phase 8 — Polish**: Depends on all stories selected for the final public release.

### User Story Dependency Graph

```text
Setup → Foundation → US1 ───────────────┐
                     ├→ US2 ────────────┤
                     └→ US2 → US3 ──────┼→ US4 → US5 → Polish
Foundation ─────────────────────────────┘          ↑
                                                   │
US1 Ray evidence ──────────────────────────────────┘
```

- US1 is the data and distributed-processing base.
- US2 is independently testable with fixtures, then enriches US1 into Verified data.
- US3 is independently testable with evaluation fixtures, then consumes the real Verified pool.
- US4 can prove software gating with fixtures but requires US1–US3 outputs for actual causal data comparisons.
- US5 can validate partial claims at any milestone and becomes the final publication/reproduction layer.

### Requirement Coverage Check

| Requirement group | Primary task coverage |
|---|---|
| FR-001–FR-005 scope, positioning, and current research | T001–T006, T106, T117, T119 |
| FR-006–FR-012 generation, governance, immutable datasets, deletion, and data cards | T021–T049, T057 |
| FR-013–FR-018 static/safe execution, repeated attempts, test strength, and downgrade | T058–T071 |
| FR-019–FR-024 quality, diversity, contamination, and sensitivity | T022–T046, T072–T082 |
| FR-025–FR-027 evaluation findings and feedback data actions | T072–T082 |
| FR-028–FR-033 including FR-031a layered benchmark evaluation, fair data-value attribution, and honest model-effect results | T083–T103 |
| FR-034–FR-038 claims, lineage, reproduction, and complete result retention | T104–T119 |
| FR-039–FR-042 local/Ray parity, real scale evidence, and benchmark isolation | T025–T026, T041–T057 |
| FR-043 continuous challenge, trade-off, and highlight evidence | T057, T071, T082, T103, T112, T120 |
| SC-001–SC-015 measurable acceptance outcomes | Story checkpoints T057, T071, T082, T100–T103, T112, and final traceability T119–T120 |

### Within Each User Story

1. Write the story's contract/integration tests and confirm expected failures.
2. Implement leaf contracts/configuration and pure operators.
3. Compose services and command-line interfaces.
4. Run the story's independent fixture acceptance.
5. Run external Ray, gVisor, or GPU work only after its preflight and budget approval.
6. Preserve failure, negative, unchanged, aborted, and budget-blocked states alongside successes.
7. At discovery and at the story checkpoint, update `docs/evidence-journal.md` for non-trivial challenges,
   alternatives, failed approaches, measured outcomes, and candidate summaries; keep unverified items explicitly
   unverified rather than waiting until final polish to reconstruct them from memory.

### Parallel Opportunities

- Phase 2 contract model files T008–T014 can proceed in parallel after T007 defines expected failures.
- US1 source/generation, governance scanners, dedup primitives, quality slicing, and shared configs can proceed in parallel after Phase 2.
- US2 Docker/config work can proceed in parallel with execution test fixtures before preflight/runner composition.
- US3 ingestion and diagnostics can proceed in parallel before finding/action composition.
- US4 token accounting, MLflow indexing, general-evaluation adapter, and experiment/evaluation configs can proceed in parallel before runner integration.
- US5 research-evidence handling can proceed in parallel with claim/reproduction tests before lineage/report composition.
- Real Ray and GPU workloads are intentionally not marked `[P]`: each is gated by current topology, frozen budget, predecessor artifacts, and evidence review.

---

## Parallel Examples

### User Story 1

```text
Task T032: license governance in src/code_data_factory/governance/licenses.py
Task T033: secret scanning in src/code_data_factory/governance/secrets.py
Task T034: PII scanning in src/code_data_factory/governance/pii.py
Task T035: contamination scanning in src/code_data_factory/governance/contamination.py
Task T037: Python/AST normalization in src/code_data_factory/dedup/normalization.py
Task T038: MinHash candidates in src/code_data_factory/dedup/minhash.py
```

### User Story 2

```text
Task T062: executor image in docker/executor/Dockerfile
Task T063: execution policies in configs/execution/gvisor.yaml and configs/execution/python.yaml
Task T059: adversarial fixtures in tests/fixtures/execution/manifest.yaml
```

### User Story 3

```text
Task T074: evaluation ingestion in src/code_data_factory/feedback/ingest.py
Task T075: slice diagnostics in src/code_data_factory/feedback/diagnostics.py
Task T080: feedback and matching policies in configs/quality/
```

### User Story 4

```text
Task T088: effective-token accounting in src/code_data_factory/experiments/tokens.py
Task T090: MLflow reference bridge in src/code_data_factory/experiments/tracking.py
Task T095: general guardrail adapter in src/code_data_factory/evaluation/general.py
Task T098: experiment configs in configs/experiments/
Task T099: evaluation suite config in configs/evaluation/data-engineering-v1.yaml
```

### User Story 5

```text
Task T104: claim-verifier contract tests in tests/contract/test_claim_verifier.py
Task T105: reproduction integration tests in tests/integration/test_reproduction.py
Task T106: research-source evidence in src/code_data_factory/evidence/research.py
```

---

## Implementation Strategy

### MVP First: US1

1. Complete Setup and Foundational phases.
2. Complete US1 through bounded source freezing, governance, deduplication, immutable dataset publication, and local/single-node-Ray equivalence.
3. Demonstrate the data lineage and software-level Ray adapter before renting a multi-node cluster.
4. Obtain an explicit Ray CPU/storage budget cap, then complete the 1/2/4-node benchmark or publish `INCOMPLETE` without a scale claim.
5. Stop and review the US1 artifacts before starting secure execution or GPU work.

### Incremental 12-Week Delivery

- **Weeks 1–3**: T001–T044 plus T049/T056, emphasizing setup, contracts, bounded sources, governance, deduplication, and local/single-node-Ray software paths.
- **Weeks 4–5**: T045–T049 plus US1 test stabilization for generation, quality, slicing, deletion propagation, and immutable dataset publication.
- **Week 6**: T058–T071 for gVisor preflight, adversarial fixtures, secure attempts, and Verified data.
- **Week 7**: T050–T057 external Ray preflight, fixed 64 GiB workload, 1/2/4-node trials, failure injection, and cost report.
- **Weeks 8–9**: T083–T100 for the thin SFT/evaluation software, optional RL-ready reward export, GPU smoke, model selection, calibration, and budget evidence without formal-result inspection.
- **Week 10**: T072–T082 for development findings, SFT-ClosedLoop/SFT-RandomMatched selection, and retest lineage, followed by T101 preregistration.
- **Week 11**: T102–T103 for six formal SFT runs and frozen-suite evaluation within the approved budget; no CPT or RL training.
- **Week 12**: T104–T120 for claims, reproduction, negative-result retention, final validation, evidence-journal consolidation, and public documentation.

### Budget and Scope Stop Rules

1. Do not create the Ray cluster until T053 has an owner-approved CPU/storage/network cap; if the 5,000 CNY limit covers all cloud resources, update `configs/project.yaml` and recalculate both GPU and Ray plans before execution.
2. Do not start formal GPU runs until T100–T101 have frozen the actual model revision, measured throughput/memory, selected token tier, price quote, reserve, and preregistration.
3. If time or money tightens, remove Ray workloads above 64 GiB, visual interfaces, model upper-bound pilots, and nonessential RL-ready export formats in that order; do not remove lineage, fair controls, three SFT seeds, failure records, or evidence downgrading.
4. Do not add multimodal processing, internet-scale crawling, PB/EB infrastructure, database kernels, Kubernetes, organizational platform features, Ray Train, Ray Tune, or Ray Serve to these tasks.

## Notes

- `[P]` never authorizes parallel mutation of the same file; coordinate tasks that touch `src/code_data_factory/cli.py` sequentially.
- Runtime directories in task descriptions are evidence destinations, not pre-created proof; a task is complete only after the named command actually produces and validates the artifacts.
- Passing software tests remains `SOFTWARE_VALIDATED`; only a real passing gVisor execution can reach `EXECUTION_VALIDATED`, and only real fair training plus evaluation can support `TRAINING_EVIDENCED`.
- Evidence-journal entries follow the same boundary: a planned solution or `CANDIDATE` summary remains `UNVERIFIED` until its linked evidence exists; update records when the issue is discovered and again at the story checkpoint.
- Commit after a reviewable task or functional group, and never commit credentials, raw sensitive samples, model weights, caches, DVC data blobs, MLflow runs, or cloud-generated artifacts.
