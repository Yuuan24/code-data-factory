# Data Model: Code Data Factory

## Modeling Rules

- Pydantic 定义单条记录和清单的运行时契约；PyArrow Schema 定义 Parquet 表。两者使用同一
  `contract_version`，不兼容变化必须提升主版本并提供读取迁移测试。
- 所有标识为小写前缀加不可变摘要，例如 `sample_<sha256>`、`dataset_<sha256>`。展示名可以变化，
  标识不能复用。
- 时间使用带时区的 RFC 3339 UTC 字符串；金额使用整数分，避免浮点误差；哈希使用小写十六进制
  SHA-256。
- 原始内容、明细表、日志和模型产物只存 `ArtifactRef`；业务记录不嵌入大型 blob（二进制大对象）。
- 状态只允许追加事件驱动的迁移。已发布数据集、已冻结实验和终态运行不原地修改；更正产生新版本。

## Shared Enumerations

### EvidenceLevel

| 值 | 含义 |
|---|---|
| `UNVERIFIED` | 没有满足任何验证门槛 |
| `SOFTWARE_VALIDATED` | 只证明代码、契约、静态检查、单元/集成测试或 dry-run 可用 |
| `EXECUTION_VALIDATED` | 不可信代码在通过 preflight 的真实隔离环境中执行并保存证据 |
| `TRAINING_EVIDENCED` | 真实参数更新、公平对照、评测、重复和谱系全部满足 |

证据层级有序但不自动继承。`EXECUTION_VALIDATED` 不意味着训练证据，训练运行存在也不意味着
任意结论达到 `TRAINING_EVIDENCED`。

### GovernanceStatus

`PENDING | ACCEPTED | QUARANTINED | REJECTED | DELETED`

### VerificationOutcome

`PASS | FAIL | POLICY_BLOCKED | TIMEOUT | OOM | SIGNALLED | FLAKY | INFRA_ERROR`

`OOM` 表示 out of memory（内存耗尽）。`POLICY_BLOCKED` 与 `INFRA_ERROR` 不等于样本逻辑失败。

### VerificationStatus

`UNVERIFIED | STATIC_PASS | STATIC_FAIL | EXECUTION_PASS | EXECUTION_FAIL | FLAKY | BLOCKED`

### TestStrength

`NONE | EXECUTION_ONLY | COVERAGE_RECORDED | NEGATIVE_CONTROL_REJECTED`

### RunStatus

`PLANNED | RUNNING | SUCCEEDED | FAILED | ABORTED | BUDGET_BLOCKED | INVALIDATED`

### FindingOutcome

`IMPROVED | UNCHANGED | REGRESSED | INCONCLUSIVE | NOT_RUN`

### DataUsageScope

`TRAINING_CANDIDATE | EVALUATION | BENCHMARK_ONLY`

`BENCHMARK_ONLY` 表示只用于系统性能/故障实验；不能成为任何训练、开发或测试 membership。

## Core Entities

### 1. ResearchSourceEvidence

记录用于当前大模型方法结论或通用组件选型的外部依据。

| Field | Type | Required | Rules |
|---|---|---:|---|
| `research_source_id` | string | yes | 稳定标识 |
| `source_kind` | enum | yes | `LARGE_MODEL_METHOD | COMPONENT` |
| `query` | string | yes | 实际检索条件 |
| `title` | string | yes | 原始资料标题 |
| `publisher` | string | yes | 发布主体 |
| `url` | string | yes | 原始资料链接，不是搜索结果页 |
| `published_or_updated_on` | date | yes | 可验证的发布日期或最后实质更新日 |
| `accessed_on` | date | yes | 实际访问日期 |
| `version` | string/null | yes | 无版本时显式为 null 并说明 |
| `supports` | list[string] | yes | 支持的具体方案或结论标识 |
| `superseded_check` | string | yes | 检查位置和结果 |
| `content_sha256` | string | yes | 保存快照的内容哈希 |

Validation: `source_kind=LARGE_MODEL_METHOD` 时必须通过宪章时效门禁；组件来源不应用该日期门槛，
但必须有当前维护、许可、兼容性和安全审查记录。

### 2. SourceSnapshot

