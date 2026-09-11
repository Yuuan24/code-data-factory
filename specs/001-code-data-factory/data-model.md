# Data Model: Agent 任务与交互轨迹

**Contract version**: 2.1.0 | **Date**: 2026-09-11 | **Status**: 2.1 外部训练示范契约；运行时模式待 T105 实现。
取代 1.x 单次代码样本语义；2.0 产物不能重贴 2.1 标签，迁移必须新建标识和来源映射。
字段使用 snake_case（下划线命名）；所有 `*_ref` 指向带内容哈希的 ArtifactRef（产物引用）。

## Shared Types and Rules

- 标识为稳定字符串；运行标识每次调用唯一，内容标识由规范化内容计算；不能以内容哈希合并两次实际尝试。
- 时间使用协调世界时（UTC）；金额为人民币分整数；未知数值为 null，不能填 0。
- EvidenceLevel（证据层级）：`UNVERIFIED`、`SOFTWARE_VALIDATED`、`EXECUTION_VALIDATED`、
  `TRAINING_EVIDENCED`，分别为未验证、软件验证、隔离执行验证和训练证据。
- UsageScope（用途）：`TRAIN`、`DEVELOPMENT`、`TEST`、`HISTORICAL_ONLY`、`BENCHMARK_ONLY`；
  后两者分别仅历史观察和仅性能测试，不能进入正式训练/评测成员。`TRAIN` 只表示通过版本化
  训练准入的外部示范用途，不表示已可重放、已验证 PASS 或可作在线采样消费。
- `contract_version` 必填；未知主版本拒绝消费，新增可选字段允许兼容读取，语义变化必须升主版本。
- ArtifactRef：`artifact_id, uri, sha256, byte_size, media_type, producer_run_id, access_scope`；
  `uri` 是项目相对路径或内容存储地址，禁止凭据和本机绝对路径。模型可见和验证器私有产物分开。

## 2.1 External Demonstration Migration

正式训练成员是 `ExternalDemonstration`，不是本项目的 `TaskPackage`、固定动作 attempt、评测输出或
模型重新采样输出。字段为：`demonstration_id, source_record_id, upstream_task_ref, upstream_tool_bundle_ref,
message_refs, call_result_refs, answer_ref, upstream_synthetic_status, parent_demonstration_id,
repair_rule_ref, eligibility_decision_ref, replay_capability, result_evidence_ref, reward_evidence_ref,
usage_scope, contract_version`。

- `eligibility_decision_ref` 指向版本化训练准入决定，独立记录接受、拒绝或待复核及理由；不以
  `outcome=PASS` 替代。
- `replay_capability` 为 `SUPPORTED | UNSUPPORTED | UNKNOWN`，缺环境或初始状态时保持非支持/未知，
  不影响已有充分质量证据的 SFT 准入。
- `result_evidence_ref` 与 `reward_evidence_ref` 可为空；来源自报成功不能写为本项目 PASS 或奖励 1。
- 仅确定性格式/唯一调用关联修复可产生新 `ExternalDemonstration`，必须关联父记录和修复规则；
  不补写缺失工具返回、模型推理或答案。

## 1. SourceSnapshot and SourceRecord

快照字段：`source_snapshot_id, source_uri, upstream_revision, captured_at, license_ref, usage_scope,
manifest_ref, content_hash, source_kind, status`。
记录字段：`source_record_id, source_snapshot_id, raw_ref, upstream_id, origin_kind, parent_source_record_ids`。
`origin_kind` 为公开原始、项目合成或派生；来源撤销标记失效，保留不含敏感内容的影响索引。
历史序列的先后顺序能唯一恢复调用对应时可产生规范字段，但须标记 `association_origin=inferred_unique`；
歧义记录隔离，禁止执行源文本中的表达式来解析记录。

## 2. TaskPackage and TaskGroup

