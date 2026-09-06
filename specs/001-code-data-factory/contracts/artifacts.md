# Artifact Contracts

本文中的 DVC 表示 Data Version Control（数据版本控制），CPU 表示 Central Processing Unit
（中央处理器），GPU 表示 Graphics Processing Unit（图形处理器），RNG 表示 random number
generator（随机数生成器），CNY 表示人民币计价单位，SSH 表示 Secure Shell（安全外壳协议），
HTTP 表示 Hypertext Transfer Protocol（超文本传输协议）。
LoRA 表示 Low-Rank Adaptation（低秩适配），QLoRA 表示 Quantized LoRA（量化低秩适配）。

## Canonical Encoding and Hashing

- JSON 使用 UTF-8、对象键字典序、无非语义空白、禁止 NaN/Infinity；`sha256` 对规范字节计算。
- YAML 是人工维护输入格式；预登记时先解析为规范 JSON，再计算 `plan_sha256`。YAML 注释不进入哈希。
- Parquet 使用显式 Arrow Schema 和 `contract_version`。每个物理文件保存 blob SHA-256；数据集
  `logical_content_hash` 对按主键排序后的行级规范摘要计算，避免仅因 row group（行组）布局变化而
  误判逻辑内容变化。
- Markdown 是派生产物，不是事实源；报告数值必须从 JSON/Parquet 重建。
- 路径均存项目相对 URI 或 DVC/MLflow URI，不保存本机绝对路径和凭据。

## Required Directory Bundle

```text
data/releases/<dataset-id>/
├── dataset_manifest.json
├── membership.parquet
├── data_card.md
├── quality_report.json
├── diversity_report.json
└── lineage/
    ├── source_snapshots.parquet
    ├── transformations.parquet
    ├── quality_assessments.parquet
    ├── dedup_clusters.parquet
    └── verification_attempts.parquet

artifacts/data-runs/<data-pipeline-run-id>/
├── data_pipeline_run.json
├── operator_metrics.parquet
├── dataset_stats.txt
├── retry_and_failure_events.parquet
├── stdout.log
├── stderr.log
└── artifact_index.json

artifacts/data-benchmarks/<scale-benchmark-id>/
├── benchmark_dataset_manifest.json
├── ray_budget_projection.json
├── ray_scale_report.json
├── raw_trials.parquet
├── fault_injection.json
└── artifact_index.json

artifacts/runs/<training-run-id>/
├── training_run.json
├── metrics.jsonl
├── stdout.log
├── stderr.log
└── artifact_index.json

artifacts/runs/training-method-selection/
├── training_method_selection.json
└── artifact_index.json

artifacts/evaluations/<evaluation-run-id>/
├── evaluation_run.json
├── evaluation_items.parquet
├── raw_predictions.parquet
├── summary_metrics.json
└── artifact_index.json

reports/<report-id>/
├── report.md
├── report.json
├── claims.json
├── lineage_index.json
└── artifact_index.json
```

## Source Artifacts

### `source_snapshot.yaml`

Required keys:

```yaml
contract_version: 1.0.0
source_snapshot_id: source_<sha256>
source_type: GIT
uri: https://example.invalid/org/repo.git
revision: 0123456789abcdef0123456789abcdef01234567
license_id: Apache-2.0
license_evidence_ref: {artifact_id: artifact_<sha256>, uri: "...", media_type: text/plain, byte_size: 1, sha256: "..."}
acquired_at: 2026-09-03T00:00:00Z
file_count: 0
line_count: 0
manifest_ref: {artifact_id: artifact_<sha256>, uri: "...", media_type: application/vnd.apache.parquet, byte_size: 1, sha256: "..."}
governance_status: ACCEPTED
```

`files.parquet` primary key: `(source_snapshot_id, relative_path)`。Required columns: `relative_path`,
`byte_size`, `line_count`, `blob_sha256`, `language`, `license_id`, `is_symlink`, `included`。符号链接默认
不跟随；路径逃逸会阻断来源。

## Data Tables

### `samples.parquet`

