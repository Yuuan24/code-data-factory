# Quickstart Validation Guide

本文件是实施完成后的验收路径，不表示当前仓库已经具备这些命令、Linux 沙箱或真实训练产物。
在代码尚未实现、Ray 多节点运行未发生、gVisor 未通过或 GPU 训练未发生时，相应结果只能标记为
`SOFTWARE-VALIDATED` 或 `UNVERIFIED`。

## 1. Prerequisites

- Linux x86_64 开发/训练环境；Python 版本由 `uv.lock` 固定。
- 数据与训练代码已经进入 Git，当前提交可由完整 40 位 SHA 标识。
- `uv`、DVC（Data Version Control，数据版本控制）和 Docker Engine 已安装。
- Ray 规模验收另需一个不参与数据计算的 head node（头节点）、1/2/4 个同构 Linux central
  processing unit（中央处理器，CPU）worker node（工作节点）、私网连通和所有节点可访问的共享
  对象/网络文件存储；OpenBayes CPU 容器是首选候选，但必须先通过 Ray 端口、节点和共享存储
  探针，单机多进程或仅 SSH 成功不能替代多节点验收。
- 安全执行场景另需独立 Linux CPU 主机、固定版本 gVisor `runsc` 和无云凭据的执行身份。
- 真实训练场景使用 OpenBayes RTX 5090；当前公开页只确认单卡实例，最多 8 张按租赁并发上限处理；
  每张公开规格为 32 GB 显存。每个独立运行默认使用一张；只有双卡伸缩校准通过后才统一改为两张。
- 仓库、`uv` 环境和全部运行输出位于 `/openbayes/home`；冻结数据和基础模型优先绑定到只读的
  `/openbayes/input/input0-4`。根文件系统不存放任何需要保留的产物。
- 准备至少一个许可明确、固定提交的有界 Python 来源和一个不可由反馈环节读取的评测测试集。

成功标准：任何步骤失败都留下结构化终态和原始证据；不能因为依赖缺失而输出更高证据层级。

## 2. Restore the Exact Environment

```bash
cd /openbayes/home/code-data-factory
export UV_PYTHON_INSTALL_DIR=/openbayes/home/.uv/python
uv sync --frozen
uv run cdf --help
uv run ray --version
dvc version
```

`UV_PYTHON_INSTALL_DIR` 确保 `uv` 下载的项目 Python 位于持久目录；项目 `.venv` 由 `uv sync`
创建在 `/openbayes/home/code-data-factory` 下。不得把平台自带但非持久的 `/opt/venv` 当成冻结环境。

Expected:

- `uv sync --frozen` 不修改 `uv.lock`。
- CLI 可列出 source、governance、dataset、benchmark、verify、experiment、evaluate、feedback、
  report、evidence 和 reproduce 命令。
- 环境清单记录 Python、依赖锁哈希、Git commit 和容器 digest。

## 3. Run Software Gates First

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/code_data_factory/contracts src/code_data_factory/verification \
  src/code_data_factory/distributed src/code_data_factory/experiments src/code_data_factory/evidence
uv run pytest tests/unit tests/contract tests/integration --cov=code_data_factory
```

Expected:

- 全部检查通过并保存测试报告。
- 测试必须覆盖非法契约、哈希不一致、跨 split 重复簇、无 preflight 执行请求、训练预算不等、
  `BENCHMARK_ONLY` 进入训练/评测、Ray 节点数冒充、超预算和缺失证据的 claim 降级。
- 该步骤只证明软件级能力，不证明安全执行或模型提升。

## 4. Freeze a Bounded Source

先编辑 `configs/sources/python.yaml`，使用完整 Git revision 和许可 allowlist。然后运行：

```bash
uv run cdf source freeze --config configs/sources/python.yaml \
  --output-dir data/raw --json
