# Code Data Factory Agent Rules

These rules apply to every planning, implementation, experiment, and review task in this repository.

## Project Positioning

- Treat this as a data-engineering project. Data generation, governance, execution verification, quality and
  diversity control, Ray processing, lineage, and the evaluation-to-data feedback loop are the primary system.
- Treat model training as the minimum downstream measurement needed to validate data value. Do not expand the
  first version into continued pre-training, reinforcement learning, hyperparameter search, a training platform,
  or model serving.
- Do not hard-code quantized low-rank adaptation (QLoRA) as the project identity. Freeze one training method before
  formal results through the documented feasibility and fairness gate; use the same method for every treatment and
  control run.

## Required Context Before Work

Before starting a task, read the relevant requirements in:

1. `.specify/memory/constitution.md`
2. `specs/001-code-data-factory/spec.md`
3. `specs/001-code-data-factory/plan.md`
4. `specs/001-code-data-factory/tasks.md`
5. `docs/evidence-journal.md`

Do not silently replace a frozen benchmark, training method, evidence level, budget, or comparison rule.

## Difficulty, Decision, and Evidence Journal

Update `docs/evidence-journal.md` when a task reveals a non-trivial constraint, failure, unexpected measurement,
or a choice among plausible approaches. Do this when the issue is discovered and when it is resolved; do not wait
until the final project summary.

A solution record is incomplete unless it explains:

- the mechanism that made the problem difficult;
- the realistic alternatives that were considered;
- why the chosen option fit the project's constraints;
- what was sacrificed or left unresolved;
- how the decision was tested and what the actual result was;
- which artifact, test, run, cost record, or commit supports the statement.

“Used component X” and “changed parameter Y” are implementation details, not a solution or trade-off by themselves.
If a checkpoint produced no non-trivial new issue, record that review explicitly instead of inventing a highlight.
Never promote a candidate evidence summary without the evidence level required by the constitution.

## Checkpoint Gate

A user-story checkpoint is not complete until its acceptance evidence and journal review are both present. The
implementing agent must update an existing `CH-###` entry, create a new one, or add an explicit no-new-challenge
checkpoint receipt with the reviewed task and artifact IDs.