Primary key: `sample_id`。Columns 与 `data-model.md#3-data-sample` 一致；大型代码内容只存
`content_uri` 和 `content_sha256`。列表字段使用 Arrow list，不把 JSON 字符串塞进普通文本列。

### `transformations.parquet`

Primary key: `transformation_id`。`input_sample_ids`/`output_sample_ids` 使用 list；配置和证据引用必须
有 SHA-256。运行完成后不得 update，只能追加纠正记录。

### `quality_assessments.parquet`

Primary key: `assessment_id`。`raw_value_json` 使用规范 JSON；每行只表达一个质量维度和一种方法。
跨维度决策在发布阶段计算，不创建不可解释的全局质量分数。

### `dedup_clusters.parquet`

Primary key: `(cluster_id, sample_id)`。Required columns: `method_version`, `candidate_method`,
`exact_metric`, `score`, `threshold`, `representative_sample_id`, `assigned_split`, `evidence_sha256`。

### `contamination_edges.parquet`

Primary key: `edge_id`。Required columns: `train_sample_id`, `evaluation_item_id`, `method`, `score`,
`threshold`, `decision`, `evidence_uri`, `evidence_sha256`, `checked_at`。

### `verification_attempts.parquet`

Primary key: `attempt_id`。必须逐次保存，不能只保存汇总布尔值。资源不受运行时支持时使用
`resource_metric_supported=false`，不能伪造 0。

### `membership.parquet`

Primary key: `(dataset_id, sample_id, split)`。Required columns: `weight`, `exposure_count`,
`selection_rank`, `selection_reason`, `dedup_cluster_id`, `membership_sha256`。

## Dataset Manifest

### `dataset_manifest.json`

```json
{
  "contract_version": "1.0.0",
  "dataset_id": "dataset_<sha256>",
  "name": "verified-v1",
  "recipe": "VERIFIED",
  "status": "PUBLISHED",
  "parent_dataset_ids": ["dataset_<sha256>"],
  "source_snapshot_ids": ["source_<sha256>"],
  "tokenizer": {
    "model_id": "frozen-model-id",
    "revision": "frozen-revision",
    "sha256": "<sha256>"
  },
  "counts": {
    "sample_count": 0,
    "unique_sample_count": 0,
    "effective_token_supply": 0
  },
  "split_counts": {"TRAIN": 0, "DEVELOPMENT": 0, "TEST": 0},
  "artifact_refs": [],
  "lineage": {
    "git_commit": "<40-hex>",
    "uv_lock_hash": "<sha256>",
    "dvc_pipeline_revision": "<sha256>"
  },
  "content_hash": "<sha256>",
  "created_at": "2026-09-03T00:00:00Z",
  "frozen_at": "2026-09-03T00:00:00Z"
}
```

Validation:

- `status=PUBLISHED` 时所有 ArtifactRef 必须存在且哈希匹配。
- `recipe=RANDOM_MATCHED|CLOSED_LOOP` 时必须含 `candidate_pool_hash`、`matching_policy_hash` 和各匹配
  变量的平衡报告引用。
- `recipe=VERIFIED` 时必须给出执行环境 preflight 和 `EXECUTION_PASS` membership 比例；没有安全
  环境时不能发布该 recipe，可发布名称不同的 software-only 草稿。
- 任何 `usage_scope=BENCHMARK_ONLY` 或 `sample_kind=BENCHMARK_REPLICA` 记录进入 membership 时发布
  失败；`benchmark_sample_count` 必须为 0。

### `data_card.md`

Required headings: Purpose, Sources and Licenses, Generation, Governance, Verification Evidence,
Quality, Diversity, Splits and Contamination, Known Gaps, Intended Use, Prohibited Use, Lineage,
Reproduction。每个表格数值旁边引用 JSON/Parquet artifact ID。

## Distributed Data Processing Artifacts

### `ray_cluster_preflight.json`

Required keys: `provider`, `cluster_id`, `checked_at`, `head_node_id_hash`,
`worker_node_id_hashes`, `expected_worker_node_count`, `private_ip_reachability`, `ray_port_checks`,
`python_versions`, `ray_versions`, `uv_lock_hashes`, `worker_resource_shapes`,
`head_compute_resources_zero`, `shared_storage_read_write_canary_refs`, `result`, `artifact_sha256`。