| Field | Type | Required | Rules |
|---|---|---:|---|
| `source_snapshot_id` | string | yes | 内容寻址 |
| `source_type` | enum | yes | `GIT | LOCAL_FIXTURE | GENERATED_TASKS` |
| `uri` | string | yes | 可重建位置；公开报告可脱敏凭据部分 |
| `revision` | string | yes | Git 来源必须是完整 40 位提交 SHA |
| `license_id` | string | yes | SPDX 标识或 `REVIEW_REQUIRED` |
| `license_evidence_ref` | ArtifactRef | yes | 许可原文/快照 |
| `acquired_at` | datetime | yes | UTC |
| `file_count` | int | yes | 非负 |
| `line_count` | int | yes | 非负且总计不超过计划上限 |
| `manifest_ref` | ArtifactRef | yes | 文件路径、大小和 SHA-256 |
| `governance_status` | GovernanceStatus | yes | 只有 `ACCEPTED` 可进入候选构建 |

Relationships: 一个来源快照产生多个 `DataSample`；删除或许可撤销通过 `DeletionLedgerEntry` 反向
定位所有后代。

### 3. DataSample

| Field | Type | Required | Rules |
|---|---|---:|---|
| `sample_id` | string | yes | 基于规范内容与生成身份稳定生成 |
| `language` | string | yes | 首版固定 `python` |
| `sample_kind` | enum | yes | `RAW_CODE | SFT_EXAMPLE | TASK_PACKAGE | TEST | MUTANT | BENCHMARK_REPLICA` |
| `usage_scope` | DataUsageScope | yes | 训练、评测或仅基准测试用途；失败关闭 |
| `content_ref` | ArtifactRef | yes | 内容和 SHA-256 |
| `source_snapshot_ids` | list[string] | yes | 至少一个来源或合成任务来源 |
| `parent_sample_ids` | list[string] | yes | 可为空；合成/修复样本必须非空 |
| `is_synthetic` | bool | yes | 只描述来源，不代表质量 |
| `generator_id` | string/null | yes | 合成时必填模型/模板版本 |
| `prompt_template_id` | string/null | yes | 合成时必填 |
| `slice_ids` | list[string] | yes | 多标签 |
| `raw_sha256` | string | yes | 原始内容哈希 |
| `ast_sha256` | string/null | yes | 可解析时必填 |
| `token_count` | int | yes | 对冻结 tokenizer 计算 |
| `governance_status` | GovernanceStatus | yes | 与验证状态独立 |
| `verification_status` | VerificationStatus | yes | 汇总状态 |
| `test_strength` | TestStrength | yes | 与执行结果独立 |
| `created_at` | datetime | yes | UTC |

Validation: `governance_status != ACCEPTED` 的样本不能进入训练 membership；`EXECUTION_PASS` 必须
存在至少两条一致的 `VerificationAttempt`，且执行环境通过 preflight。生成测试未拒绝负对照时，
`test_strength` 不能是 `NEGATIVE_CONTROL_REJECTED`。`sample_kind=BENCHMARK_REPLICA` 必须同时满足
`usage_scope=BENCHMARK_ONLY`，发布和训练入口必须拒绝该用途。

### 4. TransformationRecord

追加式记录每个数据动作。

| Field | Type | Required | Rules |
|---|---|---:|---|
| `transformation_id` | string | yes | 唯一 |
| `operation` | enum | yes | `GENERATE | PARSE | FILTER | DEDUP | REPAIR | REGENERATE | SELECT | DOWNWEIGHT | DELETE | REVIEW` |
| `input_sample_ids` | list[string] | yes | 至少一个，初始生成可引用任务样本 |
| `output_sample_ids` | list[string] | yes | 拒绝/删除时可为空 |
| `reason_code` | string | yes | 版本化受控词表 |
| `evidence_refs` | list[ArtifactRef] | yes | 可为空但必须记录原因 |
| `actor` | string | yes | 命令、规则、人或模型身份 |
| `config_sha256` | string | yes | 冻结配置 |
| `started_at` | datetime | yes | UTC |
| `finished_at` | datetime | yes | 不早于开始时间 |

Relationships: 构成 `DataSample` 的有向无环谱系；出现循环时发布失败。

### 5. QualityAssessment

| Field | Type | Required | Rules |
|---|---|---:|---|
| `assessment_id` | string | yes | 唯一 |
| `sample_id` | string | yes | 外键 |
| `dimension` | string | yes | 如 parse、lint、secret、PII、testability、difficulty |
| `method_id` | string | yes | 规则/模型/人工方法及版本 |
| `raw_value` | scalar/json | yes | 原始输出，不只存通过/失败 |
| `threshold` | scalar/json/null | yes | 运行前门槛 |
| `decision` | enum | yes | `PASS | FAIL | REVIEW | NOT_APPLICABLE` |
| `evidence_ref` | ArtifactRef | yes | 原始结果 |
| `assessed_at` | datetime | yes | UTC |

