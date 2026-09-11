# Research Decisions: Agent 工具调用轨迹数据工厂

**Revision**: 2.1 | **Research date**: 2026-09-08 | **Migration reviewed**: 2026-09-11 | **Method evidence cutoff**: 2026-04-01

本文记录组件与方法选择。结论是本项目设计选择；外部接口可读不代表本地兼容性通过。所有组件
在实施首个兼容门禁固定版本、许可、内容摘要和依赖锁；没有实际运行的组合保持 `UNVERIFIED`
（尚未验证）。历史原料可用性审计与当前方法研究分开，旧数据不作为新方法的时效证据。

## Research Method and Source Register

检索条件：`site:huggingface.co/docs/trl grpo tool environment rollout_func`、
`site:verl.readthedocs.io agent loop multi turn rollout`、
`site:gorilla.cs.berkeley.edu BFCL v4 multi turn benchmark 2026`；并直接读取下表官方资料。
访问日期均为 2026-09-08。网页标为 latest/stable 但无原始更新日期的记录不能当作有日期的新研究。

| 标识 | 资料、发布者与链接 | 原始日期/版本核查 | 支持范围 |
|---|---|---|---|
| R01 | Hugging Face 作者，[Agentic RL: Token-In, Token-Out Done Right](https://huggingface.co/blog/huggingface/tito) | 原文 2026-05-29；符合方法门槛 | 原采样词元保留、上下文改写和截断的兼容设计 |
| R02 | Hugging Face，[TRL 环境接入](https://huggingface.co/docs/trl/openenv) | 在线未固定版本；用于接口核查，不充当新研究日期 | 环境工厂、逐工具方法、奖励读取、自定义交互扩展点 |
| R03 | verl 项目，[Agent Loop](https://verl.readthedocs.io/en/latest/advance/agent_loop.html) | 在线未固定版本；接口核查 | 原始词元及模型输出掩码；备选训练集成路径 |
| R04 | NVIDIA，[NeMo Gym Evaluate](https://docs.nvidia.com/nemo/gym/evaluation/) | 在线文档无已核实原始更新日 | 同环境复评与重新评分；作为工程接口参考，不宣称新算法收益 |
| R05 | Berkeley，[BFCL V4](https://gorilla.cs.berkeley.edu/leaderboard.html) | 官方页 Last Updated 2026-04-12；指向 `f7cf735`、包 2025.12.17 | 当前仍使用的工具调用外部评测；不宣称完整榜单最新于访问日 |
| R06 | Berkeley，[CHANGELOG](https://github.com/ShishirPatil/gorilla/blob/main/berkeley-function-call-leaderboard/CHANGELOG.md) | V4 发布记载 2025-07-17；当日读取记录含旧更新，不据此推断新版本 | 核对 V4 含多轮、工具相关性和 Agent 类别；与 R05 配合选冻结子集 |
| R07 | Hugging Face，[smolagents agents](https://huggingface.co/docs/smolagents/reference/agents) | 在线接口自述 experimental；必须锁版本 | ToolCallingAgent、step_callbacks、max_steps、完整结果接口 |
| R08 | Agent-Ark，[Toucan 数据卡](https://huggingface.co/datasets/Agent-Ark/Toucan-1.5M) | 本地审计 revision `0df3cf37f2abefb380370cfb02eabea2a35ae782`，来源更新 2025-10-04 | 原料存在及格式；不是已验证可执行任务库，不作新方法证据 |
| R09 | Ray，[Ray Data 文档](https://docs.ray.io/en/latest/data/data.html) | 当日文档显示 2.58.0 | 保留批处理规划基线，仍需 Linux 兼容实测 |
| R10 | datasketch，[MinHash](https://ekzhu.com/datasketch/minhash.html) | 当日文档显示 2.0.0 | 集合近重复指纹，不是 embedding 语义去重 |
| R11 | DuckDB，[全文索引](https://duckdb.org/docs/stable/core_extensions/full_text_search) | 在线 stable，未固定发布包 | 有界冻结语料检索，索引可重建 |
| R12 | Pint，[单位库](https://pint.readthedocs.io/en/stable/) | stable 链接当日显示开发版字符串；不据此锁预发布包 | 复用单位定义，实施从正式 release 选择 |
| R13 | Python，[History and License](https://docs.python.org/3/license.html) | 当日文档 3.14.7；固定内容前另存许可文件 | 文档输入来源审计，不是项目 Python 运行版本 |
| R14 | Qwen，[Qwen3-8B 模型卡](https://huggingface.co/Qwen/Qwen3-8B) | 当日官方卡可读；Apache-2.0；具体 revision 待下载冻结 | 保留已有测量候选，不能从模型卡推断本项目单卡训练已通过 |
| R15 | Hugging Face，[SFT Trainer](https://huggingface.co/docs/trl/sft_trainer) | 在线未固定版本；接口核查 | 多轮示范消费、模板和训练损失处理；实际掩码须本地检验 |

以上仅 R01、R05 的已核实日期用于当前方法/基准采用依据。其他为现有开源组件或资源盘点；
涉及算法提升的推断不得由无日期文档支持。本版不采用未经核查的新 RL 算法或模型收益结论。

## 2.1 Source and Eligibility Migration

**Decision**: 正式 SFT 训练示范取自外部开源数据集，外部历史轨迹不再被统一限制为仅任务参考。
训练准入、可重放性、结果/奖励证据和在线采样资格分别审核；本项目受控任务、固定动作、评测输出
和模型采样不进入首版训练池。

**Evidence boundary**: 这是用户确认的流向与契约迁移，不是任何外部来源已经合格、许可可用或质量
通过的结论。实际来源选择、版本、字段、许可和代表样本审核由 T045 冻结；若不合格，选择其他外部
来源而不是自行生成补量。

## Decision 1: Concrete Task Scope and Existing Data

**Decision**: 信息查询、计算、单位与时间转换保留为受控验证/评测任务范围。Toucan 是外部训练示范
候选，须按 2.1 独立准入政策审核；能否重放仅决定可重放子集证据，不能替代训练准入。

**Rationale**: 内容易理解，不需要私有业务知识，目标值和来源依据可独立判定，且多步依赖自然存在。
此前已全量审计 Toucan 精选集 119287 条；办公候选仅 227 条相关记录，147 次基础函数重放中发现
44 条“无工具错误返回但文档颜色结构错误”，因此撤回办公主线。该观测是历史本地原函数检查，
不是 Linux 隔离执行、完整服务协议或全任务正确性结果。公开证据摘要保留在证据日志。

**Alternatives considered**: 电商售后依赖未知业务规则；办公文件需要未提供的初始附件和视觉真值；
通用代码修复会扩大环境与算法投入。当前方案保留已有任务表达，但不把远程服务名映射到本地函数
后假称原环境重放。100 任务先导有明确停止门禁；数据量不足先定位原料/质量问题。

## Decision 2: One Data Processing Stack

**Decision**: 沿用 Pydantic + PyArrow/Parquet + DuckDB + Ray Data + DVC + MLflow 的分工；
使用一个批处理引擎，数据处理算子同时可本地执行，数据事实与运行索引分开。

**Rationale**: 覆盖解析、批量处理、结构校验、切片查询、质量和资产治理；无需部署数据平台。
Ray 是主要新增分布式实践，SQL 分析可直接解释配方、失败与成本。规模复制集有单独身份和用途。

**Alternatives considered**: Spark 同样能完成批处理，但本版保留已选 Ray，避免维护两套等价语义。
Airflow/Prefect 增加调度与服务维护；DVC stage 已满足本项目离线依赖、缓存和重跑。
DataTrove 很适合文本语料算子与去重；完整引入其执行器会与 Ray Data 重叠，且本项目主对象是
任务、事件和多表关系。若后续单个成熟算子满足轨迹投影输入，允许只复用算子，不重建框架。

## Decision 3: Reuse Deduplication and Retrieval

**Decision**: 精确哈希 + datasketch MinHash/局部敏感哈希候选；任务祖先与来源图另行管理。
只读资料检索复用 DuckDB 全文索引。句向量工具 Sentence Transformers 和向量库 FAISS 为有证据
才启用的语义复核备选；不写自有相似检索算法。

**Rationale**: 工具名重复不是任务重复；相同调用序列也可能有不同参数关系和目标。项目价值在
投影规则、分组切分、误合并/漏检抽审和多样性取舍。先完成 100 对候选人工审阅再冻结阈值。

**Alternatives considered**: 单纯字符串去重漏掉模板改写；只用向量相似会合并数值/条件不同任务；
额外向量数据库与当前规模无关。Embedding（向量表征）和 MinHash 不能混称同一种“语义去重”。

## Decision 4: Reuse Agent Execution, Keep Task Semantics Local

**Decision**: smolagents `ToolCallingAgent` 负责多轮循环；项目实现工具包装、实际输入/输出拦截、
步骤回调与规范事件映射。工具为只读检索、明确四则运算、Pint 单位转换与标准库时间转换。

**Rationale**: 不自研通用 Agent 框架。现有库的 callback 不必然包含精确模型请求，因此模型接口
边界也须记录；`max_steps` 不一定等于总工具调用数，批量调用、最终答案和辅助模型调用均须计预算。

**Alternatives considered**: CodeAgent 默认生成代码，会引入不需要的任意代码执行；通用工作流平台
和多 Agent 协作不属于本任务。NeMo Gym 可提供环境/评测体系，但首版引入其多服务运行结构会增加
环境平台工作；只借鉴并核对其验证/重评分接口，不重复安装整套系统。

## Decision 5: RL Compatibility Is an Acceptance Gate

**Decision**: 优先一个 TRL 环境工厂适配，复用本地工具、复位与验证器；实际采样不更新参数。
公开历史示范的原始词元缺失保留未知，后续 RL 由真实训练采样器生成词元/概率附件。

**Rationale**: R01 支持保留真实采样词元的设计；R02 确认上游已有环境接口。两者支持设计，不能
替代本地集成验证。分别出接口回执、真实采样回执、环境执行回执，不使用一个泛化标签混淆。

**Alternatives considered**: 只写奖励导出不能接在线训练；立即实现 RL 平台抢占数据工程范围；
同时支持 verl 增加维护矩阵。后续若 TRL 实测缺少必要能力，再按失败证据选择 verl，复用核心契约。

## Decision 6: Long-Horizon and Sparse-Reward Data First

**Decision**: 首版完成 32/128 步结构与受控恢复测试，事件按步骤存储，大内容走引用；保存可见
上下文和显式历史改写。奖励记录区分终局零奖励、未知、截断，重评分不改原始证据。

**Rationale**: 先保住不能事后恢复的信息；未来只增加具体任务、采样策略和训练附件。长程测试不
消耗正式长上下文 RL 训练预算，也不冒充模型长程能力。

**Alternatives considered**: 所有步骤嵌套一行影响流式处理和恢复；通用快照/分支平台依赖环境深层
语义。只为一个冻结语料/会话环境实现受控快照；其他环境显式声明不支持。过程诊断不自动变奖励。

## Decision 7: Data Attribution and External Evaluation

**Decision**: 保留两配方三种子 SFT；任务失败模式覆盖为唯一干预，其余条件匹配。主指标改为
整次交互成功率；BFCL V4 固定本地类别子集作为独立外部锚点。

**Rationale**: 训练测试一个数据假设，避免算法搜索。R05 仍在 2026-04-12 官方更新中使用 V4，并
给出复现代码基线；选其本地类别以减少外部依赖。工具协议和任务语义必须复核，不能把官方 runner
可安装当成结果有效。

**Alternatives considered**: 旧代码/SQL 基准偏离新主任务；只用自建集合缺少外部参照；完整 BFCL
包含首版无意覆盖的能力与在线条件。允许明确的子集结果，不算官方完整总分。SFT 对比不回答 RL 优劣。

## Component Adoption Gate

| 组件组 | 当前决定 | 实施门禁与失败动作 |
|---|---|---|
| Python 数据栈、uv、DVC、MLflow | 沿用职责；Ray 2.58.0 是规划基线，其他精确版本由锁文件统一固定 | 从上游正式 release 和许可文件建清单；Linux 安装、读写/重建、依赖冲突和安全公告核查；未通过不得扩大跑数 |
| datasketch | 新增首选 | 固定随机种子、签名维度；近重复对照与多模式等价；误合并超出冻结门槛则修规则 |
| smolagents | 新增首选，承认 experimental 接口风险 | 精确输入记录、参数/回调、停止与总调用预算测试；版本升级重新跑契约；不默认 fork 上游 |
| TRL/PEFT/Transformers | 沿用训练，增加一个环境适配 | 同工具定义、真实采样、掩码、模板和保存/重载；失败只保持软件回执 |
| DuckDB 全文扩展、Pint、时间库 | 本地工具首选 | 预装冻结扩展与单位/时区数据，断网运行；工具和独立真值交叉检验 |
| BFCL | V4 官方指向提交作为基线 | 解析完整提交、许可及数据 hash，固定子集/官方命令；失败不退回代码基准冒充覆盖 |
| Qwen3 测量候选 | 8B 优先，4B 事前备选 | 官方 revision/工具模板/许可、实际反向传播与预算门禁；不按正式分数换模型 |

所有“自研例外”必须提供：所需数据语义、现成接口为何不满足、已比较组件、最小补充代码范围、
验证和维护责任。不得以“实现起来简单”直接重写已有调度、Agent 循环、去重或训练功能。

## Resolved Decisions and Remaining Execution Evidence

范围、主要组件、唯一数据干预、RL 适配入口和长程验收已确定。外部来源的训练准入尚待实际审核。
尚待实施的证据：外部示范准入/发布、组件组合锁定、真实采样、多节点、SFT 与数据收益。
这些门禁失败时保留明确未完成记录，不能由本文来源或规划代替。详细字段与验收入口见
[data-model.md](data-model.md)、[quickstart.md](quickstart.md)。