dvc add data/raw
```

Expected artifacts:

- `source_snapshot.yaml`
- `files.parquet`
- 许可证据快照
- 每文件 SHA-256 和 DVC pointer（指针）

Negative validation:

```bash
uv run cdf source freeze --config tests/fixtures/sources/floating-revision.yaml \
  --output-dir artifacts/negative/floating-revision --json
```

Expected: exit code 2，不接受 branch/tag 代替完整 commit，且不留下伪发布数据。

## 5. Validate Governance and Deduplication

```bash
uv run cdf governance scan --dataset data/raw/source_snapshot.yaml \
  --policy configs/quality/governance.yaml \
  --output-dir data/interim/governed --json

uv run cdf dataset build --recipe clean --config configs/quality/clean.yaml \
  --source-snapshot data/raw/source_snapshot.yaml \
  --evaluation-index data/releases/eval-index.json \
  --engine local \
  --output-dir data/interim/clean --json
```

Expected:

- 合成密钥和个人信息 canary 被命中并隔离。
- 精确、抽象语法树和 MinHash 候选分别有明细；MinHash 候选有精确相似度复核。
- 校准集报告 precision（精确率）、recall（召回率）、false positive（误报）和 false negative（漏报）。
- 整个重复簇只属于一个训练/开发/测试切分。
- 污染命中样本不进入训练 membership。

## 6. Validate Ray Data Correctness and Multi-Node Scaling

### 6.1 Prove the thin adapter on bounded real data

同一业务算子先跑本地 oracle（正确性基线），再跑单节点 Ray。Ray 版本由 `uv.lock` 固定；规划基线
是 2.58.0，未完成 Linux 兼容性冒烟前不能写成已验证版本。

```bash
uv run cdf dataset build --recipe clean --config configs/quality/clean.yaml \
  --source-snapshot data/raw/source_snapshot.yaml \
  --evaluation-index data/releases/eval-index.json \
  --engine ray --ray-address local \
  --output-dir data/interim/clean-ray-single --json
```

Expected:

- 本地与 Ray 的 Arrow Schema、样本 ID 集、接受/拒绝原因计数和 `logical_content_hash` 完全相同。
- 物理 Parquet 文件名、分片数和行序允许不同，不参与逻辑内容哈希。
- `data_pipeline_run.json` 保存 block、batch、task/actor pool、原始 `Dataset.stats()` 和指标支持状态。
- 此步骤仍是单机软件级验证，不得声明多节点或大规模扩展。

### 6.2 Prepare an isolated 64 GiB workload and cost gate

GiB 表示 gibibyte（吉比字节，`2^30` 字节）。规模数据由冻结来源确定性回放，只用于基准测试：

```bash
uv run cdf benchmark prepare --source-snapshot data/raw/source_snapshot.yaml \
  --target-logical-gib 64 --seed 20260904 \
  --output-dir data/benchmarks/ray-64gib-v1 --json

uv run cdf benchmark budget --config configs/distributed/ray-scale-v1.yaml \
  --price-quote artifacts/quotes/ray-cpu-provider.json \
  --approved-cost-cap-cny APPROVED_CAP \
  --output-dir artifacts/data-benchmarks/ray-scale-v1 --json
```

`APPROVED_CAP` 必须替换为用户明确批准的 Ray CPU/存储预算。

Expected:

- manifest 中 100% 记录为 `BENCHMARK_ONLY`，包含稳定副本 ID、物理/逻辑字节和重建命令。
- 训练、开发、测试和 dataset publish 命令引用该 manifest 时退出 3。
- 预算覆盖 1/2/4 节点各一次预热、各 5 次实测、一次故障注入、共享存储和网络，并在创建集群前
  冻结停止上限；它与 GPU 卡时预算分账但进入最终总成本。

### 6.3 Run the fixed workload on real worker nodes

优先在 OpenBayes 分别创建 1、2、4 个同构 CPU 工作容器；官方文档确认同一创建人的运行中容器
可以通过私有 Internet Protocol（互联网协议，IP）地址和 Secure Shell（安全外壳协议，SSH）互通，
但这不自动证明 Ray 端口、IP 稳定性或共享可写存储。下面命令中的
地址与 CPU 数必须替换为真实值，Dashboard 保持本地绑定，不直接暴露公网；若后续探针失败，立即
关闭这些容器并在具备私网和共享对象存储的普通 Linux CPU 虚拟机上执行同一流程：

```bash
# head node
uv run ray start --head --num-cpus=0 --dashboard-host=127.0.0.1