Validation: 不存在跨全部维度的唯一 `quality_score` 字段；接受决策必须可追到各维度结果。

### 6. DedupCluster and ContaminationEdge

`DedupCluster` fields:

- `cluster_id`, `method_version`, `member_sample_ids`, `representative_sample_id`
- `candidate_method`: `EXACT | AST_EXACT | MINHASH`
- `exact_metric`: `IDENTICAL | JACCARD | CONTAINMENT`
- `threshold`, `pair_evidence_ref`, `assigned_split`

`ContaminationEdge` fields:

- `edge_id`, `train_sample_id`, `evaluation_item_id`, `method`, `score`, `threshold`
- `decision`: `BLOCK | REVIEW | CLEAR`
- `evidence_ref`, `checked_at`

Validation: MinHash 命中必须有精确指标复核；一个 cluster 的成员不能分配到不同 split；`BLOCK`
边涉及的样本不能进入训练，对应评测指标在清理前标记 invalidated（失效）。

### 7. VerificationAttempt

| Field | Type | Required | Rules |
|---|---|---:|---|
| `attempt_id` | string | yes | 样本、环境、序号决定 |
| `sample_id` | string | yes | 外键 |
| `attempt_index` | int | yes | 从 1 开始 |
| `runtime` | string | yes | `runsc` 或实际 runtime |
| `runtime_version` | string | yes | 固定版本 |
| `platform` | string | yes | 目标 `systrap` |
| `preflight_id` | string | yes | 关联通过的 host-side preflight |
| `image_digest` | string | yes | 禁止 tag-only |
| `command_digest` | string | yes | 实际入口摘要 |
| `network_mode` | string | yes | 必须 `none` 才能晋级 |
| `limits` | json | yes | CPU、内存、PID、文件、输出和墙钟上限 |
| `outcome` | VerificationOutcome | yes | 终态 |
| `exit_code` | int/null | yes | 未启动可为空 |
| `duration_ms` | int | yes | 非负 |
| `resource_usage` | json | yes | 实测或明确 unsupported |
| `stdout_ref` | ArtifactRef | yes | 截断策略和原始哈希 |
| `stderr_ref` | ArtifactRef | yes | 同上 |
| `output_ref` | ArtifactRef/null | yes | 产生结果时必填 |
| `coverage_ref` | ArtifactRef/null | yes | 可选覆盖证据 |
| `negative_control_ref` | ArtifactRef/null | yes | 生成测试晋级时必填 |

State rule: 两次均为 `PASS` 且关键输出哈希一致才汇总为 `EXECUTION_PASS`；不一致为 `FLAKY`；
preflight 未通过产生 `POLICY_BLOCKED`，不能静默改用 `runc`。

### 8. DataSlice

| Field | Type | Required | Rules |
|---|---|---:|---|
| `slice_id` | string | yes | 稳定标识 |
| `dimension` | string | yes | 技能、来源、难度、长度、生成器、测试强度等 |
| `predicate` | string | yes | 受控 DSL（领域专用语言），不可接受任意 SQL |
| `version` | string | yes | 谓词版本 |
| `description` | string | yes | 人可读含义 |

### 9. DatasetVersion and DatasetMembership

`DatasetVersion` fields:

- `dataset_id`, `name`, `recipe`: `CLEAN | VERIFIED | SFT_RANDOM_MATCHED | SFT_CLOSED_LOOP |
  RL_READY_EXPORT`
- `parent_dataset_ids`, `source_snapshot_ids`, `contract_version`
- `tokenizer_id`, `sample_count`, `unique_sample_count`, `effective_token_supply`
- `manifest_ref`, `membership_ref`, `data_card_ref`, `quality_report_ref`, `diversity_report_ref`
- `dvc_pipeline_revision`, `git_commit`, `uv_lock_hash`, `content_hash`
- `status`: `DRAFT | FROZEN | PUBLISHED | INVALIDATED`
- `created_at`, `frozen_at`, `invalidation_reason`

`DatasetMembership` fields:

- `dataset_id`, `sample_id`, `split`: `TRAIN | DEVELOPMENT | TEST`
- `weight`, `exposure_count`, `selection_rank`, `selection_reason`
- `dedup_cluster_id`, `membership_sha256`