Gate: `result=PASS` 要求实际独立节点数与预期相同、head 不参与计算、私网 Ray 控制面和数据面可达、
Python/Ray/锁文件一致、worker 同构，并且每个节点都能读取同一输入 canary、写入唯一输出且由 driver
核对哈希。只有 SSH 成功、公网 HTTP/WebSocket 映射成功或配置声明节点数均不能通过。

### `benchmark_dataset_manifest.json`

Required keys:

- `benchmark_dataset_id`, `source_snapshot_ids`, `replay_policy_sha256`, `seed`
- `usage_scope=BENCHMARK_ONLY`, `record_count`, `input_file_count`
- `physical_storage_bytes`, `logical_payload_bytes`；首版正式规模的后者至少为 64 gibibyte
  （吉比字节，GiB；`2^30` 字节）
- `benchmark_replica_index_range`, `sample_id_set_sha256`, `schema_sha256`
- `file_refs`, `created_at`, `manifest_sha256`, `rebuild_command`

Gate: 所有行都必须有稳定 `benchmark_sample_id` 和 `BENCHMARK_ONLY`；输出不得与 `data/releases/`
共享目录。其哈希可进入系统性能报告，但不能成为训练或评测数据版本的父节点。

### `data_pipeline_run.json`

Required keys 与 `data-model.md#17-datapipelinerun` 一致，另必须包含：

- `attempt_id`, `adapter`, `batch_format=pyarrow`, `batch_size`, `block_count`, `block_size_config`
- `ray_compute_strategy`、`task_pool_size`/`actor_pool_size`；本地运行显式为 null
- `head_node_participated_in_compute=false`, `tasks_per_node`, `storage_backend`, `cache_policy`
- `cluster_preflight_ref`；多节点运行必须引用同一集群会话的通过结果
- `input_hashes`, `rule_decision_counts`, `output_id_set_sha256`, `output_logical_content_hash`
- `git_commit`, `dvc_pipeline_revision`, `runtime_image_ref`, `artifact_refs`

Gate: `RAY_MULTI_NODE` 不接受仅由配置声明的节点数，必须由哈希化节点快照和 `tasks_per_node`
证明至少两个独立工作节点实际处理 block。`SUCCEEDED` 要求输入/输出计数、规则决策、Schema、ID 集
和逻辑内容哈希完成核对；物理文件名、分片数和行序不参与逻辑等价。

### `operator_metrics.parquet`

Primary key: `(data_pipeline_run_id, operator_id, metric_name, sample_time)`。Required columns:
`operator_type`, `node_id_hash`, `task_id_hash`, `metric_value`, `metric_unit`, `metric_supported`,
`source=DATASET_STATS|PROMETHEUS|RUNNER`, `source_artifact_sha256`。

至少尝试记录最终算子 rows/bytes output、wall time、CPU time、user-defined-function time、worker heap、
对象存储使用/峰值、spilled bytes、shuffle bytes、in/out queue bytes、backpressure time 和任务状态。
Ray 当前未为某类物理算子暴露指标时，`metric_supported=false` 且 `metric_value=null`，不能填 0。

### `ray_budget_projection.json`

Required keys: `price_quote_refs`, `currency=CNY`, `head_hourly_price_cny_fen`,
`worker_hourly_price_cny_fen`, `storage_price`, `network_price`, `warmup_plan`, `measured_trial_plan`,
`projected_node_hours`, `projected_cost_cny_fen`, `approved_cost_cap_cny_fen`, `approved_at`,
`actual_cost_cny_fen`, `billing_refs`, `projection_sha256`。

Gate: 没有运行前成本上限不得创建正式 64 GiB 多节点作业；实际成本超限时停止后续轮次并保存终态，
不得省略失败轮次后只重跑有利配置。

### `ray_scale_report.json`

Required keys 与 `data-model.md#18-scalebenchmark` 一致，另必须包含：