# each worker node
uv run ray start --address=PRIVATE_HEAD_IP:6379 --num-cpus=CPUS_PER_WORKER
```

每次切换 1、2、4 节点拓扑后、正式 workload 前都运行一次无训练数据的集群探针：

```bash
uv run cdf benchmark preflight --config configs/distributed/ray-scale-v1.yaml \
  --ray-address auto --expected-worker-nodes WORKER_NODES \
  --shared-storage-uri SHARED_STORAGE_URI \
  --output-dir artifacts/data-runs/ray-scale-v1/preflight-WORKER_NODES-nodes --json
```

探针必须证明 head 的 Ray 计算 CPU 为零、节点身份互异、控制面与数据面端口可达、所有节点的
Python/Ray/`uv.lock` 一致，且能对同一共享存储完成逐节点读写 canary 和哈希核对。只有 SSH 或
公网服务映射成功不得继续。

对每种规模做一次不计入结果的预热，再按冻结随机顺序做 5 次实测；下面表示其中一次：

```bash
uv run cdf benchmark ray-data \
  --dataset data/benchmarks/ray-64gib-v1/benchmark_dataset_manifest.json \
  --config configs/distributed/ray-scale-v1.yaml \
  --ray-address auto --expected-worker-nodes WORKER_NODES --trial-index TRIAL_INDEX \
  --cluster-preflight artifacts/data-runs/ray-scale-v1/preflight-WORKER_NODES-nodes/ray_cluster_preflight.json \
  --budget artifacts/data-benchmarks/ray-scale-v1/ray_budget_projection.json \
  --output-dir artifacts/data-runs/ray-scale-v1/WORKER_NODES/TRIAL_INDEX --json
```

`WORKER_NODES` 依次为 1、2、4，`TRIAL_INDEX` 为 1–5。每次必须使用新输出前缀并记录 cold/warm
cache（冷/热缓存）状态，不能复用上次物化结果。再用冻结配置运行一次 worker 进程终止故障注入，
最后汇总：

```bash
uv run cdf benchmark ray-data \
  --dataset data/benchmarks/ray-64gib-v1/benchmark_dataset_manifest.json \
  --config configs/distributed/ray-scale-v1.yaml \
  --ray-address auto --expected-worker-nodes 4 --trial-index fault-1 \
  --fault-injection kill-one-worker-process \
  --cluster-preflight artifacts/data-runs/ray-scale-v1/preflight-4-nodes/ray_cluster_preflight.json \
  --budget artifacts/data-benchmarks/ray-scale-v1/ray_budget_projection.json \
  --output-dir artifacts/data-runs/ray-scale-v1/fault-1 --json

uv run cdf benchmark summarize \
  --runs-dir artifacts/data-runs/ray-scale-v1 \
  --local-baseline data/interim/clean/data_pipeline_run.json \
  --config configs/distributed/ray-scale-v1.yaml \
  --output-dir artifacts/data-benchmarks/ray-scale-v1 --json

uv run cdf report build \
  --scale-benchmark artifacts/data-benchmarks/ray-scale-v1/ray_scale_report.json \
  --output-dir reports/ray-scale-v1 --json

