# Artifact Contracts

**Version**: 2.1.0 | **Status**: 2.1 外部训练数据产物语义；运行时实现待 T105–T108。

## 2.1 External Training Publication

正式训练发布只读取冻结的外部原始分片、规范化外部示范、训练准入决定、修复父链与切分登记。
本项目 `TaskPackage`、交互 attempt、验证器结果、固定动作和模型采样记录不得作为训练成员，也不是
外部发布的必需输入。训练准入、可重放性、结果/奖励证据及在线采样资格分别存表；缺后面三者不能
伪造，但不能以此覆盖独立的外部训练准入决定。

## Encoding and Compatibility

JSON（结构化交换格式）以 UTF-8、排序对象键、确定数值表示编码，禁止非有限数；金额为分整数。
YAML（配置格式）先解析成规范内容后计算哈希，注释不影响身份。SHA-256 为内容摘要算法；物理
文件保存字节摘要，数据集另按稳定主键与规范行内容计算逻辑摘要，分片/行序变化不算语义变化。
未知值为 null；空列表表示已知为空。Markdown 报告从事实表派生，不能成为第二套结果状态。
契约主版本 2 不直接接受旧代码样本版本 1，迁移要产生新记录与明确来源关系。

## Required Bundles

| 目录 | 必需产物 | 发布前检查 |
|---|---|---|
| `data/raw/<source-id>/` | `source_manifest.json`、许可及原始分片引用 | 版本、哈希、来源/用途明确 |
| `data/normalized/<build-id>/` | `external_demonstrations.parquet`、`eligibility_decisions.parquet`、`repairs.parquet`、`decisions.parquet`、`split_registry.parquet`；可执行分支另存 tasks/attempts/events | 外键、上游消息/调用关联、修复父链、原始记录对账 |
| `artifacts/interactions/<attempt-id>/` | `attempt.json`、`events.parquet`、`artifact_index.json`、引用的模型输入/输出与工具结果 | 预算、所有终态、不可变封存；不完整尾部显式标记 |
| `artifacts/verifications/<verification-id>/` | `verification.json`、`checks.parquet`、`evidence_manifest.json`、`reward.json`（若请求评分） | 独立证据、验证器身份、未知奖励为空 |
| `data/releases/<dataset-id>/` | `dataset_manifest.json`、`membership.parquet`、`recipe.json`、`quality_report.json`、`diversity_report.json`、`cost_report.json`、`data_card.md`、`lineage_index.json` | 成员可追溯到外部消息和准入/修复证据，切分/污染通过、内容不可变 |
| `data/exports/<view-id>/` | `export_manifest.json`、`training_examples.parquet`、`target_mapping.parquet`、`loss_mask_audit.json` | 每个训练片段能反查 external demonstration/上游消息/准入决定，词元预算可计算 |
| `artifacts/compatibility/<receipt-id>/` | `compatibility_receipt.json`、`checks.parquet`、`run_refs.json`、`dependency_manifest.json` | 接口模拟、真实采样、长程与恢复能力分别列状态 |
| `artifacts/data-runs/<run-id>/` | `pipeline_run.json`、`operator_metrics.parquet`、`retry_events.parquet`、`commit_manifest.json`、原始数据框架统计 | 处理阶段与重试完整，提交前后核对一致 |
| `artifacts/data-benchmarks/<benchmark-id>/` | 输入清单、`scale_plan.json`、`raw_trials.parquet`、`scale_report.json`、故障注入及费用引用 | 64 GiB、真实 1/2/4 节点各 5 次；复制身份隔离 |
| `artifacts/experiments/<plan-id>/` | `experiment_plan.json`、模型/方法/预算门禁、批次清单、匹配报告、`run_registry.parquet` | 两配方三个种子、等预算、全部终态 |
| `artifacts/evaluations/<run-id>/` | `evaluation_run.json`、`items.parquet`、`attempt_refs.parquet`、`metrics.json`、`protocol_deviations.json` | 冻结分母、真实交互、独立判定和系统故障计数 |
| `reports/<report-id>/` | `report.md`、`claims.json`、`findings.parquet`、`data_actions.parquet`、`lineage_index.json` | 所有指标可重算，保留无提升/回退 |