Validation: `PUBLISHED` 后不可改；训练 membership 只允许治理通过的样本；测试 split 在反馈选择期间
不可读；`SFT_RANDOM_MATCHED` 和 `SFT_CLOSED_LOOP` 的候选池及匹配字段哈希必须一致。

### 9a. TaskPackage, CandidateGeneration, and RewardRecord

`TaskPackage` fields:

- `task_package_id`, `task_type`: `DATA_TRANSFORM | QUALITY_REPAIR | PIPELINE_DEBUG`
- `instruction_ref`, `input_dataset_ref`, `target_schema_ref`, `hidden_assertions_ref`
- `allowed_tool_schema_ref`, `environment_image_ref`, `verifier_version`, `mutation_evidence_ref`
- `source_repository_id_hash`, `difficulty`, `initial_policy_success_rate`, `slice_ids`
- `usage_scope`, `content_hash`, `status`: `DRAFT | VERIFIED | FROZEN | INVALIDATED`

`CandidateGeneration` fields:

- `candidate_generation_id`, `task_package_id`, `generator_model_id`, `generator_revision`
- `sampling_config_sha256`, `seed`, `answer_ref`, `prompt_tokens`, `completion_tokens`
- `final_artifact_ref`, `verification_attempt_ids`, `reward_record_id`, `failure_reason`
- `status`: `GENERATED | VERIFIED | REJECTED | REPLAY_MISMATCH`

`RewardRecord` fields:

- `reward_record_id`, `candidate_generation_id`, `reward_policy_version`, `verifier_version`
- `artifact_correctness`, `hidden_assertion_pass`, `constraint_compliance`
- `tool_validity_component`, `efficiency_component`, `safety_component`, `total_reward`
- `raw_evidence_refs`, `replay_reward`, `is_flaky`, `computed_at`

Validation: `total_reward > 0` 必须同时满足最终数据产物正确、全部隐藏断言通过和任务约束通过；
静态代码质量或效率不能覆盖硬门禁失败。正式 SFT 只接受 `TaskPackage.status=FROZEN` 且
`CandidateGeneration.status=VERIFIED` 的答案。重放奖励不一致时标记 `REPLAY_MISMATCH`，不得发布
`RL_READY_EXPORT`；RewardRecord 只证明兼容数据存在，不证明真实 RL 训练发生。

### 10. ExperimentPlan

| Field | Type | Required | Rules |
|---|---|---:|---|
| `experiment_plan_id` | string | yes | 内容寻址 |
| `title` | string | yes | 人可读 |
| `training_mode` | enum | yes | 首版固定 `SFT` |
| `hypothesis` | string | yes | 运行前声明 |
| `treatment_recipe` | string | yes | 数据配方 |
| `control_recipe` | string | yes | 公平对照 |
| `target_difference` | string | yes | 唯一目标差异 |
| `matching_fields` | list[string] | yes | 预处理变量 |
| `model_selection_ref` | ArtifactRef | yes | 候选门禁、淘汰理由和冻结结果 |
| `base_model_id` | string | yes | 精确模型标识 |
| `base_model_revision` | string | yes | 固定 revision |
| `tokenizer_sha256` | string | yes | 固定 tokenizer |
| `chat_template_sha256` | string | yes | 固定对话与工具调用模板 |
| `training_method` | enum | yes | `FULL_PARAMETER | LORA | QLORA`；正式计划只允许一种 |
| `training_method_selection_ref` | ArtifactRef | yes | 事前可行性门禁及被拒候选理由 |
| `training_config_ref` | ArtifactRef | yes | 所选方法、参数更新范围、精度、优化器和学习率等 |
| `planned_loss_tokens_per_run` | int | yes | 每组每种子相同 |
| `verifier_version` | string | yes | 两组相同且已冻结 |
| `seeds` | list[int] | yes | 正式计划 `[17,29,43]` |
| `evaluation_suite_version` | string | yes | 固定版本 |
| `primary_metrics` | list[string] | yes | 至少一个 |
| `secondary_metrics` | list[string] | yes | 可为空 |
| `guardrails` | json | yes | 通用/安全回退阈值 |
| `decision_rule` | string | yes | 含置信区间和多种子条件 |
| `gpu_provider` | string | yes | 当前计划固定 `OpenBayes` |
| `platform_resource_type` | string | yes | 平台实际显示的资源标识；不得推断未公开规格 |
| `gpu_model` | string | yes | 当前计划固定 `NVIDIA GeForce RTX 5090 32GB` |
| `parallelism_mode` | enum | yes | 首版固定 `SINGLE_GPU` |
| `gpu_count_per_run` | int | yes | 首版固定 1 |
| `method_calibration_ref` | ArtifactRef | yes | 单卡训练方法选择、显存、稳定性、重载与成本证据 |
| `price_cny_per_gpu_hour` | decimal string | yes | 报价，不用 float |
| `soft_budget_cny` | int | yes | 默认 `5000` |
| `approved_budget_cny` | int | yes | `5000..10000` |
| `budget_exception_ref` | ArtifactRef/null | yes | 超过 5000 时必填 |
| `reserved_fraction` | decimal string | yes | 默认 `0.15` |
| `status` | enum | yes | `DRAFT | PREREGISTERED | RUNNING | CLOSED | INVALIDATED` |
| `preregistered_at` | datetime/null | yes | `PREREGISTERED` 时必填 |
| `plan_sha256` | string | yes | 冻结内容哈希 |