- `worker_node_counts=[1,2,4]`, `warmup_runs_per_scale=1`, `measured_runs_per_scale=5`
- `cluster_preflight_refs`，分别引用 1/2/4 节点当前集群会话的通过结果
- `raw_trial_ref`, `node_distribution_refs`, `operator_metrics_refs`, `billing_refs`
- 每种规模的 `median_throughput_gib_per_second`, `min`, `max`, `bootstrap_ci95`
- `speedup_vs_one_node`, `parallel_efficiency`, `correctness_equivalence`, `failed_or_retried_runs`
- `claim_decision=MEASURED_SCALE_OUT|NO_SIGNIFICANT_SPEEDUP|REGRESSED|INCOMPLETE`

Gate: `MEASURED_SCALE_OUT` 要求 2/4 节点任务分布为真实多节点、全部输出等价，且相对单节点吞吐提升
的 95% 区间排除零提升。其余结果必须按实际状态保留；“4 个 worker 已启动”不能替代扩展收益。
故障注入只证明被测 worker 进程失败的有限恢复，不得升级为节点级灾备或 exactly-once 声明。

## Execution Preflight Artifact

### `executor_preflight.json`

Required keys:

- `preflight_id`, `host_os`, `kernel_version`, `architecture`
- `docker_version`, `runtime=runsc`, `runtime_version`, `platform=systrap`, `runtime_checksum`
- `image_digest`, `dockerfile_sha256`, `python_version`, `uv_lock_hash`
- `non_root`, `cap_drop_all`, `no_new_privileges`, `network_none`, `read_only_root`
- `input_read_only`, `output_tmpfs_limit_bytes`, `no_host_namespaces`, `no_devices`, `no_docker_socket`
- `cpu_limit`, `memory_limit_bytes`, `pids_limit`, `file_size_limit_bytes`, `wall_time_limit_seconds`
- `network_canary_blocked`, `privilege_canary_blocked`, `host_inspection_ref`
- `passed`, `created_at`, `expires_at`, `artifact_refs`

`passed=true` 要求全部布尔安全条件为 true；调用端不能忽略 `expires_at`。容器内 `dmesg` 或命令输出
不能替代主机侧 runtime inspection。

## Experiment Artifacts

### `model_selection.json`

Required keys:

- `candidate_order`, `selected_model_id`, `selected_revision`, `tokenizer_sha256`, `license_ref`
- `model_type`, `parameter_count`, `text_only`, `training_stage`, `official_model_card_ref`
- `baseline_evaluation_ref`, `memory_calibration_ref`, `checkpoint_reload_ref`
- `rejected_candidates`，每项包含 `model_id`, `reason`, `evidence_ref`
- `selected_before_formal_results=true`, `created_at`, `selection_sha256`

Gate: 第一候选为 `Qwen/Qwen3-8B` 的 Instruct checkpoint；3B–4B 结果不能替代正式模型门禁，带视觉编码器的候选
不能进入纯文本正式矩阵。精确 revision 和兼容性必须由真实下载与 GPU 冒烟确认，规划文本不算通过。

### `training_method_selection.json`

Required keys:

- `model_selection_sha256`, `dataset_hash`, `candidate_order`, `global_batch_size`
- `candidate_runs`，每项包含 `training_method=FULL_PARAMETER|LORA|QLORA`, `config_hash`,
  `run_id`, `actual_topology_ref`, `backward_passed`, `peak_gpu_memory_bytes`, `memory_margin_fraction`,
  `effective_tokens_per_second`, `finite_loss`, `checkpoint_reload_passed`, `projected_six_run_gpu_hours`,
  `projected_six_run_cost_cny`, `new_training_infrastructure_required`, `decision`, `rejection_reasons`
- `selected_training_method`, `selected_config_hash`, `selected_before_formal_results=true`,
  `selection_rule_sha256`, `created_at`, `selection_sha256`

Gate: 任何候选出现反向传播失败、显存余量低于 10%、非有限 loss、检查点不能重载、六次正式运行
挤占 15% 重跑余量或需要项目新增分布式训练平台时必须拒绝。多个候选通过时按预登记顺序选择一种；
该选择应用于全部配方和种子，不能形成训练方法效果矩阵或根据正式结果回选。

