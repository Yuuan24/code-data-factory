# Quickstart Validation Guide: 轨迹数据产线

**Revision**: 2.1 | **Status**: 外部训练数据主线待 T103–T108 实现；已有 T001–T044 仅保留原软件和
固定动作验证范围。外部发布不依赖本地环境或模型生成。命令契约见 [contracts/cli.md](contracts/cli.md)。

## 1. Prerequisites and Reproducible Setup

本地开发在具有固定依赖锁和授权来源数据的检出目录执行：

```bash
uv sync --frozen
uv run cdf --help
uv run pytest tests/contract
```

对于新建或重新分配的 OpenBayes Linux 实例，先遵守
[租用 Linux 环境恢复与依赖验证契约](contracts/rented-environment-recovery.md)：先分类 workspace、再做有
时间上限的镜像与实际 artifact 路径预检，然后从 `/openbayes/home/code-data-factory` 运行：

```bash
bash scripts/openbayes/bootstrap.sh
bash scripts/openbayes/bootstrap.sh
/openbayes/home/.pylibs/bin/uv pip check --python .venv/bin/python
```

第二次 bootstrap 和 Linux probe 都通过时，才可写入依赖/Parquet 的 `SOFTWARE_VALIDATED` 证据；这不替代
后续执行、Ray 或训练门禁。