uv run cdf evidence verify --claims reports/ray-scale-v1/claims.json --strict --json
```

确认所有共享存储产物和账单引用已落盘后，在每个节点执行 `uv run ray stop` 并关闭云实例，避免空闲
计费。

Expected:

- 1/2/4 节点各有当前集群会话的 `ray_cluster_preflight.json`；失败探针和提供商切换原因也被保留。
- 节点快照和 tasks-per-node 证明 block 实际分布在 1/2/4 个独立工作节点，而非同机进程数。
- 15 次正式轮次全部保留，报告吞吐、墙钟时间、加速比、扩展效率、CPU/heap、对象存储、spill、
  shuffle、backpressure（背压）、重试、失败和实付成本。
- 各规模输出逻辑哈希完全一致。只有相对单节点吞吐提升的 95% 区间排除零提升时，才能声明被测
  workload 获得扩展收益；否则发布无加速、负加速和瓶颈分析。
- 故障注入结果一致且重试可见时，只能声明“被测 worker 进程失败的有界恢复”，不能声明节点级
  灾备、外部副作用 exactly-once（精确一次）或生产级稳定性。
- Ray worker 不执行不可信代码；安全执行仍由下一节的独立 gVisor 主机证明。

## 7. Prove or Downgrade Safe Execution

### 7.1 On the isolated Linux executor

```bash
uv run cdf verify preflight --config configs/execution/gvisor.yaml \
  --output-dir artifacts/runs/preflight --json
```

Expected preflight proof:

- 主机侧确认 runtime 是固定版本 `runsc`/`systrap`。
- 非 root、capabilities 全移除、no-new-privileges、网络关闭、根文件系统只读。
- 输入只读、输出为容量限制 tmpfs；CPU、内存、PID、文件和墙钟时间受限。
- 网络访问和权限提升 canary 被阻断。

### 7.2 Execute fixtures and candidates

```bash
uv run cdf verify run --dataset tests/fixtures/execution/samples.parquet \
  --preflight artifacts/runs/preflight/executor_preflight.json \
  --config configs/execution/python.yaml --repeat 2 \
  --output-dir artifacts/runs/verification-fixtures --json
```

Expected fixture outcomes:

| Fixture | Expected outcome |
|---|---|
| correct deterministic code | two `PASS`; summary `EXECUTION_PASS` |
| wrong implementation | `FAIL` |
| infinite loop | `TIMEOUT` |
| excessive allocation | `OOM` or policy resource failure |
| network attempt | `POLICY_BLOCKED`/test failure; no network access |
| nondeterministic output | `FLAKY` |
| generated weak test | execution recorded, but test strength below `NEGATIVE_CONTROL_REJECTED` |

如果 preflight 不通过，重复运行同一命令应退出 3，并生成软件级/阻断记录；不得自动改用 Docker
`runc` 或本地 subprocess。

## 8. Publish the Verified Task Pool and Matched SFT Datasets

```bash
uv run cdf dataset build --recipe verified --config configs/quality/verified.yaml \
  --source-snapshot data/raw/source_snapshot.yaml \
  --verification artifacts/runs/verification \
  --engine ray --ray-address auto \
  --output-dir data/interim/verified --json

uv run cdf dataset publish --draft data/interim/clean \
  --config configs/quality/publish.yaml --output-dir data/releases/clean-v1 --json
uv run cdf dataset publish --draft data/interim/verified \
  --config configs/quality/publish.yaml --output-dir data/releases/verified-v1 --json
```

在闭环策略冻结后，从同一个 `Verified` 任务—答案池构建 `SFT-RandomMatched`：

```bash
uv run cdf dataset build --recipe sft-random-matched \
  --config configs/quality/random-matched.yaml \
  --candidate-pool data/releases/verified-v1 \
  --engine ray --ray-address auto \
  --output-dir data/interim/random-matched --json
