# Quickstart Validation Guide: 轨迹数据产线

**Revision**: 2.0 | **Status**: T001–T012 的基础包、锁、契约和 Linux 依赖读写证据已完成；后续数据、
隔离执行、Ray、真实采样和训练任务仍未完成。命令契约见 [contracts/cli.md](contracts/cli.md)。

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

## 2. Audit Existing Data and Build 100 Pilot Tasks

```bash
uv run cdf source audit --manifest configs/sources/toucan-sft.json --output-dir artifacts/source-audit --json
uv run cdf task build --config configs/tasks/pilot.yaml --output-dir data/pilot --json
uv run cdf environment check --config configs/execution/local-tools.yaml --output-dir artifacts/preflight --json
```

预期：保存冻结来源、原始记录数、实际工具调用范围、初始状态缺失和许可判断。历史观察层与可执行
层数量分开；100 个独立任务覆盖三个族，各不少于 20 个，改写不重复计任务。固定动作重复执行两次，
准备至少 35 个正负哨兵（七类各至少五例）。先导失败则暂停扩大采样，不能以源数据总行数代替。

## 3. Import and Collect Complete Attempts

```bash
uv run cdf trajectory import --source configs/sources/toucan-sft.json --adapter toucan --output-dir data/imported --json
uv run cdf trajectory collect --tasks data/pilot/task_manifest.json --config configs/execution/collect.yaml --execution-config configs/execution/local-tools.yaml --output-dir artifacts/interactions/pilot --json
uv run cdf verify run --attempts artifacts/interactions/pilot/manifest.json --config configs/quality/verifier.yaml --output-dir artifacts/verifications/pilot --json
```

预期：每轮实际请求、输出、调用关联和工具结果存在；工具无报错但用错中间数值时判失败；验证器
故障判 UNKNOWN。超限、模型错误和基础设施故障分别记录。查看历史日志不计真实执行。

## 4. Govern, Deduplicate, Publish and Export

创建构建输入清单 `data/build-inputs/pilot.json`，带哈希引用第 3 节导入的历史原料清单、
`data/pilot/task_manifest.json`、实际采样 manifest、实际 verification manifest 和已冻切分登记簿；
格式见 [构建输入契约](contracts/artifacts.md#build-input-manifest)。清单是批处理输入，不触发额外采样。
历史观察层保留；只有执行/示范门禁通过的数据进入正式发布及 SFT 导出。

```bash
uv run cdf data build --input data/build-inputs/pilot.json --config configs/quality/build.yaml --backend local --output-dir data/draft/local --json
uv run cdf data build --input data/build-inputs/pilot.json --config configs/quality/build.yaml --backend ray --output-dir data/draft/ray --json
uv run cdf dataset publish --draft data/draft/local --output-dir data/releases/pilot --json
uv run cdf dataset export-sft --dataset data/releases/pilot/dataset_manifest.json --config configs/experiments/export-sft.yaml --output-dir data/exports/pilot --json
```

预期：本地/Ray 决策、逻辑哈希一致，近重复候选至少人工抽审 100 对。同源文档、模板派生和重复簇
不跨集合；新增桥接冲突须隔离，全量/增量读取同一登记簿。SFT（监督微调）目标只含经选择的模型
输出及必要输出控制词元；用户、工具、输入包装和填充损失为零。原始失败记录数不因导出改变。

故障验收：输出提交前终止一次、提交后重试一次，再以 `--resume <run-id>` 恢复；无重复/部分发布。
撤销一个测试来源，列出全部受影响版本和结论。原始敏感内容不出现在审计打印中。

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
uv run cdf feedback build --evaluation artifacts/evaluations/base-dev/evaluation_run.json --pool data/releases/verified/dataset_manifest.json --policy configs/quality/feedback.yaml --output-dir data/recipes/main --json
uv run cdf experiment calibrate --config configs/experiments/calibration.yaml --output-dir artifacts/experiments/calibration --json
uv run cdf experiment preregister --config configs/experiments/sft-main.yaml --calibration artifacts/experiments/calibration/manifest.json --output-dir artifacts/experiments/sft-main --json
```

此处 `data/releases/verified` 为在先导通过后，由第 3–4 节相同流程按正式规模建立的合格池。
两配方由同池导出；正式训练前分别执行发布和 SFT 导出，将数据/掩码/匹配产物写入计划。
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
uv run cdf reproduce --manifest data/releases/verified/dataset_manifest.json --output-dir artifacts/reproductions/verified --json
```

预期：数据逻辑哈希一致，逐题指标可重算，来源与结论双向可追溯。删除一个必要证据后报告门禁
准确拒绝。每个故事检查点都有证据日志记录；未完成项不会因文档齐全而被标为已实现。
