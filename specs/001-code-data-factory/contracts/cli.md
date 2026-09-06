# Command-Line Interface Contract

## General Contract

命令行程序名为 `cdf`，所有可变数据通过显式配置和产物路径传入。命令默认输出人可读摘要；加
`--json` 后，标准输出只包含一个符合 Pydantic 契约的 JSON 对象，日志写到标准错误。所有相对路径
以仓库根目录解析。

本文中的 DVC 表示 Data Version Control（数据版本控制），CPU 表示 Central Processing Unit
（中央处理器），GPU 表示 Graphics Processing Unit（图形处理器）。

通用参数：

```text
--config PATH          版本化 YAML 配置
--output-dir PATH      产物目录
--contract-version V   预期契约版本；不兼容则失败
--json                 机器可读输出
--dry-run              验证输入、依赖、预算和写入计划，不执行外部副作用
```

每个成功响应至少包含：

```json
{
  "command": "cdf ...",
  "status": "SUCCEEDED",
  "run_id": "run_<sha256>",
  "contract_version": "1.0.0",
  "input_hashes": {},
  "artifact_refs": [],
  "warnings": [],
  "evidence_level": "SOFTWARE_VALIDATED"
}
```

`run_id` 对相同冻结输入和配置保持稳定，attempt（尝试）另有唯一编号。命令发现目标产物已存在且
哈希一致时返回成功并标记 `reused=true`；路径存在但哈希不一致时失败，不覆盖。

## Exit Codes

| Code | Symbol | Meaning |
|---:|---|---|
| 0 | `OK` | 命令成功，或幂等复用已有一致产物 |
| 2 | `INVALID_INPUT` | 参数、配置或契约验证失败 |
| 3 | `POLICY_BLOCKED` | 许可、污染、安全 preflight 或证据门禁阻断 |
| 4 | `DEPENDENCY_UNAVAILABLE` | 可选外部模型、GPU、Ray 集群、gVisor 或共享存储不可用 |
| 5 | `EXECUTION_FAILED` | 流水线/执行/训练/评测运行失败；原始失败产物已保存 |
| 6 | `HASH_MISMATCH` | 已有产物或重建结果与清单哈希不一致 |
| 7 | `BUDGET_BLOCKED` | 预计或实付金额超过获批预算 |
| 8 | `EVIDENCE_INCOMPLETE` | 请求的证据层级缺少必要产物 |
| 10 | `INTERNAL_ERROR` | 未分类软件错误；不能伪装成样本失败 |

## Commands

### `cdf source freeze`

冻结 allowlist 内的来源并生成 `SourceSnapshot`。

```text
cdf source freeze --config configs/sources/python.yaml --output-dir data/raw --json
```

Inputs: 来源 URI、完整 Git revision、许可预期、路径/大小上限。  
Outputs: `source_snapshot.yaml`, `files.parquet`, `license/`, DVC 跟踪建议。  
Gate: revision 非 40 位提交哈希、许可不明确、超过有界规模或文件哈希失败时退出 2/3。

### `cdf governance scan`

运行许可、明显密钥、个人可识别信息和冻结评测污染检查。

```text
cdf governance scan --dataset data/raw/source_snapshot.yaml \
  --policy configs/quality/governance.yaml --output-dir data/interim/governed --json
```

Outputs: `quality_assessments.parquet`, `quarantine.parquet`, `governance_summary.json`。  
Gate: 扫描器合成 canary 未命中时退出 3；零发现只表示本次方法未发现，不输出“无风险”结论。

### `cdf dataset build`

解析、规范化、去重、生成和切片候选数据。

```text
cdf dataset build --recipe clean --config configs/quality/clean.yaml \
  --source-snapshot data/raw/source_snapshot.yaml \
  --evaluation-index data/releases/eval-index.json \
  --engine ray --ray-address auto \
  --output-dir data/interim/clean --json
```

`--recipe` values: `clean | verified | random-matched | closed-loop | cpt-minimal | cpt-governed`。  
`--engine` values: `local | ray`；`ray` 必须给出 `--ray-address` 或受控配置，`local` 用于小数据测试和
正确性基线。两种模式调用相同业务算子。  
Outputs: `samples.parquet`, `transformations.parquet`, `dedup_clusters.parquet`,
`contamination_edges.parquet`, `slice_membership.parquet`, `data_pipeline_run.json`。  
Gate: 同一 dedup cluster 跨 split、污染阻断样本入选或谱系成环时退出 3。

### `cdf benchmark prepare`

从冻结来源确定性构建只用于系统规模实验的 Ray 数据集，不构造新的训练来源。