所有 OpenBayes 测试 checkout 还必须由 GitHub 的非 `main` 候选分支取得；优先在远端核对 branch SHA 与
checkout SHA 一致后才可开始测试。若 Git smart-HTTP 已记录为有界失败，但 GitHub API 和完整 SHA 的 Codeload
archive 可用，可使用直接从 GitHub 下载的 exact-commit archive，并记录 API/ref、archive SHA-256 和来源方法。
只有该精确 SHA 的远端测试全部通过，并且 `origin/main` 未在期间移动，才允许 fast-forward 合并到 `main`。
完整交付规则见根目录 [AGENTS.md](../../AGENTS.md#github-to-openbayes-test-gate)。

保存环境和依赖清单；数据组件必须真实安装。执行门禁另需无特权受限容器；训练和真实采样另需
通过模型/预算门禁的资源。不需要建设网页前端、线上调度平台或多 Agent 服务。

## 2. Audit External Demonstrations

```bash
uv run cdf source audit --manifest configs/sources/external-training.json --output-dir artifacts/data-audit/external-pilot --json
uv run cdf trajectory import --source configs/sources/external-training.json --adapter toucan --output-dir data/normalized/external-pilot --json
```

预期：保存冻结来源、许可、原始分片、上游工具定义及消息/调用/返回/答案定位。训练准入、可重放性、
结果/奖励证据分开；按来源和能力切片抽审至少 30 条，少量来源全审。此步骤不运行工具、不调用模型、
也不将来源自报成功改写为本项目 PASS。

## 3. Build an External Candidate Pool Without an Environment

```bash
uv run cdf data build --input data/build-inputs/external-pilot.json --config configs/quality/external-sft.yaml --backend local --output-dir data/candidates/external --json
uv run cdf dataset publish --draft data/candidates/external --output-dir data/releases/external --json
uv run cdf dataset export-sft --dataset data/releases/external/dataset_manifest.json --config configs/experiments/export-sft.yaml --output-dir data/exports/external --json
```

预期：发布成员均能反查外部上游消息及确定性修复父链，且有独立训练准入决定；本项目任务、固定动作、
交互评测与模型采样成员计数均为零。缺少训练准入、必要上下文、工具定义或目标映射的记录拒绝或待复核。

## 4. Verify the Separate Executable Branch

受控任务环境仅用于验证、交互评测与训练器采样兼容，不构成外部训练发布的输入或前置条件。

```bash
uv run cdf task build --config configs/tasks/pilot.yaml --output-dir data/pilot --json
uv run cdf environment check --config configs/execution/local-tools.yaml --output-dir artifacts/preflight --json
uv run cdf trajectory collect --tasks data/pilot/task_manifest.json --config configs/execution/collect.yaml --execution-config configs/execution/local-tools.yaml --output-dir artifacts/interactions/pilot --json
uv run cdf verify run --attempts artifacts/interactions/pilot/manifest.json --config configs/quality/verifier.yaml --output-dir artifacts/verifications/pilot --json
```

预期：每轮实际请求、输出、调用关联和工具结果独立保存，工具无报错但跨步骤依赖错误仍判失败。
此分支的任务、固定动作与模型调用费用只进入评测/兼容记录，不能写入 `data/releases/external/` 或
`data/exports/external/`。

## 5. Verify RL and Long-Horizon Extension Now

RL 指强化学习；首版检验采样接入和数据兼容，不优化 RL 参数。

```bash
uv run cdf compatibility check --profile configs/execution/trl-tools.yaml --mode contract --output-dir artifacts/compatibility/contract --json
uv run cdf compatibility check --profile configs/execution/trl-tools.yaml --mode sampling --output-dir artifacts/compatibility/sampling --json
uv run cdf compatibility check --profile configs/execution/long-horizon.yaml --mode long-horizon --output-dir artifacts/compatibility/long-horizon --json
uv run cdf reward rescore --evidence tests/fixtures/sparse-rewards/manifest.json --policy configs/quality/reward-terminal-v2.yaml --output-dir artifacts/verifications/rescore --json
```

预期：

- 同任务固定动作经两入口执行，工具/状态/验证语义一致；不要求随机模型轨迹相同。
- 至少两个任务各两次实际训练器采样，保存实际词元、模型输出标记、策略/模板版本及成本；没有
  参数更新。替身测试通过不能取代这四次真实采样；模型失败也保留并可验证数据契约。
- 32/128 步各一固定案例无损存读、跨步依赖与可见上下文可重建；一次上下文改写与一次受控状态
  恢复正确关联。非受控外部环境恢复返回 unsupported。
- 稀疏奖励四种状态各至少两个任务：成功、已知全零、未知、截断。重评分保留原始证据，明确两个
  奖励版本差异，质检项没有被自动用作密集奖励。

## 6. Measure Data Processing at Fixed Scale

```bash
uv run cdf benchmark run --plan configs/distributed/ray-scale-v1.yaml --output-dir artifacts/data-benchmarks/ray-scale-v1 --json
```

预期：64 GiB（吉比字节）复制负载全部为 BENCHMARK_ONLY，不算独立训练任务。真实 1/2/4 节点
各一次预热与五次正式运行，含资源/费用/重试/等价和工作进程终止记录。无加速也保留；缺节点时
成功标准未完成，不能用单机进程代替。

## 7. Development Feedback and Fixed SFT Plans

```bash
uv run cdf evaluate run --model configs/experiments/base-model.json --suite configs/evaluation/tool-tasks.yaml --split development --output-dir artifacts/evaluations/base-dev --json
uv run cdf feedback build --evaluation artifacts/evaluations/base-dev/evaluation_run.json --pool data/releases/external/dataset_manifest.json --policy configs/quality/feedback.yaml --output-dir data/recipes/main --json
uv run cdf experiment calibrate --config configs/experiments/calibration.yaml --output-dir artifacts/experiments/calibration --json
uv run cdf experiment preregister --config configs/experiments/sft-main.yaml --calibration artifacts/experiments/calibration/manifest.json --output-dir artifacts/experiments/sft-main --json
```

此处 `data/releases/external` 为第 2–3 节由外部示范治理建立的合格池，不依赖先导任务或模型生成。
两配方由同池导出；正式训练前分别冻结发布和 SFT 导出，将数据/掩码/匹配产物写入计划。
测试至少 200 个任务且含 20 个独立来源—模板连通组；开发至少 200 个任务。只有开发失败模式用于
选择，目标干预不被匹配掉。相同完整目标、有效词元/步数/批次计算预算的计划匹配不成功就统一降档。

正式前冻结一个模型、一个训练方法、模板和解码预算，两配方及 `[17,29,43]` 三个种子；留 15% 预算
用于失败重跑/复现。存下实际报价而非沿用历史价格。没有预算和资源门禁时不启动付费运行。

## 8. Train, Interactively Evaluate, Attribute

以下仅示范六次正式运行之一；实际两配方各三个种子均需终态：

```bash
uv run cdf experiment run --plan artifacts/experiments/sft-main/experiment_plan.json --recipe sft-closed-loop --seed 17 --output-dir artifacts/experiments/sft-main/training --json
uv run cdf evaluate run --model artifacts/experiments/sft-main/training/model.json --suite configs/evaluation/tool-tasks.yaml --split test --output-dir artifacts/evaluations/model-test --json
uv run cdf evaluate run --model artifacts/experiments/sft-main/training/model.json --suite configs/evaluation/bfcl-local-v4.yaml --split test --output-dir artifacts/evaluations/model-bfcl --json
uv run cdf report build --plan artifacts/experiments/sft-main/experiment_plan.json --output-dir reports/sft-main --json
```

预期：全部数据/方法/预算冻结后才解锁 test。每轮根据模型实际动作运行工具；最终目标/证据/约束
决定 `TaskSuccess@1`，即一次完整尝试的成功比例。BFCL（Berkeley 工具调用评测）固定子集按官方
类别单列并记录协议偏离，不算完整榜单总分。

报告包含六次训练、逐题/逐种子差值、聚类配对区间、2 个百分点实际意义阈值、护栏与成本。固定
分母保留环境故障和有限重试，未解决基础设施故障阻止正式因果结论。负向、不确定、回退和失败
不得删除；完成训练不保证数据有正收益。至少一条真实反馈链完整关联复评。

## 9. Reproduce and Audit Evidence

```bash
uv run cdf evidence verify --manifest reports/sft-main/lineage_index.json --output-dir artifacts/evidence-audit --json
uv run cdf reproduce --manifest data/releases/external/dataset_manifest.json --output-dir artifacts/reproductions/external --json
```

预期：数据逻辑哈希一致，逐题指标可重算，来源与结论双向可追溯。删除一个必要证据后报告门禁
准确拒绝。每个故事检查点都有证据日志记录；未完成项不会因文档齐全而被标为已实现。