### `experiment_plan.yaml`

必须覆盖 `ExperimentPlan` 的全部字段。预登记冻结后，同目录写 `plan_sha256.txt` 和
`preregistration_receipt.json`，后者至少包含 `created_at`, `git_commit`, `dvc_pipeline_revision`,
`plan_sha256`, `budget_projection_sha256`。

额外不变量：

- 每个 comparison（比较）的 treatment 和 control 必须有相同 `planned_loss_tokens_per_run`。
- 同一计划的全部配方和种子必须使用相同 `training_method`、`training_config_ref`、
  `parallelism_mode=SINGLE_GPU` 和 `gpu_count_per_run=1`，并引用通过门禁的
  `training_method_selection.json`。
- 正式计划 seeds 必须精确为 `[17, 29, 43]`，除非计划明确标记 `exploratory=true`。
- 超过 5,000 元时 `approved_budget_cny <= 10000` 且 `budget_exception_ref` 必填。
- 预算例外 `created_before_formal_results=true`，并拒绝 result-sensitive allocation（结果敏感分配）。

### `budget_projection.json`

Required keys:

- `gpu_provider=OpenBayes`, `platform_resource_type`, `price_cny_per_gpu_hour`, `price_quote_ref`,
  `calibration_run_ids`, `model_selection_ref`, `training_method_selection_ref`, `parallelism_mode`,
  `gpu_count_per_run`
- `observed_tokens_per_gpu_hour`, `observed_cost_cny_per_million_tokens`
- `soft_budget_cny=5000`, `max_budget_cny=10000`, `approved_budget_cny`
- `reserve_fraction=0.15`, `available_gpu_count`, `planned_concurrency`, `planned_runs`,
  `planned_gpu_hours`, `planned_cost_cny`
- `feasible_tiers`, `selected_tier`, `assumptions`, `projection_sha256`

价格示例、云厂商列表或理论吞吐不能替代 `price_quote_ref` 和成功冒烟的实测吞吐。

### `training_run.json`

必须包含 `TrainingRun` 全部字段和以下环境指纹：

- `platform=OpenBayes`, `platform_resource_type`, `hostname_hash`, `physical_gpu_id_hash`,
  `gpu_model=NVIDIA GeForce RTX 5090 32GB`, `visible_gpu_count`, `parallelism_mode=SINGLE_GPU`,
  `world_size=1`, `gpu_count=1`, `gpu_topology_ref`, `peak_gpu_memory_bytes`, `training_method`
- `driver_version`, `cuda_version`, `torch_version`, `transformers_version`, `trl_version`,
  `peft_version`, `accelerate_version`
- `runtime_image_ref`, `runtime_image_digest`, `uv_lock_hash`, `git_commit`
- `dataset_id`, `dataset_content_hash`, `experiment_plan_id`, `plan_sha256`

成功运行的 `artifact_index.json` 至少引用训练日志、metrics、最终完整权重或 adapter checkpoint、
训练配置和 RNG state（随机数生成器状态）。失败/中止运行仍保存能取得的日志、实耗卡时、金额和
失败原因。

## Evaluation Artifacts

### `evaluation_run.json`

Required keys: `evaluation_run_id`, `training_run_id` or `base_model_revision`,
`evaluation_suite_version`, `suite_layer=EXTERNAL|PROJECT`, `split`, `generation_config_sha256`, `status`, timestamps,
`item_results_ref`, `raw_predictions_ref`, `summary_metrics_ref`, `executor_preflight_id`,
`cost_cny_fen`。外部层还必须包含 `benchmark_name`, `benchmark_revision`, `official_protocol_ref`,
`runner_image_ref`, `protocol_deviations`；项目层必须包含 `project_extension=true`。

### `evaluation_items.parquet`

Primary key: `(evaluation_run_id, evaluation_item_id)`。必须包含每项 prediction、执行结果、最终产物、
隐藏断言、约束、安全结果、错误类别和执行尝试引用，使 `summary_metrics.json` 可完全重算。