```text
cdf benchmark prepare --source-snapshot data/raw/source_snapshot.yaml \
  --target-logical-gib 64 --seed 20260904 \
  --output-dir data/benchmarks/ray-64gib-v1 --json
```

Outputs: `benchmark_dataset_manifest.json` 和分片 Parquet。  
Gate: 每条记录必须具有 `usage_scope=BENCHMARK_ONLY`、稳定 `benchmark_sample_id` 和副本序号；
目标目录不得位于 `data/releases/`，任何训练/评测 membership 引用都会退出 3。

### `cdf benchmark preflight`

在已启动但尚未执行正式 workload 的 Ray 集群上运行有界 canary，验证实际节点、私网、版本、资源
和共享存储。OpenBayes 或其他提供商使用同一契约。

```text
cdf benchmark preflight --config configs/distributed/ray-scale-v1.yaml \
  --ray-address auto --expected-worker-nodes 4 \
  --shared-storage-uri SHARED_STORAGE_URI \
  --output-dir artifacts/data-runs/ray-scale-v1/preflight-4-nodes --json
```

Outputs: `ray_cluster_preflight.json`、哈希化节点快照、端口检查和每节点共享存储 canary 引用。  
Gate: head 暴露计算资源、实际独立 worker 数/规格不符、私网 Ray 控制面或数据面不可达、Python/Ray/
锁文件不一致，或任一节点无法读写同一共享存储时退出 3/4。只有 Secure Shell（安全外壳协议，
SSH）或公网端口映射成功不足以通过；失败结果仍保存，且不得启动正式 64 GiB 运行。

### `cdf benchmark ray-data`

在已由用户或云平台创建的 Ray 集群上运行一次冻结 workload。`worker-nodes` 指实际独立 Linux
虚拟机或物理机，不是同机 worker 进程。

```text
cdf benchmark ray-data \
  --dataset data/benchmarks/ray-64gib-v1/benchmark_dataset_manifest.json \
  --config configs/distributed/ray-scale-v1.yaml \
  --ray-address auto --expected-worker-nodes 4 --trial-index 1 \
  --cluster-preflight artifacts/data-runs/ray-scale-v1/preflight-4-nodes/ray_cluster_preflight.json \
  --budget artifacts/data-benchmarks/ray-scale-v1/ray_budget_projection.json \
  --output-dir artifacts/data-runs/ray-4n-trial-1 --json
```

`--fault-injection` values: `none | kill-one-worker-process`，默认 `none`；故障注入只允许在
`BENCHMARK_ONLY` workload 上运行，不能终止训练或安全执行 worker。  

Outputs: `data_pipeline_run.json`, `operator_metrics.parquet`, 原始 `dataset_stats.txt`,
`retry_and_failure_events.parquet`, logs 和 artifact index。  
Gate: 通过的集群探针必须属于当前集群会话和节点规模；实际工作节点数/规格、Ray/Python/锁文件、
block 数、共享存储或预算与冻结配置不符时退出 2/3/7；输出核对失败时退出 6。系统失败允许冻结
配置规定的有限重试，普通业务异常不自动重试。

### `cdf benchmark budget`

在创建多节点集群前冻结 CPU 节点、共享存储和网络的报价与停止上限。

```text
cdf benchmark budget --config configs/distributed/ray-scale-v1.yaml \
  --price-quote artifacts/quotes/ray-cpu-provider.json \
  --approved-cost-cap-cny APPROVED_CAP \
  --output-dir artifacts/data-benchmarks/ray-scale-v1 --json
```

Outputs: `ray_budget_projection.json`。  
Gate: 报价、1/2/4 节点各一次预热与 5 次正式运行、故障注入、存储/网络估算或审批上限缺失时
退出 2；`APPROVED_CAP` 必须替换为用户实际批准值，不提供隐含默认预算。

### `cdf benchmark summarize`

把预热、1/2/4 节点各 5 次正式运行和故障注入运行汇总为不可变伸缩报告。

```text
cdf benchmark summarize \
  --runs-dir artifacts/data-runs/ray-scale-v1 \
  --local-baseline data/interim/clean/data_pipeline_run.json \
  --config configs/distributed/ray-scale-v1.yaml \
  --output-dir artifacts/data-benchmarks/ray-scale-v1 --json
```

Outputs: `raw_trials.parquet`, `ray_scale_report.json`, `fault_injection.json`。  
Gate: 任一正式轮次、实际节点分布、输出等价、原始资源/成本证据缺失时标记 `INCOMPLETE` 并退出
8；只有吞吐提升区间排除零提升时可输出 `MEASURED_SCALE_OUT`。单机 Ray 运行不能填入 2/4 节点槽位。