State transition: `DRAFT -> PREREGISTERED -> RUNNING -> CLOSED`；任何影响假设、组别、词元、种子、
指标或判定规则的变更必须创建新计划，不能修改已预登记记录。

### 11. TrainingRun

| Field | Type | Required | Rules |
|---|---|---:|---|
| `training_run_id` | string | yes | 与 MLflow run 关联 |
| `experiment_plan_id` | string | yes | 外键 |
| `recipe` | string | yes | 必须属于计划 |
| `dataset_id` | string | yes | 冻结数据集 |
| `seed` | int | yes | 必须属于计划 |
| `base_model_revision` | string | yes | 必须与计划相同 |
| `mlflow_run_id` | string | yes | 运行索引 |
| `platform` | string | yes | 当前固定 `OpenBayes` |
| `platform_resource_type` | string | yes | 平台实际显示的资源标识 |
| `gpu_model` | string | yes | 固定 `NVIDIA GeForce RTX 5090 32GB` |
| `visible_gpu_count` | int | yes | 当前容器实测可见卡数；并发实例不可相加冒充同节点卡数 |
| `parallelism_mode` | enum | yes | 必须与计划相同 |
| `gpu_count` | int | yes | 首版固定 1 |
| `physical_gpu_id_hash` | string | yes | 用于轮换审计，不公开序列号 |
| `gpu_topology_ref` | ArtifactRef/null | yes | 首版为空；记录单卡身份即可 |
| `driver_version` | string | yes | 实际值 |
| `cuda_version` | string | yes | 实际值 |
| `runtime_image_ref` | string | yes | OpenBayes 可见运行时镜像标识 |
| `runtime_image_digest` | string/null | yes | 平台暴露时记录；否则为空并声明限制 |
| `planned_loss_tokens` | int | yes | 来自计划 |
| `observed_loss_tokens` | int | yes | 不含 padding 的实测值 |
| `optimizer_steps` | int | yes | 实测 |
| `status` | RunStatus | yes | 终态也保留 |
| `started_at`, `finished_at` | datetime | yes | UTC |
| `gpu_seconds` | decimal string | yes | 实测 |
| `peak_gpu_memory_bytes` | int | yes | 峰值显存，用于兼容性和余量门禁 |
| `cost_cny_fen` | int | yes | 实付分 |
| `training_method` | enum | yes | 必须与计划冻结的方法相同 |
| `log_ref`, `checkpoint_ref`, `metrics_ref` | ArtifactRef | conditional | `SUCCEEDED` 必填；checkpoint 可为完整权重或 adapter；失败至少有 log |
| `failure_reason` | string/null | yes | 非成功终态必填 |

Validation: `SUCCEEDED` 且用于正式对比时必须 `planned_loss_tokens == observed_loss_tokens`；同一计划
的配方/种子组合唯一；全部运行必须使用相同单卡拓扑、训练设置和验证器版本。失败运行不可删除或
复用其 ID。

### 12. EvaluationRun and EvaluationItem

`EvaluationRun` fields:

- `evaluation_run_id`, `training_run_id` 或 `base_model_revision`
- `evaluation_suite_version`, `suite_layer`: `EXTERNAL | PROJECT`, `split`, `generation_config_sha256`
- `benchmark_name`, `benchmark_revision`, `official_protocol_ref`, `runner_image_ref`,
  `protocol_deviations`；项目层的前三项可为空但必须声明 `project_extension=true`
- `executor_preflight_id`, `status`, `started_at`, `finished_at`
- `item_results_ref`, `summary_metrics_ref`, `raw_predictions_ref`, `cost_cny_fen`