```

Expected:

- 每个发布包含不可变 manifest、membership、data card、质量/多样性报告和完整 lineage 表。
- `SFT-RandomMatched` 保存候选池哈希和任务类型、来源、难度、输入规模、测试强度、基线模型
  成功率的匹配平衡报告。
- 每个任务包保存冻结输入数据、目标 schema、隐藏数据质量/业务不变量、参考答案、验证器和变异
  证据；缺任一项不能进入正式 SFT 数据。可选 RL-ready 导出还必须保存可重放奖励，但不证明 RL。

## 9. Run Tiny SFT Compatibility and Calibration

首次租用 RTX 5090 时先记录实际报价和硬件，不直接开始正式实验。当前官网价是 2.9 元/卡时，
但正式计划以前必须重新核对：

```bash
pwd
nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv
df -h /openbayes/home
```

确认当前目录位于 `/openbayes/home`，显卡名称、每卡显存、可见卡数、驱动和持久空间均进入运行
环境记录。先用 3B–4B Instruct checkpoint 验证 SFT、保存、重载和评测链路，再用第一候选
`Qwen/Qwen3-8B` 执行单卡正式模型门禁：

```bash
uv run cdf experiment run --plan configs/experiments/pipeline-smoke-4b.yaml \
  --recipe sft-random-matched --seed 17 --output-dir artifacts/runs/train-smoke --json
uv run cdf experiment run --plan configs/experiments/model-gate-qwen3-8b.yaml \
  --recipe sft-random-matched --seed 17 --output-dir artifacts/runs/train-smoke --json
uv run cdf reward replay --candidates data/releases/verified-v1 \
  --output-dir artifacts/runs/reward-replay --json
uv run cdf experiment select-model --config configs/experiments/model-selection.yaml \
  --runs-dir artifacts/runs/train-smoke \
  --output-dir artifacts/runs/model-selection --json
```

Expected:

- 3B–4B 只验证软件链路，不成为正式效果测量模型；8B 候选只训练 0.25M 有效词元，冒烟结果不
  成为模型提升证据。
- 冻结 8B 候选的精确 revision、tokenizer/chat-template 哈希、Python/CUDA/PyTorch/TRL/PEFT 版本、OpenBayes
  运行时镜像标识和平台可提供的镜像 digest；平台不暴露 digest 时记录复现限制。
- 记录未训练基线、峰值与实测可用显存、每秒有效词元、卡时和实付金额，并验证完整权重或 adapter
  保存与重载。全参数微调、低秩适配（Low-Rank Adaptation，LoRA）和量化低秩适配
  （Quantized LoRA，QLoRA）只参加事前可行性门禁；峰值显存、数值稳定性、重载、六次运行成本或
  简化边界未通过的候选被拒绝，正式矩阵只冻结一种方法。
- 可选 RL-ready 数据保存任务、候选答案、最终数据产物、验证器执行和奖励分量；重放不一致时
  取消 RL-ready 标记，但不阻止合格 SFT 数据继续使用。
- 输出 `model_selection.json`；任何冒烟指标都不能发布为模型提升结论。

运行训练方法门禁；它不比较三种方法的最终能力：

```bash
uv run cdf experiment select-training-method \
  --config configs/experiments/training-method-selection.yaml \
  --runs-dir artifacts/runs/method-gates \
  --output-dir artifacts/runs/training-method-selection --json
```

随后执行 `SFT-RandomMatched` 和 `SFT-ClosedLoop` 各一次单种子校准，验证单卡显存、吞吐、
checkpoint、等有效词元、评测灵敏度、成本预测和中断恢复；它不是正式结论。

```bash
uv run cdf experiment calibrate \
  --training-method-selection artifacts/runs/training-method-selection/training_method_selection.json \
  --runs artifacts/runs/train-calibration \
  --output-dir artifacts/runs/train-calibration --json
