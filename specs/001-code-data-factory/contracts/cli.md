# CLI Contracts

**Version**: 2.1.0 | **Status**: 命令骨架已存在；外部训练数据流实现待 T105–T108。
CLI 指命令行界面，`cdf` 为本项目命令名；`uv run` 为 Python 项目运行方式。
命令仅包装现成数据/训练组件和项目业务规则，不实现通用调度、模型服务或外部工具平台。

## Common Envelope

每个命令支持 `--json` 和 `--output-dir`。结构化输出包括 `command, run_id, status, evidence_level,
artifact_refs, counts, warnings, errors`。日志走标准错误，结构化结果走标准输出；费用与运行状态
必须保存。`--dry-run` 只校验配置/依赖，不能签发执行或训练证据；拒绝假实现的成功输出。

退出码：0 为该命令在声明范围内完成（例如诊断出坏样本也可完成）；2 输入/模式错误；3 环境或依赖
缺失；4 执行基础设施失败；5 用户取消；6 哈希/逻辑不一致；7 超预算；8 质量/证据/兼容门禁未通过。
轨迹 FAIL 是任务结果，不能一律当命令内部异常；质量命令是否以 8 退出由其验收门槛决定。

路径 `configs/...` 是版本化配置。2.1 的训练主线不调用 `trajectory collect`：外部来源审计、导入、
构建、发布和导出在没有本地交互环境或模型生成调用时可独立运行。

## Data Production Commands

| 命令及主要参数 | 产物/行为 | 门禁 |
|---|---|---|
| `cdf source audit --manifest <path>` | 外部来源版本、许可、分片哈希、字段/工具定义、记录数、准入候选与拒绝原因 | 来源审计不签发训练准入或执行 PASS |
| `cdf task build --config <path>` | 独立任务、初始资源、真值、来源/模板组和切分登记 | 先分组再生成变体；缺初始条件不能标可执行 |
| `cdf trajectory import --source <path> --adapter <name>` | 外部原始消息/调用/返回/答案到规范示范映射、歧义隔离、修复父链 | 历史身份不能变成当前策略采样或本项目执行结果 |
| `cdf trajectory collect --tasks <manifest> --config <collection-config> --execution-config <path>` | 调用 smolagents、完整实际尝试、费用 | 运行前环境/预算门禁；隐藏参考不对模型可见 |
| `cdf data build --input <manifest> --config <path> --backend local\|ray` | 外部示范准入、去重、切分、质量/覆盖、增量草稿 | 同一冻结语义；每次拒绝/待复核/修复有证据；禁用本项目采样成员 |
| `cdf data build --input <manifest> --config <path> --backend ray --resume <run-id>` | 按已提交输入/分区恢复 | 不重复发布，不把恢复运行当原运行从未失败 |
| `cdf dataset publish --draft <path>` | 外部合格成员、质量/成本/数据卡与双向谱系 | 上游消息/修复链/准入、切分、数据及哈希完整；不要求环境重放 |
| `cdf dataset export-sft --dataset <manifest> --config <path>` | 训练视图、目标片段、loss-mask 审计 | 排除观察/用户损失，保留模型控制词元；失败原池不变 |
| `cdf source revoke --source-id <id> --reason <text>` | 撤销台账、受影响版本/实验/结论 | 不清除必要非敏感审计，不继续分发失效内容 |

## Verification and Extension Commands

| 命令及主要参数 | 产物/行为 | 门禁 |
|---|---|---|
| `cdf environment check --config <path>` | 非特权、挂载、网络、资源与版本检查 | 不合格不能发隔离执行证据 |
| `cdf trajectory inspect --attempt <path>` | 原始轨迹回看 | 只读日志，不调用环境 |
| `cdf trajectory replay --attempt <path> --environment <path>` | 固定动作真实重执行的新 attempt | 原始环境不可恢复就拒绝；不自动替换工具 |
| `cdf verify run --attempts <manifest> --config <path>` | 最终结果、证据、约束及诊断 | 未知/不稳定不填 PASS 或 0 |
| `cdf reward rescore --evidence <manifest> --policy <path>` | 新版本奖励与差异 | 不重采样，不覆盖旧证据 |
| `cdf compatibility check --profile <path> --mode contract\|sampling\|long-horizon` | 接口、真实采样、长程三种独立回执 | sampling 必须真实模型词元；contract 替身不可升级 |
| `cdf benchmark run --plan <path>` | 固定规模 Ray 原始运行与故障证据 | 真实节点/报价/输入冻结，性能副本用途隔离 |

`long-horizon` 指长程契约，运行 32/128 步确定性案例与受控恢复，不启动长程模型训练。
`sampling` 指训练器生成轨迹的探针，不调用强化学习优化器；未通过依赖或费用门禁不得运行。

## Feedback, Experiment and Evidence Commands

| 命令及主要参数 | 产物/行为 | 门禁 |
|---|---|---|
| `cdf evaluate run --model <ref> --suite <path> --split development\|test` | 实际交互与独立逐题评测 | test 仅在正式冻结后解锁；系统故障按预登记口径 |
| `cdf feedback build --evaluation <manifest> --pool <manifest> --policy <path>` | 开发发现、数据动作、两配方草稿及匹配报告 | 不读取最终 test；失败模式覆盖为目标干预 |
| `cdf experiment calibrate --config <path>` | 模型/方法/模板兼容、保存重载、词元/成本测量 | 事前顺序，只选择一种方法，不做正式效果搜索 |
| `cdf experiment preregister --config <path> --calibration <manifest>` | 六次运行计划、批次表、预算与分析规则 | 等有效词元/步数/计算配置、冻结匹配与 test |
| `cdf experiment run --plan <path> --recipe <name> --seed <int>` | 调用上游 SFT、真实参数更新记录 | recipe 仅两个合法值；seed 仅 17/29/43；保留所有终态 |
| `cdf report build --plan <path>` | 对照差异、波动、护栏、质量/成本/反馈和完整结论 | 不能以正分数覆盖缺失证据 |
| `cdf evidence verify --manifest <path>` | 所有引用/哈希/指标重算与层级审计 | 证据缺失返回 8，不自动生成模型收益 |
| `cdf reproduce --manifest <path>` | 从冻结输入重建所选数据或证据 | 外部付费运行另受预算门禁；不能以日志拷贝冒充重跑 |

`recipe` 取 `sft-random-matched` 或 `sft-closed-loop`。未来 RL 优化是新计划类型与阶段，本版 CLI
不提供假 `train-rl` 占位命令。归因、实际采样和长期兼容要求由已有契约验收，而不是命令数量证明。