`EvaluationItem` fields:

- `evaluation_run_id`, `evaluation_item_id`, `repository_id_hash`, `input_dataset_id_hash`, `task_template_id`
- `capability_tags`, `task_package_ref`, `prediction_ref`, `final_artifact_ref`
- `execution_pass`, `artifact_correct`, `hidden_assertions_pass`, `constraints_pass`, `artifact_pass`
- `repair_pass`, `security_pass`, `completion_tokens`, `duration_ms`, `cost_cny_fen`
- `verification_attempt_ids`, `error_category`

Validation: 正式 test 结果只有在 `SFT_CLOSED_LOOP` 冻结后才能产生；项目层
`artifact_pass=true` 要求执行、最终产物、隐藏断言、约束和安全限制全部为真；外部层必须保留官方
指标语义和所有协议偏离。汇总指标必须可由逐项记录重算，外部与项目层不得合成一个总分。

### 13. EvaluationFinding and DataAction

`EvaluationFinding` fields:

- `finding_id`, `evaluation_run_ids`, `capability`, `error_pattern`, `slice_ids`
- `evidence_item_ids`, `severity`, `confidence`, `status`: `OPEN | ACTIONED | RETESTED | CLOSED`
- `created_at`

`DataAction` fields:

- `data_action_id`, `finding_id`, `action`: `ADD | REPAIR | REGENERATE | RESELECT | DOWNWEIGHT |
  DELETE | MANUAL_REVIEW`
- `target_sample_ids` 或 `target_slice_ids`, `reason`, `policy_version`
- `output_dataset_id`, `retest_plan_id`, `outcome`: FindingOutcome

Validation: `SFT_CLOSED_LOOP` membership 的每个非随机变更必须关联 `DataAction`；action 只能读取开发集
finding，不能读取最终测试结果。

### 14. PublishedClaim

| Field | Type | Required | Rules |
|---|---|---:|---|
| `claim_id` | string | yes | 稳定标识 |
| `statement` | string | yes | 精确、可证伪 |
| `claim_type` | enum | yes | `SOFTWARE_CAPABILITY \| DISTRIBUTED_DATA \| SAFE_EXECUTION \| MODEL_EFFECT \| RESEARCH_METHOD` |
| `evidence_level` | EvidenceLevel | yes | 显式层级 |
| `supporting_artifact_refs` | list[ArtifactRef] | yes | 非空 |
| `experiment_plan_ids` | list[string] | yes | 模型效果时非空 |
| `training_run_ids` | list[string] | yes | 训练证据时覆盖处理/对照/全部种子 |
| `evaluation_run_ids` | list[string] | yes | 同上 |
| `research_source_ids` | list[string] | yes | 当前方法结论时非空 |
| `data_pipeline_run_ids` | list[string] | yes | 分布式数据结论时覆盖 1/2/4 节点全部正式轮次 |
| `scale_benchmark_ids` | list[string] | yes | 分布式数据结论时非空 |
| `limitations` | list[string] | yes | 非空 |
| `contrary_evidence_refs` | list[ArtifactRef] | yes | 没有时也保存空列表 |
| `reproduction_command` | string | yes | 单一入口 |
| `report_id` | string | yes | 发布报告 |
| `created_at` | datetime | yes | UTC |

Training claim gate: `claim_type=MODEL_EFFECT` 且 `evidence_level=TRAINING_EVIDENCED` 时，必须有真实
处理/对照运行、计划三个种子、等预算、正向均值、95% 置信区间下界大于 0、护栏未超阈值、逐项
评测和完整谱系。任何条件不满足时只能使用更低层级或 `INCONCLUSIVE` 表述。

Distributed claim gate: `claim_type=DISTRIBUTED_DATA` 时证据层级保持 `SOFTWARE_VALIDATED`，并必须有
真实 1/2/4 节点任务分布、全部 5 次轮次、等价输出、资源/故障/成本和结论边界。它不能自动升级为
安全执行或模型效果证据。

### 15. ArtifactRef

| Field | Type | Required | Rules |
|---|---|---:|---|
| `artifact_id` | string | yes | 稳定标识 |
| `uri` | string | yes | 项目相对路径、DVC URI 或 MLflow artifact URI |
| `media_type` | string | yes | 标准媒体类型 |
| `byte_size` | int | yes | 非负 |
| `sha256` | string | yes | blob 哈希 |
| `logical_content_hash` | string/null | yes | Parquet/多文件产物可填 |
| `created_by_run_id` | string/null | yes | 可回溯生产运行 |