```

## 10. Freeze the Budget Before Formal Results

用真实报价和校准运行生成预算：

```bash
uv run cdf experiment budget --price-cny-per-gpu-hour 2.90 \
  --model-selection artifacts/runs/model-selection/model_selection.json \
  --training-method-selection artifacts/runs/training-method-selection/training_method_selection.json \
  --calibration-run artifacts/runs/train-calibration/training_run.json \
  --soft-budget-cny 5000 --max-budget-cny 10000 --reserve 0.15 \
  --output-dir artifacts/runs/budget --json
```

根据校准选择六个正式运行的统一有效训练词元、步数和曝光预算，并在任何正式结果产生前预登记：

```bash
uv run cdf experiment preregister --config configs/experiments/sft-main.yaml \
  --budget artifacts/runs/budget/budget_projection.json \
  --output-dir artifacts/runs/plans/sft-main --json
```

超过 5,000 元时，先准备 `budget_exception.yaml`。它只能用于保住核心两组、三个种子、基础设施
失败重跑或独立复现，最高约 10,000 元；不能用于看到正向结果后加练某一组。CPT、RL 和额外模型
规模不是扩支理由。

Expected plan equality:

- 同一比较的初始 checkpoint、tokenizer/chat template、有效训练 token、步数、曝光/排序、验证器、
  解码、冻结训练方法及配置、优化器、单卡硬件、seeds `[17,29,43]` 和评测版本相同。
- `planned_loss_tokens` 必须等于 `observed_loss_tokens`；不等时不能发布因果结论。
- 共同初始 checkpoint 只作背景分数，不登记成等预算 control（对照）。

## 11. Establish the Evaluation Baseline

```bash
uv run cdf evaluate run --base-model configs/experiments/frozen-model.yaml \
  --suite configs/evaluation/external-code-v1.yaml --split development \
  --output-dir artifacts/evaluations/base-external-development --json
uv run cdf evaluate run --base-model configs/experiments/frozen-model.yaml \
  --suite configs/evaluation/data-engineering-v1.yaml --split development \
  --output-dir artifacts/evaluations/base-development --json
```

Expected:

- 外部层分别保存 LiveCodeBench version 6 `pass@1`、DataSciBench 确定性子集分项和 BIRD 或
  Spider 2.0-lite 执行准确率；任何子集、prompt、runner 或解码偏离都进入 `protocol_deviation`，
  不合成一个外部总分。
- 项目层保存逐项生成程序、最终数据产物、隐藏断言、执行结果、错误类别和切片。
- 项目主指标为一次生成 `ArtifactPass@1`；另有 `RepairPass@1`、任务模板/仓库/输入数据集三重
  不相交的 `HeldOutArtifactPass@1`、推理成本、安全和外部能力护栏。
- test split 此时仍无法执行或读取。

## 12. Build One Real Feedback Loop

```bash
uv run cdf feedback build \
  --evaluation artifacts/evaluations/base-development/evaluation_run.json \
  --policy configs/quality/feedback-v1.yaml \
  --candidate-pool data/releases/verified-v1 \
  --output-dir data/interim/closed-loop-v1 --json

uv run cdf dataset publish --draft data/interim/closed-loop-v1 \
  --config configs/quality/publish.yaml \
  --output-dir data/releases/closed-loop-v1 --json
```

Expected:

- 每个 finding（评测发现）关联逐项开发集证据、能力切片和优先级。
- 每个新增、修复、重选、降权、删除或复核动作关联 finding 和复验计划。
- `SFT-ClosedLoop` 与 `SFT-RandomMatched` 来自同一个 `Verified` 候选池，且匹配字段分布满足预登记容差。
- 反馈链中不存在 test item ID。

## 13. Run Formal SFT Data Comparisons

对每个 recipe 和 seed 独立启动；下面只展示一个运行：

```bash
uv run cdf experiment run \
  --plan artifacts/runs/plans/sft-main/experiment_plan.yaml \
  --recipe sft-closed-loop --seed 17 \
  --output-dir artifacts/runs/training --json