| 字段 | 规则 |
|---|---|
| `task_id, task_revision, source_record_ids` | 任务独立于示范；同任务多次尝试不能生成新 task_id |
| `instruction_ref, initial_resources_ref, tool_bundle_ref` | 输入与初始资源完整；工具 bundle 含名称/参数模式/版本 |
| `environment_ref, verifier_spec_ref, expected_result_ref` | 后两者为评判私有，不进入模型输入 |
| `task_family, template_family_id, source_group_ids, derivation_root_ids` | 分组切分依据；相同根的改写不能跨集合 |
| `usage_scope, split_group_id, split_policy_version` | 在生成变体前冻结；已有组不随新增记录变更切分 |
| `dependency_depth, tool_set, recovery_condition, difficulty_bin` | 任务结构属性；难度另记估计方法/基线版本，未知可空 |
| `interaction_budget_ref, initial_state_ref` | 预算和可复位输入；外部任务缺失时不得标可执行 |
| `capabilities` | 布尔/枚举：reset、action_replay、snapshot_restore；每项有证据或显式 unsupported |
| `status` | `DRAFT -> AUDITED -> EXECUTABLE -> FROZEN`；撤销后 `INVALIDATED` |

`TaskGroup` 记录 `split_group_id, member_task_ids_ref, reason_edges_ref, assigned_scope`。分组边包括同源、
同模板根、派生关系和确认近重复；不能以改写分散泄漏。新增边连接不同已冻集合时隔离新任务并
失效受影响版本，不能静默搬移原 test。

## 3. Attempt

字段：`attempt_id, task_id, task_revision, parent_attempt_id, branch_event_id, actor_kind,
policy_ref, sampling_config_ref, harness_ref, environment_ref, preflight_ref, budget_ref,
started_at, finished_at, event_manifest_ref, final_output_ref, end_reason, cost_record_ref`。

`actor_kind` 为 `HISTORICAL_IMPORT | SCRIPTED_FIXTURE | MODEL_GENERATION | MODEL_EVALUATION | TRAINER_SAMPLING`。
`MODEL_GENERATION` 仅用于评测或兼容分支，不得作为 2.1 正式训练示范来源；历史导入没有真实策略元数据时
`policy_ref=null`，不能标为当前策略采样。
运行状态 `CREATED -> RUNNING -> SEALED`；进程中断仍创建 `SEALED` 回执并标明日志是否完整，
未知最后动作结果不伪造完成。快照恢复产生新 attempt，关联父与分支点。

`end_reason`：`COMPLETED | BUDGET_TRUNCATED | ENVIRONMENT_ERROR | CANCELLED | INTERRUPTED`。
任务判定 `outcome` 为 `PASS | FAIL | UNKNOWN`，仅以 VerificationRecord 为权威；封存 Attempt
不保存可变判定。展示时使用带 verification_id 的可重建关联视图，禁止回写封存实体。正常结束
不保证 PASS，截断不能因部分正确默认成功。重新验证新增 VerificationRecord，不覆盖执行终态。

## 4. TrajectoryEvent and DependencyEdge

事件字段：`event_id, attempt_id, seq, event_type, timestamp, model_call_id, tool_call_id,
parent_event_id, payload_ref, visible_context_ref, raw_output_ref, status, origin`。
同一 attempt 内 `seq` 为严格递增整数且 `(attempt_id, seq)` 唯一。事件类型：
`OBSERVATION | MODEL_REQUEST | MODEL_OUTPUT | TOOL_CALL | TOOL_RESULT | CONTEXT_REWRITE |
CHECKPOINT | FINAL_OUTPUT | INTERRUPTION`。工具返回必须关联同一尝试存在的调用，重复回包保留但
不重复应用；无法关联时隔离。模型请求和输出按 `model_call_id` 成对，可有明确不完整的中断尾部。

`DependencyEdge`：`edge_id, attempt_id, from_event_id, to_event_id, source_field, target_field,
relation, provenance, evidence_ref`。跨步参数取值与资料引用可形成依赖；`provenance` 区分固定任务
真值、确定解析、模型推断、人工确认。推断不是已验证因果边。

## 5. VisibleContext and Checkpoint

`VisibleContext`：`context_id, model_call_id, ordered_message_refs, tool_schema_ref,
render_config_ref, input_token_ref, parent_context_id, rewrite_event_id, content_hash`。
必须重建实际发送的消息；分词器/模板能获取时保存身份，输入词元只有实际取得才保存。
`CONTEXT_REWRITE` 包含前后 context 引用、原因、执行者和是否适合所选训练消费策略。
原始完整工具结果和被截短的模型可见结果分别引用，不能混淆。

`Checkpoint`：`checkpoint_id, attempt_id, event_seq, snapshot_ref, environment_ref,
context_ref, restore_capability, state_hash`。仅日志检查点不等于环境快照。
首版受控快照只含不可变语料引用、会话工作区、随机源与工具会话状态；模型权重不属于环境快照。
缺少任何必要可恢复状态必须返回 unsupported；外部不可回滚副作用不能靠重放掩盖。