### 16. DeletionLedgerEntry

| Field | Type | Required | Rules |
|---|---|---:|---|
| `deletion_id` | string | yes | 唯一 |
| `trigger` | enum | yes | `LICENSE_REVOKED | SOURCE_DELETED | PII | SECRET | CORRECTION | OWNER_REQUEST` |
| `source_snapshot_ids` | list[string] | yes | 可为空但样本必须非空 |
| `sample_ids` | list[string] | yes | 受影响样本 |
| `affected_dataset_ids` | list[string] | yes | 由谱系计算 |
| `affected_run_ids` | list[string] | yes | 由谱系计算 |
| `affected_claim_ids` | list[string] | yes | 由谱系计算 |
| `action` | enum | yes | `QUARANTINE | INVALIDATE | DELETE_DISTRIBUTION_COPY` |
| `evidence_ref` | ArtifactRef | yes | 请求或发现证据 |
| `recorded_at` | datetime | yes | UTC |

Validation: 历史运行记录不被静默抹除；改为 `INVALIDATED` 并从可分发数据中删除受影响内容，同时
保留不含敏感正文的审计索引。

### 17. DataPipelineRun

记录一次本地或 Ray Data 流水线执行；它证明实际执行与资源行为，不自动证明安全执行或模型收益。

| Field | Type | Required | Rules |
|---|---|---:|---|
| `data_pipeline_run_id` | string | yes | 内容寻址的稳定运行标识；attempt 另有编号 |
| `execution_mode` | enum | yes | `LOCAL \| RAY_SINGLE_NODE \| RAY_MULTI_NODE` |
| `workload_kind` | enum | yes | `REAL_DATASET_BUILD \| BENCHMARK_ONLY` |
| `ray_job_id` | string/null | yes | Ray Jobs 提交时必填；本地可空 |
| `python_version` | string | yes | 实际版本 |
| `ray_version` | string/null | yes | Ray 模式必填，规划基线 2.58.0 |
| `ray_commit` | string/null | yes | 运行时可取得时必填，否则记录限制 |
| `uv_lock_hash` | string | yes | 所有节点一致 |
| `input_manifest_ref` | ArtifactRef | yes | 冻结文件、记录数、物理/逻辑字节和哈希 |
| `operator_graph_sha256` | string | yes | 顺序、算子版本、资源和 batch/block 配置 |
| `physical_worker_node_count` | int | yes | 不含 head；本地为 1 |
| `ray_worker_process_count` | int/null | yes | Ray 模式实测，不用它冒充节点数 |
| `cluster_topology_ref` | ArtifactRef/null | yes | 多节点时必填，含哈希化节点 ID 与每节点资源 |
| `cluster_preflight_ref` | ArtifactRef/null | yes | 多节点时必填，含私网端口、版本、资源和共享存储探针 |
| `resource_config` | json | yes | CPU、内存、对象存储、spill 目录与并发限制 |
| `input_record_count` | int | yes | 非负 |
| `input_physical_bytes` | int | yes | 规范输入对象的实际字节 |
| `input_logical_payload_bytes` | int | yes | 解压后参与业务算子的 payload 字节 |
| `output_record_count` | int | yes | 与规则计数对账 |
| `output_schema_sha256` | string | yes | 跨执行模式一致 |
| `output_logical_content_hash` | string | yes | 按稳定主键排序；不依赖文件名/分片/行序 |
| `operator_metrics_ref` | ArtifactRef | yes | 算子级吞吐、CPU、heap、队列、spill、shuffle、backpressure |
| `dataset_stats_ref` | ArtifactRef/null | yes | Ray 模式保存原始 `Dataset.stats()` |
| `retry_and_failure_ref` | ArtifactRef | yes | 重试、恢复、最终失败和故障注入记录 |
| `wall_time_ms` | int | yes | 包含最终写出完成，非负 |
| `cost_cny_fen` | int | yes | 实付；免费资源填 0 但保留价格来源 |
| `status` | RunStatus | yes | 所有终态保留 |
| `evidence_level` | EvidenceLevel | yes | 单机最多软件级；多节点也不自动晋级模型证据 |
| `started_at`/`finished_at` | datetime | yes | UTC，结束不早于开始 |