### `summary_metrics.json`

每个指标：

```json
{
  "metric": "ArtifactPass@1",
  "value": 0.0,
  "numerator": 0,
  "denominator": 0,
  "slice_values": [],
  "source_item_results_sha256": "<sha256>"
}
```

项目层至少分别报告 `ArtifactPass@1`, `RepairPass@1`, `HeldOutArtifactPass@1` 和断言诊断项；外部层
保持 LiveCodeBench `pass@1`、DataSciBench 确定性子集分项、BIRD/Spider 2.0-lite execution
accuracy 的官方语义。不同层或不同 benchmark 不得合成一个加权总分。组间比较还必须包含
`mean_delta`, `seed_stddev`, `paired_bootstrap_ci95_low`,
`paired_bootstrap_ci95_high`, `guardrail_deltas`, `decision` 和全部 run IDs。

## Feedback Artifacts

`evaluation_findings.parquet` primary key: `finding_id`；`data_actions.parquet` primary key:
`data_action_id`。每个 action 关联开发集 finding、目标样本/切片、策略版本、新数据集和复验计划。
文件级 metadata 必须含 `source_split=DEVELOPMENT`；出现 `TEST` 时 closed-loop publish 失败。

## Claim and Report Artifacts

### `claims.json`

Top-level keys: `contract_version`, `report_id`, `claims`, `generated_at`, `artifact_index_sha256`。
每项 claim 遵循 `PublishedClaim`。

Claim verifier rules:

| Claim type / level | Required evidence |
|---|---|
| `SOFTWARE_CAPABILITY / SOFTWARE_VALIDATED` | 代码版本、实际测试产物、明确不证明安全执行或模型提升 |
| `DISTRIBUTED_DATA / SOFTWARE_VALIDATED` | 冻结 workload、真实 1/2/4 节点分布、5 次原始轮次、输出等价、算子资源/故障/成本与结论边界 |
| `SAFE_EXECUTION / EXECUTION_VALIDATED` | 通过的 preflight、至少两次一致尝试、原始日志、资源限制和环境指纹 |
| `MODEL_EFFECT / TRAINING_EVIDENCED` | 预登记计划、处理/对照全部种子、等预算、逐项评测、统计判定、护栏、成本和完整谱系 |
| `RESEARCH_METHOD / SOFTWARE_VALIDATED` | 合格的 ResearchSourceEvidence；大模型方法通过宪章时效门禁 |

任何缺失都产生 `required_downgrade`，严格模式退出 8。工具不得自动把措辞改得更强。

### `lineage_index.json`

以 `claim_id` 为入口，列出完整统一谱系键：

```json
{
  "claim_<sha256>": {
    "git_commit": "<40-hex>",
    "uv_lock_hash": "<sha256>",
    "dvc_pipeline_revision": "<sha256>",
    "dataset_ids": ["dataset_<sha256>"],
    "dataset_content_hashes": ["<sha256>"],
    "data_pipeline_run_ids": ["data_run_<sha256>"],
    "scale_benchmark_ids": [],
    "contract_version": "1.0.0",
    "mlflow_run_ids": ["..."],
    "evaluation_suite_version": "...",
    "report_id": "report_<sha256>",
    "artifact_refs": []
  }
}
```

索引还要建立 artifact/dataset/run 到 claim 的反向列表，以支持许可撤销和删除影响分析。

## Deletion Ledger

`deletion_ledger.parquet` 是追加式表。删除正文后保留不含敏感内容的哈希、受影响对象 ID、动作和
证据引用。受影响的数据集、运行和 claim 状态改为 `INVALIDATED`，报告必须展示失效原因；历史
实验记录不能被静默删除。

## Compatibility Policy

- `1.x` reader 必须读取同主版本旧 minor（次版本）产物。
- 添加 nullable（可空）字段提升 minor；改变含义、类型、主键或必需性提升 major（主版本）。
- 每次 schema 变更生成 JSON Schema 和 Arrow Schema 快照，并用 golden fixture（黄金夹具）测试。
- 未知 major 版本必须退出 2，不做 best-effort（尽力猜测）解析。