### `cdf verify preflight`

在执行主机验证 gVisor、容器策略、网络/权限 canary 和资源限制。

```text
cdf verify preflight --config configs/execution/gvisor.yaml \
  --output-dir artifacts/runs/preflight --json
```

Outputs: `executor_preflight.json`, 原始主机侧 inspection 和 canary 日志。  
Gate: 任一必需控制失败时退出 3。输出不得宣称样本已执行验证。

### `cdf verify run`

对候选样本执行至少两次编译/测试和负对照审计。

```text
cdf verify run --dataset data/interim/clean/samples.parquet \
  --preflight artifacts/runs/preflight/executor_preflight.json \
  --config configs/execution/python.yaml --repeat 2 \
  --output-dir artifacts/runs/verification --json
```

Outputs: `verification_attempts.parquet`, `verification_summary.parquet`, bounded stdout/stderr。  
Gate: preflight 缺失/过期时退出 3，不允许自动切换 `runc`；不稳定结果为 `FLAKY`，不是命令内部错误。

### `cdf dataset publish`

把草稿数据版本冻结为不可变发布。

```text
cdf dataset publish --draft data/interim/verified \
  --config configs/quality/publish.yaml --output-dir data/releases/verified-v1 --json
```

Outputs: `dataset_manifest.json`, `membership.parquet`, `data_card.md`, `quality_report.json`,
`diversity_report.json`。  
Gate: 治理、切分、谱系、哈希或数据卡不完整时退出 8；已发布目录不覆盖。

### `cdf experiment select-model`

验证候选模型的官方身份、许可、未训练基线、显存、真实反向传播以及检查点重载，并在正式结果可见
前冻结选择。

```text
cdf experiment select-model --config configs/experiments/model-selection.yaml \
  --runs-dir artifacts/runs/model-gates \
  --output-dir artifacts/runs/model-selection --json
```

Outputs: `model_selection.json`。  
Gate: 第一候选真实门禁失败时只能按配置中的冻结顺序尝试下一候选；3B–4B 链路冒烟不能替代 8B
正式模型门禁，视觉模型不能进入纯文本正式矩阵。

### `cdf experiment select-training-method`

在正式结果产生前，以同一冻结校准样本核验全参数微调、低秩适配（Low-Rank Adaptation，LoRA）
和量化低秩适配（Quantized LoRA，QLoRA）的单卡可行性，并只冻结一种方法供所有正式配方和种子
使用。

```text
cdf experiment select-training-method \
  --config configs/experiments/training-method-selection.yaml \
  --runs-dir artifacts/runs/method-gates \
  --output-dir artifacts/runs/training-method-selection --json
```

Outputs: `training_method_selection.json`。  
Gate: 候选必须完成真实反向传播、保留至少 10% 显存余量、产生有限 loss、成功保存和重载，并在
预算内保留两个配方、三个种子及 15% 余量；需要项目新增分布式训练平台的候选直接拒绝。门禁只
选择一种方法，不发布全参数/LoRA/QLoRA 的能力比较。

### `cdf experiment budget`

根据 OpenBayes RTX 5090 实际报价和兼容性冒烟吞吐计算各档位成本；当前公开报价为 2.9 元/卡时，
并发数只影响完成时间，不改变总卡时。正式预登记前仍须保存当时的报价快照。

```text
cdf experiment budget --price-cny-per-gpu-hour 2.90 \
  --model-selection artifacts/runs/model-selection/model_selection.json \
  --training-method-selection artifacts/runs/training-method-selection/training_method_selection.json \
  --calibration-run artifacts/runs/train-calibration/training_run.json \
  --soft-budget-cny 5000 --max-budget-cny 10000 --reserve 0.15 --json
```

Outputs: `budget_projection.json`，包含每运行和总词元、卡时、金额、余量及可行档位。  
Gate: 不接受缺少实际吞吐的正式预算；示例价格仅演示参数，不是计划报价。

### `cdf experiment preregister`

冻结实验假设、数据组、训练预算、种子、指标、护栏和判定规则。

```text
cdf experiment preregister --config configs/experiments/sft-main.yaml \
  --budget artifacts/runs/budget_projection.json \
  --output-dir artifacts/runs/plans/sft-main --json
```

Outputs: `experiment_plan.yaml`, `plan_sha256.txt`。  
Gate: 数据集未冻结、组间预算不等、测试套件未冻结、预算超限或超过 5,000 元但无事前例外记录时
退出 3/7/8。

### `cdf experiment run`

调用外部 TRL/PEFT/Accelerate 训练入口；本项目不实现优化器。