每个 bundle 包含产物索引：逻辑标识、相对位置、内容哈希、大小、类型、产生运行和访问范围。
大工具观察、词元附件、快照使用引用；不能把隐藏答案打包到模型可访问目录。

## Build Input Manifest

`data/build-inputs/<name>.json` 明确关联 `source_manifests`、`external_demonstration_manifests`、
`eligibility_manifests`、`repair_manifests`、`split_registry_ref` 与规则版本；所有引用均带哈希。
可执行 task/attempt/verification manifests 是独立分支的可选附加输入，不能替代或自动生成训练准入。
不默认从邻近目录猜测输入，也不调用模型、工具或环境补全外部示范。集合中的重复引用按实体标识对账，
不能重复计数。

## Attempt and Publication Semantics

- 构建标识包含输入清单、规则、依赖与切分登记簿版本；执行 attempt 另有唯一标识。重试同一构建
  可以复用验证完整的中间产物，但不同整任务尝试不能共享 attempt_id；同一多轮尝试包含多个具有独立 model_call_id 的模型调用。
- 写入临时分片→完成所有哈希/计数/关系检查→提交不可变 manifest（清单）。中途失败不发布，
  清单存在但内容不一致时拒绝覆盖。
- 发布清单保存原始、接受、拒绝、隔离、删除等计数，按不重叠终态对账；“有过失败后修复”另有
  过程计数，不与最终状态相加。
- 增量与全量均读取同一已冻切分登记簿。新近重复边连接既有训练/测试对象时，记录冲突并阻断受
  影响发布；不能在全量重建时重新抽签分配集合。
- 外部示范无环境/策略资料时允许保存 null；其重放与在线采样消费资格为不支持/未知，但训练发布
  只按独立准入规则决定。

## SFT Export Contract

SFT 指监督微调。导出含模型期望的工具定义、完整必要消息上下文、目标片段及映射。工具调用和
返回标识必须对应；用户消息、工具观察、输入角色包装和填充的 loss_mask 为零；模型应生成的
工具调用边界、参数及结束词元按冻结模板计入训练目标。正常回答与工具调用均须做词元级测试。
源轨迹不因导出改写；格式规范化与实际历史词元分别保存。公开样本重新分词只能称 SFT 编码，
不能成为真实 RL（强化学习）采样附件。错误动作仅在可靠标注下可作非目标上下文。
过长样本拒绝或按已有完整上下文策略导出，不能隐式截去前置工具结果。

## Quality and Sparse Reward Accounting

至少报告：外部原始/规范/合格/发布示范、独立上游任务/派生数、拒绝/待复核/修复、重复/泄漏、
来源/模板/依赖深度/长度/能力切片、处理前后配比、有效训练词元与来源获取/治理/复核成本。可执行
任务、实际尝试、验证轨迹和奖励为独立分支统计，不混入训练成员或训练成本分母。

奖励可计算率 = 已知奖励尝试数 / 请求奖励的全部尝试数。
全零任务比例只在“至少一次已知奖励且所有尝试的奖励均已知”的任务中计算，分母单列；存在未知
的任务另列，不能冒充全失败。每千条合格轨迹成本包含生成、失败、验证和加工分摊；产量为零则
不可计算并显示总支出。费用统计包含实际失败/重试，不因为被筛掉而消失。

## Experiment and Claim Gate

所有模型收益必须关联同一个预登记计划中的两配方、种子 `[17,29,43]`、实际参数更新与检查点、
匹配和批次/词元审计、独立实际交互评测及全部运行终态。基础模型只是背景分数。
收益、无收益、回退、失败和未知各有正式状态；训练证据层级不意味着正收益。
没有环境证据不得签发隔离执行结论，没有真实采样不得签发采样兼容结论，没有多节点不得签发
扩展性能结论。相关数据结构和 CLI 已存在也不能代替这些运行。

## Research and Dependency Evidence

`dependency_manifest.json` 保存名称、用途、官方来源、准确版本/提交、许可文件摘要、锁文件摘要、
安全/兼容检查日期、通过/失败记录；访问 latest 文档不作为已固定版本。
`research_source.json` 保存查询、标题、发布者、链接、原始日期、访问日期、版本、替代检查和支持
的具体设计。旧资源盘点不能冒充符合宪章日期要求的新方法研究。