## 6. VerificationRecord and RewardRecord

`VerificationRecord`：`verification_id, attempt_id, evidence_manifest_ref, verifier_version,
check_results_ref, status, outcome, replay_consistency, mutation_audit_ref, verified_at`。
`status` 为 `VERIFIED | ERROR | INSUFFICIENT | UNSTABLE`；后三者 outcome 为 UNKNOWN。
检查项包含结果正确、证据关联、约束满足和过程诊断，诊断不强制规定唯一解题路径。
参考生成模型不能同时成为唯一评判来源；验证器负对照证据单独保存。

`RewardRecord`：`reward_record_id, attempt_id, verification_id, reward_policy_version,
reward_scope, components_ref, total_reward, availability, unavailable_reason, created_at`。
`reward_scope` 首版为 `TERMINAL`（终局）；未来允许 `STEP`（步骤）并带 event_id，不能静默改变语义。
`availability=KNOWN` 才可为数值，未知为 null。首版映射：已验证 PASS 为 1、已验证 FAIL 为 0；
UNKNOWN 不可映射。诊断项与奖励 components 分离；改变奖励版本增加记录而非覆盖。

## 7. QualityDecision, DedupRelation and DatasetVersion

`QualityDecision`：`decision_id, subject_type, subject_id, policy_version, action, reason_codes,
evidence_refs, actor_ref, parent_decision_id`。动作接受/拒绝/隔离/修复/重选/删除；修复产生新对象。
`DedupRelation`：对象对、类型、相似度、投影/组件/阈值版本、人工判断、代表选择理由。
质量维度独立存结果，不只保存总分；错误示范可保留上下文但是否训练由冻结目标掩码决定。

`DatasetVersion`：`dataset_id, parent_dataset_id, source_manifest_refs, external_demonstration_manifest_ref,
eligibility_manifest_ref, task_manifest_ref, attempt_manifest_ref, membership_ref, recipe_ref,
split_manifest_ref, quality_report_ref, cost_report_ref, data_card_ref, logical_content_hash, status`。
`status=DRAFT -> VALIDATED -> PUBLISHED`；后续撤销创建 `INVALIDATED` 记录，不覆盖旧内容。
`membership` 对 2.1 训练版本引用 external demonstration、其准入决定、来源/修复链和用途；可执行
task/attempt 是可选的附加证据，不是训练发布前提。训练导出记录具体 message/token 目标映射。原始
失败池始终独立于合格示范视图。

## 8. SFTView and SamplingAttachment

SFT（监督微调）视图：`view_id, dataset_id, demonstration_id, context_refs, selected_target_spans,
model_template_ref, tokenized_example_ref, loss_mask_ref, effective_loss_tokens, export_policy_version`。
`loss_mask` 为是否计入训练损失的逐词元标记；用户、工具、输入角色包装和填充为零；模型应生成的工具调用边界/结束词元按冻结模板计入目标。含未知错误定位的示范
不得凭模型评分任意切段。原始生成词元缺失不阻止合法 SFT 重新分词，但必须注明是训练重编码。

`SamplingAttachment` 仅真实训练采样产生：`sampling_id, attempt_id, policy_revision,
trainer_revision, tokenizer_ref, chat_template_ref, per_call_input_ids_ref, per_call_output_ids_ref,
model_output_mask_ref, behavior_logprobs_ref, sampling_config_ref, context_segments_ref,
provenance, consumer_profile`。
词元编号（token ID）为实际分词/生成单元编号。概率字段按算法要求可空，消费资格由已固定的
`consumer_profile` 判定；不得从历史输出补造采样概率。`provenance=ACTUAL_SAMPLER` 才能满足
在线采样要求。词元数和 mask 长度严格一致；重编码副本不覆盖原词元。
历史上下文重写无法按该训练器正确消费时，拒绝资格并保留原始记录。

## 9. CompatibilityReceipt

字段：`receipt_id, task_bundle_hash, adapter_revision, dependency_lock_hash, consumer_profile,
checks_ref, actual_runs_ref, tested_capabilities, unsupported_capabilities, status, evidence_level`。
`tested_capabilities` 分开列：历史轨迹审计、环境重执行、训练接口模拟、真实模型采样、32/128 步
结构、受控快照恢复、稀疏奖励重评分。无统一 `rl_ready=true`；没有实际运行不得写采样通过。
RL（强化学习）参数更新不在首版回执中，后续用独立训练记录证明。