```text
cdf experiment run --plan artifacts/runs/plans/sft-main/experiment_plan.yaml \
  --recipe verified --seed 17 --output-dir artifacts/runs/training --json
```

Outputs: `training_run.json`, 训练日志、指标、检查点 ArtifactRef 和 MLflow run ID。  
Gate: 计划未预登记、模型/数据/配置哈希不符或预算不足时拒绝启动。运行失败仍写终态记录并退出 5。

### `cdf evaluate run`

对基础或训练检查点运行版本化评测并保留逐项结果。

```text
cdf evaluate run --model-run artifacts/runs/training/<run-id>/training_run.json \
  --suite configs/evaluation/external-code-v1.yaml --split development \
  --output-dir artifacts/evaluations --json

cdf evaluate run --model-run artifacts/runs/training/<run-id>/training_run.json \
  --suite configs/evaluation/data-engineering-v1.yaml --split development \
  --output-dir artifacts/evaluations --json
```

`--split` values: `development | test`。  
Outputs: `evaluation_run.json`, `evaluation_items.parquet`, `raw_predictions.parquet`,
`summary_metrics.json`。  
Gate: `test` 在 `ClosedLoop` 数据冻结前不可运行；安全代码指标缺少合格 executor preflight 时降级或
退出 3。外部 suite 必须冻结 benchmark revision、官方协议、runner 镜像和偏离记录；运行子集或改动
prompt/解码/执行器时不得输出完整官方 leaderboard 声明。项目 suite 必须标记 `project_extension=true`，
两层分数不得合成一个总分。

### `cdf feedback build`

把开发集逐项错误映射为 finding、数据动作和新数据版本。

```text
cdf feedback build --evaluation artifacts/evaluations/<eval-id>/evaluation_run.json \
  --policy configs/quality/feedback-v1.yaml --candidate-pool data/releases/verified-v1 \
  --output-dir data/interim/closed-loop-v1 --json
```

Outputs: `evaluation_findings.parquet`, `data_actions.parquet`, closed-loop draft。  
Gate: 任何输入引用 test split 时退出 3；每个非随机 membership 变化必须关联 finding 和 action。

### `cdf report build`

从规范产物生成机器清单和静态 Markdown 报告。

```text
cdf report build --experiment-plan artifacts/runs/plans/sft-main/experiment_plan.yaml \
  --output-dir reports/sft-main --json
```

`--experiment-plan` 与 `--scale-benchmark` 二选一。Ray 报告使用：

```text
cdf report build \
  --scale-benchmark artifacts/data-benchmarks/ray-scale-v1/ray_scale_report.json \
  --output-dir reports/ray-scale-v1 --json
```

Outputs: `report.md`, `report.json`, `claims.json`, `lineage_index.json`。  
Gate: 缺少预登记运行时必须把状态显示为失败/中止/未运行，不能省略；Ray 报告缺少真实节点分布、
输出等价、5 次轮次或成本时只能生成 `INCOMPLETE`/负结果，不得输出扩展收益。

### `cdf evidence verify`

验证 claim 的证据层级、哈希、预算、运行覆盖和反向谱系。

```text
cdf evidence verify --claims reports/sft-main/claims.json --strict --json
```

`--strict` 表示任一 claim 需要降级时退出 8；不加时生成降级后的候选清单，但不覆盖原报告。

### `cdf reproduce`

从冻结输入重建指定数据集、运行或 claim。

```text
cdf reproduce --claim-id claim_<sha256> --manifest reports/sft-main/lineage_index.json \
  --output-dir artifacts/reproductions/<claim-id> --json
```

Outputs: `reproduction_run.json`, 重新计算的哈希和差异报告。  
Gate: 外部依赖不可用时退出 4 并保持原证据层级；哈希差异退出 6，除非差异落入预登记容差并有
逐字段解释。

## Budget Exception Record

超过 5,000 元软上限但不超过 10,000 元时，`cdf experiment preregister` 要求以下独立 YAML：

```yaml
reason_code: PRESERVE_CORE_SEEDS
requested_budget_cny: 7600
created_before_formal_results: true
price_quote_ref: artifact_<sha256>
calibration_run_ids:
  - train_<sha256>
required_remaining_runs:
  - recipe: clean
    seed: 43
estimated_cost_cny: 2410
alternatives_considered:
  - reduce_cpt_to_exploratory
  - use_minimum_token_tier
result_sensitive_allocation: false
```

允许的 `reason_code` 只有 `PRESERVE_CORE_CONTROLS | PRESERVE_CORE_SEEDS | INFRASTRUCTURE_RERUN |
INDEPENDENT_REPRODUCTION`。CPT 正式实验、扩展词元和界面开发不是预算例外理由。