Validation: `execution_mode=RAY_MULTI_NODE` 要求 `physical_worker_node_count >= 2`、通过的集群探针、
任务节点分布证据和共享存储证据。指标采集不受支持时对应值为 null 并带
`metric_supported=false`，不能填 0。
`status=SUCCEEDED` 仍须保留已恢复失败。只有所有 output 门禁通过后才能提交 dataset manifest。

### 18. ScaleBenchmark

| Field | Type | Required | Rules |
|---|---|---:|---|
| `scale_benchmark_id` | string | yes | 冻结配置内容寻址 |
| `benchmark_dataset_ref` | ArtifactRef | yes | 全部记录必须 `BENCHMARK_ONLY` |
| `target_logical_payload_bytes` | int | yes | 首版固定至少 64 gibibyte（吉比字节，GiB；`2^30` 字节） |
| `operator_graph_sha256` | string | yes | 所有规模一致 |
| `worker_node_counts` | list[int] | yes | 精确为 `[1, 2, 4]` |
| `measured_repeats_per_scale` | int | yes | 精确为 5；预热不计入 |
| `run_order` | list[int] | yes | 运行前随机化并冻结 |
| `run_ids_by_scale` | map[int,list[string]] | yes | 每个规模 5 个成功/失败终态都保留 |
| `cluster_preflight_refs` | map[int,ArtifactRef] | yes | 1/2/4 节点当前集群会话的通过结果 |
| `throughput_summary` | json | yes | 各规模中位数、范围和 95% bootstrap 区间 |
| `speedup_and_efficiency` | json | yes | 相对单节点，含原始公式输入 |
| `correctness_equivalence` | bool | yes | Schema、ID 集、规则计数、逻辑哈希全部一致 |
| `fault_injection_run_id` | string | yes | worker 进程终止测试 |
| `bottleneck_analysis_ref` | ArtifactRef | yes | 包含无加速/负加速解释，不能只留最佳轮次 |
| `approved_cost_cap_cny_fen` | int | yes | 首次运行前批准 |
| `actual_cost_cny_fen` | int | yes | 账单回填 |
| `claim_scope` | string | yes | 只描述被测版本、数据、算子、节点和存储 |

Validation: 任一规模缺少通过的当前集群探针、5 个终态、实际节点分布证据或输出等价性失败时，
不能发布 Ray 多节点扩展收益；可以发布失败/瓶颈报告。单节点多进程 run 不能填入 2/4 节点位置。

## Relationship Overview

```text
ResearchSourceEvidence ───────────────┐
                                     ▼
SourceSnapshot → DataSample → TaskPackage → DatasetVersion → TrainingRun → EvaluationRun
      │              │            │              │            │              │
      │              ├→ VerificationAttempt     │            ├→ CandidateGeneration→ RewardRecord
      │              ├→ QualityAssessment       │            │              ├→ EvaluationFinding
      │              └→ DedupCluster            │            │              │          │
      │                                         │            │              │          ▼
      └→ TransformationRecord ───────────────────┘            │              │      DataAction
                                                              └──────────────┘          │
ExperimentPlan ───────────────────────────────→ TrainingRun                         next DatasetVersion

all entities → ArtifactRef; all evidence-bearing entities → PublishedClaim
SourceSnapshot/DataSample → DeletionLedgerEntry → affected datasets/runs/claims
SourceSnapshot/DataSample → DataPipelineRun → DatasetVersion
DataPipelineRun[1,2,4 nodes] → ScaleBenchmark → PublishedClaim
```

## Invariants Required for Publication

1. 100% 数据集 membership 可回溯到来源和 transformation chain（转换链）。
2. 数据集清单计数、Parquet 行数和内容哈希一致。
3. 同一重复簇不跨训练、开发和测试切分。
4. `EXECUTION_PASS` 不存在缺失 preflight、单次执行或弱测试强度的静默晋级。
5. 正式实验每个配方/种子都有终态记录；失败、负向和无变化记录保留。
6. 同一 SFT 比较的计划/实测有效训练词元一致，其他冻结预算相同，预算例外在正式结果产生前冻结。
7. 每个报告指标可由逐项 Parquet 重新计算，每个 claim 可反向解析全部 ArtifactRef。
8. `BENCHMARK_ONLY` 记录进入任何训练、开发、测试 membership 的数量为零。
9. 相同冻结输入与业务算子的本地/Ray 运行具有相同 Schema、样本决策和逻辑内容哈希；Ray 物理
   分片、文件名或行序不能成为语义差异。
10. Ray 多节点成果必须关联实际节点拓扑、任务分布、5 次原始轮次、失败恢复、资源和成本证据。