## 10. ExperimentPlan, TrainingRun and Evaluation

`ExperimentPlan`：标识、修订、假设、目标数据差异、候选池、两配方、匹配项及容差、共同模型和
方法选择回执、词元/步数/输入计算预算、曝光/排序规则、种子、评测版本、护栏、判定规则、报价/
预算、预登记时间和哈希。`training_mode=SFT`；未来 RL 使用新计划，增加采样预算/奖励版本，
不能混入原 SFT 配方比较。`DRAFT -> PREREGISTERED -> RUNNING -> CLOSED`；修改冻结项创建新计划。

`TrainingRun`：`run_id, experiment_id, recipe, seed, dataset_id, initial_model_ref,
method_config_ref, batch_schedule_ref, planned_loss_tokens, observed_loss_tokens, optimizer_steps,
runtime_ref, checkpoint_ref, log_ref, cost_ref, status`。`status` 包含成功、失败、中止、预算阻断。
不等有效词元/步数时不能进入因果比较；三种子及所有失败 attempt 不能覆盖或丢弃。

`EvaluationRun`：模型/训练运行引用、套件/子集/协议与解码预算、preflight（运行前检查）、原始尝试
和每题结果、失败重试策略、费用、终态。`EvaluationItem` 包含 task、首次 attempt、重试 attempt、
最终判定、实际调用数/词元/耗时、来源/模板组、错误类别；指标分母由冻结任务集合确定。
外部 benchmark（基准）另含官方 commit、data hash、category、protocol_deviations（协议偏离）。
开发/最终测试分开，汇总按 [plan.md](plan.md#interactive-evaluation) 口径重算。

## 11. Finding, DataAction and Claim

`Finding`：开发评测引用、涉及任务/步骤、错误类型、原因假设、置信程度、反证和目标切片。
`DataAction`：finding、选择/补充/修复/降权等动作、目标数据差异、配方及后续数据版本/复验引用。
正式首轮 ClosedLoop 只在冻结同池重选；新增外部来源或修复只在下一轮重新冻池后用于比较。
状态 `OPEN -> ACTIONED -> RETESTED -> CLOSED`，结果为改善/无变化/回退/不确定。

`Claim`：精确表述、证据层级、全部输入/运行/相反证据引用、成本、限制、重跑入口。
提升、无提升和回退都可以有训练证据；训练证据层级与“正收益”判定不能等同。

## 12. PipelineRun, ScaleBenchmark and DeletionLedger

`PipelineRun`：运行与 attempt 身份、输入、算子图/配置/依赖锁、执行后端、节点/进程数、物理与
逻辑字节、记录数、分片、逻辑哈希、每阶段指标、重试和提交状态、成本。节点数不以进程数替代。
`ScaleBenchmark`：输入 manifest、`BENCHMARK_ONLY`、副本祖先、64 GiB 逻辑量、1/2/4 节点各
5 次原始终态、预热、冻结顺序、故障注入、等价结果和成本。未支持的资源指标为空并说明原因。
`DeletionLedger`：触发原因、来源/对象、全部受影响版本/运行/结论、删除分发副本或失效动作及证据。
已暴露敏感内容从分发与存储按治理规则移除，审计只留必要非敏感标识。

## Publication Invariants

1. 所有已发布成员均能反查外部来源、上游记录/消息、修复父链、训练准入决定和用途；可执行
   task/attempt 仅在存在时作为附加引用。指标从规范明细重算。
2. 外部消息、工具调用/返回和答案的关联可审计；缺必要上下文或目标映射的记录不能冒充合格示范。
3. 初始资源和隐藏参考严格分离；每轮可见上下文与实际请求一致。
4. 同来源/模板派生/重复组不跨训练、开发、test；BENCHMARK_ONLY 不参与学习和评测。
5. 未知验证与奖励不填 0，奖励更新不改原证据，读取日志与实际重执行分开。
6. 真实训练采样附件来自实际采样器；历史数据不补造词元/概率身份。
7. 32/128 步存储通过不自动获得真实长程模型能力；接口通过不自动获得 RL 训练证据。
8. 两 SFT 配方、三个种子全部保留，公平门禁和独立交互评测通过才作数据归因。
9. 增量/本地/分布式逻辑一致；未完整提交不发布；撤销传播到全部关联证据。
