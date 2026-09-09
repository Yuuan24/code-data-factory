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
5. 若本机存在，读取本地私有决策记录；该记录不得被 Git 跟踪或在公开文档中引用。

Do not silently replace a frozen benchmark, training method, evidence level, budget, or comparison rule.

## Private Decision Record

当任务揭示非平凡约束、失败、意外测量或合理方案之间的取舍时，更新本机忽略的私有决策记录。
该记录在发现和解决时同步更新，但不得被提交、推送或作为公开文档引用。

私有决策记录不完整，除非它解释：

- the mechanism that made the problem difficult;
- the realistic alternatives that were considered;
- why the chosen option fit the project's constraints;
- what was sacrificed or left unresolved;
- how the decision was tested and what the actual result was;
- which artifact, test, run, cost record, or commit supports the statement.

“Used component X” and “changed parameter Y” are implementation details, not a solution or trade-off by themselves.
If a checkpoint produced no non-trivial new issue, record that review explicitly instead of inventing a highlight.
Never promote a candidate evidence summary without the evidence level required by the constitution. 公开材料只保留
可分发的结论、证据层级、范围和复现入口，不披露私有记录的细节。

## Checkpoint Gate

A user-story checkpoint is not complete until its acceptance evidence and local decision-record review are both
present. The implementing agent must update an existing local `CH-###` entry, create a new one, or add an explicit
no-new-issue checkpoint receipt with the reviewed task and artifact IDs.

## Git Commit Identity Gate

Every commit created, amended, merged, or rewritten for this repository, including commits made in a temporary
clone or history-rewrite mirror, must use only this identity:

```text
Yuuan24 <48498800+Yuuan24@users.noreply.github.com>
```

Before the first commit in every worktree or temporary clone, explicitly set and verify the repository-local
`user.name` and `user.email` to those exact values. Do not inherit a global Git identity. Company, personal, or
otherwise unverified email addresses must not appear in author or committer metadata.

Before every push, force-push, or history rewrite publication, inspect the actual candidate commit with
`git show -s --format='%an <%ae>%n%cn <%ce>' <candidate-sha>` and verify that both author and committer exactly
match the required identity. On any mismatch, stop before the remote update and recreate or repair the candidate
locally; changing an already public commit still requires explicit authorization for the corresponding history
rewrite.

## GitHub-to-OpenBayes Test Gate

The repository default branch is `main`; treat it as the protected integration branch even when repository settings
do not technically enforce protection. A rented OpenBayes test is valid for merge only when its checkout was fetched
from GitHub at the exact candidate commit. Copying a Mac working tree to OpenBayes is not GitHub-branch test evidence.

For every code, dependency, configuration, or runnable-documentation change:

1. Start from a freshly fetched `origin/main`, create a descriptively named non-`main` test branch, and make all
   changes there. Do not commit directly on `main`.
2. Stage only the reviewed paths; inspect staged `--stat`, `--name-status`, and `git diff --cached --check` before
   committing. Do not commit credentials, private data, ignored runtime artifacts, or raw remote logs.
3. Run the appropriate local tests and record their exact scope. Push only the candidate test branch to GitHub.
4. On OpenBayes, prefer cloning or fetching that GitHub branch into a clean test checkout. Record both the remote
   checkout SHA and the GitHub branch SHA; they must match before testing begins. If Git smart-HTTP has a bounded,
   recorded failure but GitHub's branch-ref API and exact-commit Codeload archive are reachable, an archive fallback
   is permitted: resolve the branch to its full SHA through the GitHub API, download Codeload by that full SHA (never
   by a mutable branch name), record the archive SHA-256 and API/ref result, and extract it into a clean test
   directory. This remains direct GitHub source evidence, but the receipt must say `GITHUB_EXACT_COMMIT_ARCHIVE`
   rather than claiming a Git checkout SHA.
5. Run the required remote bootstrap, repeat-start, dependency, and task-specific tests from that GitHub checkout.
   A test against a locally copied checkout cannot satisfy this gate.
6. If any remote test fails, keep `main` unchanged. Fix on the same or a replacement non-`main` test branch, push
   the new candidate SHA, and repeat the GitHub-to-OpenBayes test from a clean checkout.
7. Only after all required remote tests pass, fetch `origin/main` again. If it has moved, rebase or reconstruct the
   candidate on the new tip and repeat the remote test. If it has not moved, fast-forward `main` to the exact tested
   SHA and push it. Do not create an untested merge commit and do not force-push `main`.
8. Preserve the branch name, tested SHA, source method, remote test commands/results, evidence hashes, and known
   limitations in the relevant checkpoint or evidence journal. Delete or retain a merged test branch only with an
   explicit user choice.

This gate is a delivery rule, not proof of stronger evidence. Dependency/Parquet checks remain
`SOFTWARE_VALIDATED`; isolated execution, distributed processing, training, and model-value claims retain their
separate gates.