```

实际租到 `N` 张 RTX 5090 时，每卡运行一个独立 SFT 作业，并发上限为 `N`；资源不足时分批完成，
并轮换 recipe 到物理实例的映射。不要让某一组单独改变拓扑。运行失败、中止、欠费关停或预算
阻断都保留。默认租 2–4 张卡并行；租 8 张卡只缩短墙钟时间，不会降低总卡时。

Formal comparison: `SFT-ClosedLoop - SFT-RandomMatched`。它只回答“在相同 SFT 方法、验证器和
有效训练词元预算下，评测反馈驱动的数据选择是否提高端到端数据工程任务成功率”。共同初始
checkpoint 与任一训练模型的差值只是观测背景，不发布成等预算数据归因。CPT/RL 不进入正式矩阵。

## 14. Evaluate Test and Publish Claims

只有所有 closed-loop 数据冻结后才运行 test：

```bash
uv run cdf evaluate run --model-run artifacts/runs/training/<run-id>/training_run.json \
  --suite configs/evaluation/external-code-v1.yaml --split test \
  --output-dir artifacts/evaluations --json

uv run cdf evaluate run --model-run artifacts/runs/training/<run-id>/training_run.json \
  --suite configs/evaluation/data-engineering-v1.yaml --split test \
  --output-dir artifacts/evaluations --json

uv run cdf report build \
  --experiment-plan artifacts/runs/plans/sft-main/experiment_plan.yaml \
  --output-dir reports/sft-main --json

uv run cdf evidence verify --claims reports/sft-main/claims.json --strict --json
```

A model-effect claim may say “data strategy improved the model” only when:

1. 处理组和对照组三个种子均真实完成参数更新。
2. 每运行计划和实测有效训练 token 完全相等，其他冻结配置一致。
3. 项目套件的 `ArtifactPass@1` 正向，paired bootstrap（配对自助法）95% 置信区间下界大于 0。
4. 通用、未见仓库和安全护栏没有超过预登记回退阈值。
5. 数据、训练、评测、成本和报告谱系完整。

否则报告必须写为负向、无变化、趋势、不确定、失败或未运行。软件通过、沙箱执行通过、论文收益、
数据量和预测收益都不能替代这五项条件。

## 15. Reproduce One Claim Independently

```bash
dvc pull
uv sync --frozen
uv run cdf reproduce --claim-id <claim-id> \
  --manifest reports/sft-main/lineage_index.json \
  --output-dir artifacts/reproductions/<claim-id> --json
```

Expected:

- 固定来源、数据清单、配置和环境可定位。
- 确定性数据产物 logical content hash 一致。
- 非确定性模型运行只允许预登记字段和容差内差异，并逐字段解释。
- 从 claim 可反查所有 artifact，从来源/数据/运行可正查受影响 claim。

## 16. Final Acceptance Checklist

- 七项目标能力各有至少一个产物和明确证据层级。
- 100% 发布样本具有来源、动作、切片、切分和验证状态。
- 本地/Ray 单节点业务输出等价；真实 1/2/4 工作节点各 5 次运行、故障注入、资源/性能/成本和
  负结果均有原始证据，否则明确标记 Ray 多节点目标未满足。
- 100% `EXECUTION_VALIDATED` 样本有合格 preflight 与原始重复运行证据。
- 至少一条开发评测 finding → data action → 新数据版本 → 复评链完整。
- 正向、负向、无变化、失败、中止和预算阻断运行均能在报告中定位。
- 大模型方法资料通过宪章时效门禁；组件不按首次发布日期误淘汰。
- 最终报告不宣称多模态、互联网规模、PB/EB 基础设施、数据库内核或组织级平台成果。
- 每个用户故事 checkpoint 都同期更新了 `docs/evidence-journal.md` 中的真实难点/取舍，或保存了
  关联任务和产物的无新增检查点回执；“使用组件”或“修改参数”没有被单独包装成解决方案。
