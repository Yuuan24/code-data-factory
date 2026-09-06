# Implementation Plan: Code Data Factory

**Branch**: `main`（Git 默认分支；规格特性名为 `001-code-data-factory`）
**Date**: 2026-09-04  
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-code-data-factory/spec.md`

## Summary

用约 12 周实现一个由数据工程主导、以 Python 为主、同时支持本地和 Ray Data 分布式批处理的
代码训练数据工厂。主交付物是可版本化的任务、候选解答、测试/验证器、执行结果、可选 RL-ready
奖励记录、质量/多样性指标和端到端谱系，而不是模型训练框架。系统从有界、
许可明确且固定版本的 Python 代码来源出发，完成生成、治理、去重、质量和多样性控制，并在独立
Linux 沙箱中做失败关闭的真实执行验证。

目标能力收敛为“受约束数据工程任务中，一次生成 Python 转换或修复程序的端到端成功率”，并以
未见任务/数据集泛化、推理成本、通用能力和安全表现为护栏。代码文本相似度和通用代码能力不作为
最终目标；最终数据产物和隐藏不变量才决定任务是否成功。正式数据价值实验只使用监督微调
（Supervised Fine-Tuning，SFT），比较 `SFT-RandomMatched` 与 `SFT-ClosedLoop` 两个同池匹配数据
版本，三个种子共六次运行。继续预训练（Continued Pre-Training，CPT）和强化学习
（Reinforcement Learning，RL）都不进入 12 周正式训练矩阵：前者需要远超个人预算的语料规模，
后者会引入 rollout 服务、奖励在线执行和策略稳定性等训练工程变量。项目可发布带可重放奖励的
RL-ready 数据，但不能把兼容产物写成 RL 训练收益。训练只是下游测量仪器，GPU 规模由单卡 SFT
冒烟与校准结果决定；全参数微调、低秩适配（Low-Rank Adaptation，LoRA）和量化低秩适配
（Quantized LoRA，QLoRA）只参加事前可行性门禁，正式矩阵冻结其中一种，不比较训练算法优劣。

## Technical Context

**Language/Version**: Python 3.12；若第 1 周确认所选 PyTorch/CUDA 组合不支持，则整个项目统一降为
Python 3.11，不维护双版本环境  
**Primary Dependencies**: `uv`、Pydantic v2、PyArrow/Parquet、DuckDB、Ray Data/Ray Jobs、Data Version Control
（数据版本控制，DVC）、MLflow Tracking、PyTorch、Transformers、TRL、PEFT、Accelerate、
版本冻结的外部 benchmark 官方 runner、Docker Engine、gVisor
`runsc`、Ruff、pytest、coverage.py；核心契约边界使用 mypy  
**Storage**: 本地或共享对象/网络文件系统中的 Parquet、JSON、YAML 和 Markdown；DVC 内容寻址
缓存管理数据及大型产物；MLflow 使用本地 SQLite 元数据与本地 artifact store 记录运行索引  
**Testing**: pytest 单元、契约和集成测试；Ruff 格式与静态规则；mypy 检查核心状态与契约；
coverage.py 记录覆盖；生成测试须通过确定性错误实现或 mutation canary（变异哨兵）  
**Target Platform**: 开发、数据处理和训练均以 Linux 为目标；数据伸缩实验优先在通过网络与共享
存储探针的 OpenBayes CPU 容器上组成 1、2、4 个同构 central processing unit（中央处理器，CPU）
worker node（工作节点）的 Ray 集群，探针失败则使用普通 Linux CPU 虚拟机；训练使用 OpenBayes
的 NVIDIA GeForce RTX 5090，单卡公开规格为 32 GB 显存，账户最多同时租用 8 张；
不可信代码执行使用与 Ray 数据节点和训练主机隔离的 Linux CPU 主机及 gVisor  
**Project Type**: 单一 Python 命令行应用、本地/分布式双模式可复现批处理流水线；无 Web 应用、公共服务或
多租户平台  
**Performance Goals**: 数据构建记录每个 Ray 算子的 wall-clock（墙钟时间）、峰值内存、对象存储
spill（溢写）、shuffle（重分布）、重试、输入/输出样本数和吞吐；同一冻结输入在本地和 Ray 模式
的逻辑内容哈希一致；固定 64 gibibyte（吉比字节，GiB；`2^30` 字节）benchmark-only（仅基准测试）
工作负载完成 1/2/4 工作节点各
5 次实测并报告扩展效率；每个 SFT 运行默认使用一张 RTX 5090，租到多张卡时只并行独立的配方/
种子运行，最多八张卡不等于单机八卡。数据并行不是首版依赖  
**Constraints**: 12 周个人项目；首版只处理 Python；来源不超过 50 个固定提交、原始代码不超过
500 万行；GPU 启动预算 5,000 元、论证后最高约 10,000 元；研究资料必须通过宪章时效门禁；
无安全环境或真实训练时必须降级证据；Ray 基准数据不得进入训练或评测  
**Scale/Scope**: 真实治理/训练候选以十万级以内样本为设计范围；另用确定性回放形成 64 GiB
仅基准测试数据，验证 1/2/4 节点分布式执行而不冒充真实训练语料规模；不覆盖多模态、互联网级
采集、petabyte/exabyte（拍字节/艾字节，PB/EB）级存储、数据库内核、Kubernetes 或组织级数据平台

## Assumptions and Frozen Decisions

- 人民币 5,000 元是 GPU 租赁启动软上限，10,000 元是本计划允许论证的最高金额；Ray CPU 工作
  节点、对象存储、低配 CPU 沙箱主机和可选模型接口费用暂不计入，但全部记录实际单价、节点时和
  金额。若 5,000 元实际是全部现金成本，实施前把所有
  现金支出统一纳入同一预算台账。
- Ray 2.58.0 是当前规划基线，但最终版本由第 1 周 Linux/Python 兼容性冒烟和 `uv.lock` 冻结。
  Ray Data 只承载可信数据的读取、批量转换、重分布、汇总和写出；它不在 worker 进程中直接执行
  不可信生成代码，也不替代 gVisor、DVC、MLflow 或训练框架。
- OpenBayes 官方文档证明同一创建人的运行中容器可通过私有 Internet Protocol（互联网协议，IP）
  地址和 Secure Shell（安全外壳协议，SSH）通讯，但没有直接承诺 Ray 所需全部端口、IP 在整轮
  实验中的稳定性或并发容器共享可写文件系统。正式采用 OpenBayes CPU
  容器前必须完成节点互达、Ray 控制面/数据面、版本、同构资源和共享对象存储读写探针；任一失败
  就切换为具备私网和共享对象存储的普通 Linux CPU 虚拟机，不用公网端口映射勉强拼接集群。
- 本地与 Ray 模式调用相同的纯业务算子和 Arrow Schema。Ray 的分片顺序、物理文件数量和文件名
  不是事实语义；按主键排序计算的 `logical_content_hash` 才用于等价性与发布门禁。
- 正式测量使用已经具备指令遵循和代码能力的 7B–8B checkpoint（检查点），第一候选为
  `Qwen/Qwen3-8B`，第二候选为 `Qwen/Qwen2.5-Coder-7B-Instruct`。第 1 周冻结官方 revision
  （修订号）、tokenizer（分词器）和 chat template（对话模板）哈希；任何门禁失败时只能按此
  顺序更换，不能查看正式处理组结果后换模型。3B–4B 仅作 RL 软件链路与容量地板冒烟，27B 不在
  首版范围。模型名称和可用 revision 仍需在租机前通过官方模型卡重新核验。
- RTX 5090 的 32 GB 单卡显存是单次运行的公开边界，租机后必须以 `nvidia-smi` 实测值确认。
  正式 SFT 不预先硬编码量化方式：全参数微调、LoRA 和 QLoRA 按预登记的资源与简化门禁核验，
  最终只冻结一种。任何精度、
  量化或参数更新方式变化都必须对所有对照组统一应用、重新校准和预登记。
- 8B SFT 从上下文 2,048 词元、每卡微批量 1、全局批量 16 个序列和梯度检查点开始；这些只是
  租机后校准起点，不是显存或吞吐承诺。LoRA 候选初始使用 rank 32、alpha 64、dropout 0.05，并
  作用于 attention（注意力）和 MLP（多层感知机）的线性投影；QLoRA 候选另使用 4-bit
  NormalFloat（4 位归一化浮点，NF4）、double quantization（二次量化）和 BF16 计算。全参数候选
  不引入项目自研分布式训练器。三者都必须记录峰值显存、吞吐、数值稳定性、检查点重载和六次
  正式运行成本投影；门禁只选方法，不产生可发布的模型效果比较。
- 最多 8 张卡只表示用户确认的租赁并发上限；OpenBayes 当前公开价格页只确认单卡实例，不证明
  2/4/8 卡位于同一节点。正式运行按实际可用单卡实例分批完成并轮换配方到硬件；DDP 不是首版
  必需能力。
- OpenBayes 当前公开按量价为每张 RTX 5090 每小时 2.9 元。运行前必须重新保存报价快照；若报价
  或资源形态变化，以预登记前快照为准并重算预算。
- OpenBayes 传统容器的根文件系统是临时的。仓库、`uv` 环境、日志、检查点和运行清单必须写入
  `/openbayes/home`；冻结数据与基础模型优先作为只读数据仓库绑定到 `/openbayes/input/input0-4`。
  正式实验使用可自动结束的 Python 脚本任务，不依赖持续打开的 Jupyter 交互会话。
- 外部生成模型通过 OpenAI-compatible（兼容 OpenAI 协议）适配器使用，是可替换依赖；其输出
  必须经过相同治理和验证，不能因模型评分而直接进入已验证层。
- 训练、评测、安全执行和 Ray 调度都是外部运行能力。项目实现数据业务算子、薄适配、契约和证据
  采集，不自行实现训练框架、优化器、分布式训练调度器、通用 rollout 平台或沙箱内核。

## Constitution Check

*GATE: Phase 0 研究前已检查；Phase 1 设计完成后必须再次检查。*

| 宪章门禁 | 设计响应 | 首次检查 |
|---|---|---|
| 真实训练后才能发布模型提升 | `PublishedClaim` 只有关联真实参数更新、训练日志、检查点与真实评测后才能成为 `TRAINING-EVIDENCED` | PASS |
| 固定预算公平归因 | 每个对比在运行前冻结相同基础权重、训练方法及配置、有效训练词元、步数、优化器、学习率计划、上下文、种子和评测版本 | PASS |
| 端到端谱系 | DVC 数据版本、MLflow 运行、评测产物和结论以统一谱系键连接，并保存内容哈希 | PASS |
| 分级证据与失败关闭 | 治理、执行结果、测试强度和结论证据层级使用正交状态；gVisor preflight 未通过时不能晋级 | PASS |
| 完整诚实结果 | 预登记的成功、负向、无变化、失败、中止和预算超限运行全部保留 | PASS |
| 大模型研究证据时效 | `research.md` 将大模型方法来源与通用组件来源分开记录，并保存日期、版本和替代检查 | PASS |

没有宪章豁免，也没有未解决的 `NEEDS CLARIFICATION`。基础模型精确标识、正式词元规模和卡时上限
由第 1 周预先定义、正式结果可见前执行的兼容性与成本门禁冻结，均有确定输入和输出，不是等待
业务选择的需求缺口。

## Architecture

```text
固定提交的许可允许 Python 来源 + 版本化合成任务
                         │
                         ▼
来源冻结 → Ray Data 读取 → 许可/密钥/个人信息治理 → 解析/标准化 → 精确、语法树与近似去重
                         │
                         ▼
候选生成 → 静态质量 → 独立 Linux gVisor 编译/测试 → Ray Data 汇合 → 质量、多样性、敏感性切片
                         │
                         ▼
冻结 SFT-RandomMatched / SFT-ClosedLoop 任务—答案—验证器数据版本
                         │
                         ▼
外部 TRL + PEFT 薄 SFT → 一次生成端到端任务评测 → 评测发现 → 一次专项数据反馈
                         │
                         ▼
             证据索引 + 机器清单 + 静态 Markdown 报告
```

### Component Responsibilities

| 组件 | 单一职责 | 不承担的职责 |
|---|---|---|
| Pydantic | 单条记录、清单与命令输出的运行时契约 | 大表分析 |
| PyArrow + Parquet | 规范表结构和列式产物 | 业务状态机 |
| DuckDB | 对 Parquet 做质量、覆盖、切片和实验汇总 | 执行生成代码；不接受不可信 SQL |
| Ray Data + Ray Jobs | 在 1–4 个 Linux 工作节点读取、批量转换、重分布和写出可信数据，并提交/观测一次性作业 | 业务规则、事实源、训练编排或安全沙箱 |
| DVC | 数据快照、流水线依赖和大型产物版本 | 训练指标浏览 |
| MLflow Tracking | 训练/评测运行参数、指标及产物引用 | 数据集事实源；不复制整份数据 |
| TRL + PEFT + Accelerate | 两配方 SFT；按事前门禁调用全参数、LoRA 或 QLoRA 中冻结的一种上游配置 | 自研优化器、方法效果矩阵、RL trainer、通用 rollout 平台、检查点格式或集群调度 |
| 外部 benchmark 官方 runner + 项目评测适配 | LiveCodeBench/DataSciBench/SQL 锚点、协议偏离和逐项输出 | 自定义排行榜、非隔离代码执行或把子集冒充完整官方分数 |
| Docker Engine + gVisor `runsc` | 固定镜像和额外用户态内核隔离 | GPU 训练；Docker 默认 `runc` 不算安全执行证据 |

### OpenBayes Training Runtime

- 当前公开价格页只确认 `1× NVIDIA RTX 5090`、32 GB 显存、40 GB 主机内存、50 GB 工作空间和
  2.9 元/小时；最多 8 张是租赁并发上限，不作为同节点多卡规格的官方证据。运行前分别记录平台
  显示的实例/资源标识、可见卡数与实际拓扑，不把总卡数乘以 32 GB 当作单个 DDP 进程可用显存。
- 每个正式运行记录 OpenBayes 资源规格、可见卡数、实际使用卡号哈希、`nvidia-smi` 输出、驱动、
  CUDA、运行时镜像标识和所有 Python 包锁定信息。若平台不暴露镜像 digest（内容摘要），保存可见
  镜像标识并明确该复现限制，不虚构 digest。
- 容器进入“运行中”后计费，直到关闭、完成或出错；启动前检查余额至少覆盖本批次预计金额和
  15% 预留，使用自动结束脚本并设置空闲关闭。余额不足导致的强制关停保存为失败运行。
- 根文件系统不保存。训练过程周期性把 adapter（适配器）检查点、日志和运行清单写到
  `/openbayes/home`；大型只读数据/模型使用 `/openbayes/input/input0-4` 绑定，避免复制工作目录。

### Capability-to-Evidence Mapping

| 目标能力 | 实现模块 | 可核验产物 |
|---|---|---|
| 代码训练数据生成与治理 | `sources/`, `generation/`, `governance/`, `dedup/` | 冻结来源、样本父子谱系、治理明细、不可变数据卡 |
| 分布式数据处理与调优 | `distributed/`, `benchmarks/` + Ray Data | 1/2/4 节点运行、算子统计、spill/shuffle、失败恢复、成本和瓶颈报告 |
| 执行验证 | `verification/` + 独立 gVisor executor | preflight、逐次编译/测试日志、资源限制、负对照结果 |
| 质量和多样性控制 | `datasets/` + DuckDB 报告 | 处理前后质量、重复率、切片覆盖、阈值校准误报/漏报 |
| 评测反馈闭环 | `evaluation/`, `feedback/` | 逐项错误 → finding → data action → 新数据版本 → 复评 |
| 数据敏感性 | `datasets/`, `feedback/` | 按来源/技能/难度/测试强度等切片的发现、解释、决策、复验 |
| RL-ready 数据与奖励治理 | `rewards/`, `verification/` | 候选输出、逐次执行、奖励分量、重放与拒绝原因；不声称发生 RL |
| 数据价值归因 | `experiments/`, `evidence/` | 同池匹配 SFT 数据、等有效词元、多种子运行、成本与置信区间 |
| 能力和泛化贡献 | 外部 benchmark runner + 受限数据工程任务环境 | 端到端任务成功、失败恢复、未见任务/数据集、效率、通用和安全护栏 |

这张映射只覆盖适合有界项目实证的部分。项目会真实实现并测量有界 Ray Data 分布式批处理，
但不会把它写成互联网、PB/EB 或组织级平台经验；Spark、多模态、互联网采集和组织级平台仍是
明确非目标。

### Evidence Journal

项目使用 `docs/evidence-journal.md` 持续记录难点、候选方案、最终选择、失败路径、验证证据、实际
结果和取舍。难点必须在发现、决策和验证时分别更新，不能留到第 12 周回忆补写；每个
user story checkpoint（用户故事检查点）必须关联一次日志复核。解决方案必须解释问题机制、现实
备选、选择标准、牺牲与未解决限制，“使用组件 X”或“修改参数 Y”本身不算取舍。没有新难点时保存
检查点回执而不是虚构证据摘要；摘要只有在相应软件、安全执行、分布式运行或训练证据真实存在后才可
从 `CANDIDATE` 升级为 `VERIFIED`。计划、预计收益、代码完成和自动化测试不得冒充真实外部运行或
模型收益。

### Data Engineering Scorecard

项目周报、最终报告和证据摘要先展示数据指标，再展示 GPU 运行和模型分数。以下指标均从不可变
清单和原始执行记录计算，分母为零时标记 `NOT_APPLICABLE`，不得填零：

| 指标 | 定义 | 价值 |
|---|---|---|
| `GovernedAcceptanceYield` | 治理接受候选数 / 全部候选数 | 解释许可、安全、质量门禁的真实损耗 |
| `UniqueVerifiedYield` | 去重后通过安全执行的唯一任务数 / 全部候选数 | 衡量每份生成成本得到多少可训练事实 |
| `VerifierMutationKillRate` | 被验证器拒绝的有效变异实现数 / 有效变异实现总数 | 防止弱测试把错误代码奖励为正确 |
| `RLReadyCoverage` | 可确定计算全部奖励分量并成功重放的候选数 / 候选总数 | 衡量数据能否供后续 RL 消费，不证明已训练 |
| `RewardReplayMismatchRate` | 重放后奖励或关键输出变化的候选数 / 重放候选数 | 暴露不可复现奖励 |
| `SliceCoverageRetention` | 发布后仍有合格样本的必需切片数 / 预声明必需切片数 | 防止清洗和去重抹掉长尾能力 |
| `LineageCompleteness` | 必填父链、哈希和版本均完整的记录数 / 应具备谱系的记录数 | 直接验收可追溯性 |
| `ClosedLoopActionClosure` | 具有数据动作、新版本和复评结果的目标 finding 数 / 目标 finding 总数 | 衡量反馈是否真的闭环 |
| `CostPer1KUniqueVerifiedTasks` | 可归属的数据生产与验证成本 / 唯一可验证任务数 × 1000 | 衡量数据生产经济性 |
| `RayScalingEfficiency_N` | N 节点吞吐 /（N × 单节点吞吐） | 衡量分布式处理收益与瓶颈 |

模型侧 `SFTSelectionLift` 只作为上述数据交付物的下游验证：它等于相同预算下
`SFT-ClosedLoop - SFT-RandomMatched` 在项目套件 `ArtifactPass@1` 上的差值；外部 benchmark
分别作为回退护栏，不参与加权。没有真实训练、公平预算和完整谱系时，该值只能标记为未验证，
不能反向覆盖数据指标。

### Canonical Lineage Key

每个可发布结论必须可解析公共键及其 claim type（结论类型）对应的专用键；相关字段为空会阻止
该结论发布，不相关字段不要求伪造：

```text
common       = git_commit + uv_lock_hash + dvc_pipeline_revision + contract_version + report_id
dataset      = dataset_id + dataset_content_hash
distributed  = data_pipeline_run_ids + scale_benchmark_id
model_effect = mlflow_run_ids + evaluation_suite_version
```

当前目录不是 Git 仓库，因此规划产物只能标记为软件设计；实施真实数据或训练运行前必须先建立
版本控制，否则 `git_commit` 无法满足端到端谱系门禁。

## Data Pipeline

1. `source freeze`：只接收 allowlist（允许清单）内、许可明确且固定 40 位提交哈希的 Python 仓库
   或本地夹具；保存文件级 SHA-256 哈希和许可快照。
2. `governance scan`：许可、明显密钥和个人可识别信息检查失败时隔离；评测套件先冻结为只读索引，
   任何直接或近似污染样本均不得训练。
3. `normalize/dedup`：保存原始哈希、Python 抽象语法树规范化哈希、token shingle（词元片段）
   MinHash 候选；MinHash 只召回候选，最终以精确 Jaccard 或 containment（包含率）判定。
4. `generate`：从受许可种子和任务模板生成“指令、上下文、答案、测试、生成元数据”候选；原始
   原始代码可作为任务生成种子，但只有形成任务—答案—验证器并通过治理后才可进入正式 SFT 池。
5. `verify`：静态检查和安全执行分开；每个样本至少执行两次。生成测试必须拒绝已知错误实现，
   否则测试强度最多为 `EXECUTION_ONLY`。
6. `slice/report`：按技能、来源、难度、长度、真实/合成、生成器、测试强度、重复簇和质量状态
   输出处理前后分布，不使用单一总分决定样本价值。
7. `publish`：整个重复簇只能进入一个 split（切分）；发布不可变 Parquet、清单、数据卡和重建入口。

## Distributed Ray Data Design

### Execution Boundary

- 业务算子实现为接收并返回 Arrow record batch（记录批）的确定性函数；本地 adapter（适配器）
  直接调用，Ray adapter 通过 `map_batches` 调用。许可、解析、哈希、质量阈值和选择策略不得在两个
  adapter 中各实现一份。
- 无状态 CPU 算子使用 task pool（任务池）；需要复用模型或扫描器初始化成本的可信算子使用固定
  actor pool（参与者池），并显式声明 CPU、内存和可选 GPU 资源。并发值只能由基准结果调整。
- MinHash signature（签名）和 band key（分带键）并行生成；按键 `repartition` 后形成候选组，
  对 hot bucket（热点桶）设置运行前阈值并隔离复核，避免二次方候选爆炸。Ray Data 只提供执行与
  shuffle，MinHash、精确相似度和簇决策仍由冻结组件和业务契约负责。
- Ray 不运行不可信代码。`verification_attempts.parquet` 由独立 gVisor 执行主机产生，Ray 只读取并
  与样本表连接；因此 Ray worker 的权限和网络状态不能被误写成安全执行证据。
- 所有输出先写到不可变 attempt 前缀；只有任务全部终态、行数/Schema/逻辑哈希通过时才写发布
  manifest。Ray 系统级任务重试上限固定为 2 次，业务异常不自动重试；每次重试和已恢复失败都写入
  `DataPipelineRun`，不得因为最终成功而删除。

### Cluster and Submission

- 开发使用 `ray.init()` 单节点模式；真实伸缩实验使用一个不参与计算的 head node（头节点）和
  1、2、4 个同构 Linux 工作节点。节点数指实际独立虚拟机或物理机，不指同机 Python 进程数。
- OpenBayes 是首选候选而非已验证的 Ray 集群产品：官方容器间通讯只足以支持试探。启动 64 GiB
  正式运行前，`cdf benchmark preflight` 必须保存每个节点的私网互达、Ray 端口、节点唯一性、
  版本/锁文件、资源同构性和共享对象存储读写 canary（哨兵）结果；失败时停止计费并换普通 Linux
  CPU 虚拟机。公网 Hypertext Transfer Protocol（超文本传输协议，HTTP）/WebSocket 映射或仅能
  SSH 不能替代该探针。
- 多节点作业用 Ray Jobs 提交，所有节点使用同一 `uv.lock`、Python、Ray 版本和运行时镜像；集群
  只开放私网所需端口，Dashboard 绑定本地接口并通过安全隧道按需查看，不直接暴露公网。
- 输入与输出使用所有节点可访问的同一对象存储或共享只读/追加式文件系统。Ray 本地磁盘只用于
  有界 spill 和临时文件，作业结束前把规范产物、原始 `Dataset.stats()`、日志和指标写回共享存储。
- Ray Dashboard 和 Prometheus（监控指标系统）用于观测，不是事实源；报告只读取带哈希的运行清单、
  算子指标 Parquet 和原始统计快照。

### Fixed-Workload Scaling Experiment

1. 从已冻结且许可明确的输入确定性回放到 64 GiB 逻辑 payload（有效载荷），为每个副本增加
   `benchmark_replica_index` 和稳定 `benchmark_sample_id`。同时记录 Parquet 物理字节和解压后的
   逻辑字节；这些记录全部标记 `BENCHMARK_ONLY`，发布与训练入口遇到该标记必须退出。
2. 固定同一输入 manifest、算子图、block size（数据块大小）、worker 的虚拟 CPU/内存、共享存储、
   Ray/Python/依赖版本和输出 Schema。工作负载覆盖读取、解析/规范化、哈希和质量特征、MinHash
   分带重分布、候选聚合、逐键确定性决策及 Parquet 写出，而不是无业务意义的 sleep/no-op。
   `C_max` 定义为四节点配置可用的最大 Ray Data map 并行槽数；固定输入 block 数不得少于
   `8 × C_max`，避免分片不足限制扩展。
3. 先运行 1 GiB 软件冒烟；正式测量按随机顺序运行 1、2、4 个工作节点，每种规模先做一次不计入
   结果的 warm-up（预热），再做 5 次测量。每次使用新 attempt 前缀并记录输入缓存策略；不得复用
   前一次物化结果。
4. `Q_N` 定义为 `N` 个工作节点时五次测量的中位逻辑 GiB/秒；`S_N = Q_N / Q_1` 为相对单节点
   speedup（加速比）；`E_N = S_N / N` 为扩展效率。五次原始轮次报告中位数、范围和 95% bootstrap
   confidence interval（自助法置信区间）；所有输出逻辑哈希必须相同。只有吞吐提升的区间排除零
   提升时才发布对应扩展收益；否则用算子级耗时、CPU、对象存储峰值、spill、shuffle、存储吞吐和
   任务 timeline（时间线）解释瓶颈并保留无加速或负加速结果。
5. 另做一次故障注入：在处理中终止一个 Ray worker 进程。只有最终输出哈希与无故障运行一致、
   重试次数可见且没有重复提交时，才可声称完成有界失败恢复；节点级灾难恢复和跨集群 checkpoint
   （检查点）不在首版声明范围。

Ray Train、Ray Tune 和 Ray Serve 不进入首版。当前训练矩阵已经由 TRL/PEFT/Accelerate 与
MLflow/DVC 管理，额外引入训练编排层只会扩大等词元和谱系的验证面；Ray 在本项目中聚焦数据
处理、资源调度、观测、故障恢复和性能分析。

## Safe Execution Design

只有满足全部条件的执行才能标记 `EXECUTION-VALIDATED`：

- 独立 Linux CPU 执行主机，固定日期/点版本和校验和的 gVisor `runsc`；主机侧 inspection（检查）
  证明实际 runtime 为 `runsc`。
- 与 RTX 5090 训练主机隔离；不共享云凭据、Docker socket、SSH 目录、宿主 home、仓库写挂载、模型
  服务密钥或缓存。
- 非 root 用户、drop all capabilities（移除全部 Linux capabilities）、`no-new-privileges`、
  禁止 privileged/host namespace/device。
- `network=none` 并运行网络 canary；根文件系统只读，输入只读，输出使用容量限制的 tmpfs。
- CPU、内存、PID、文件大小、输出大小和墙钟时间均受限；镜像用 digest 固定，运行时不下载依赖。
- 保存每次尝试的输入、输出、退出状态、资源结果和哈希；重复结果不一致标记 `FLAKY`。

Docker 默认 `runc`、本地子进程或 mock（模拟）只能提供 `SOFTWARE-VALIDATED` 证据。

## Experiment Design

### Shared Rules

有效训练词元（effective loss tokens）是实际参与损失计算且不含 padding（填充）的 response
词元。同一对比的计划值必须等于实测值。各组还必须固定初始 checkpoint、tokenizer、chat template、
上下文、全局批量、训练方法及配置、优化器、学习率、步数、数据曝光与排序、精度、单运行卡数、随机
种子和检查点间隔。不得按单组结果提前停止，也不做结果驱动的超参数搜索。

基础模型未训练检查点只作为分数背景，不是等预算因果对照；其与微调模型的差值只能描述为
“训练后的观测差异”，不能称为数据归因结果。

### Training Method Feasibility Gate

正式结果产生前，使用同一冻结小样本、相同上下文和有效训练词元口径，对全参数微调、LoRA 与
QLoRA 做有界可行性核验。该核验只回答“哪一种方法能作为低复杂度、可公平复现的测量仪器”，不
比较最终能力，也不产生训练方法优劣结论。每个候选必须记录实际可见拓扑、峰值显存、吞吐、数值
稳定性、检查点保存/重载、预计六次正式运行卡时和是否需要新增训练基础设施。

选择顺序遵循以下门禁，而不是预设 QLoRA：

1. 先拒绝任何无法在实际租赁拓扑中稳定完成反向传播和检查点重载的候选。
2. 再拒绝任何会挤占两个数据配方、三个种子、15% 重跑余量或数据工程核心里程碑的候选。
3. 再拒绝任何需要项目自研分布式 trainer、调度平台或新增正式方法矩阵的候选。
4. 多个候选均通过时，按预登记顺序选择参数更新语义最直接且总卡时可接受的方法；选择后对所有
   处理组和对照组统一冻结。全参数微调不是禁止项，但不能以缩减公平对照或扩大训练系统为代价。

门禁使用与正式 test 隔离的校准任务，不得根据正式处理组结果回选方法。未通过的方法及原因同样
保留，以形成资源约束下的工程取舍证据。

### Main SFT Data Attribution Experiment

正式实验只有两个数据配方、三个预登记种子 `[17, 29, 43]`，共六次训练运行：

| 配方 | 数据构造 | 可回答的问题 |
|---|---|---|
| `SFT-RandomMatched` | 从冻结的可验证任务—答案池随机选择，并匹配来源、任务类型、难度、长度、测试强度和基线成功率 | 反馈选择的反事实基准 |
| `SFT-ClosedLoop` | 只读取 development（开发）评测错误，按冻结策略从同一池选择；匹配字段和有效训练词元与对照相同 | `SFT-ClosedLoop - SFT-RandomMatched`：反馈驱动的数据选择是否带来增量 |

每个 task package（任务包）属于数据转换、质量修复或流水线调试之一，包含冻结输入数据、目标
schema、数据质量/业务不变量、提示、参考答案、隐藏测试、变异哨兵、验证器版本和执行策略。训练
输出只要求一次生成 Python 程序，不引入多轮 Agent 环境。最终 test（测试）集按任务模板、来源
仓库和输入数据集三重隔离，在数据选择冻结前不可见。若同池匹配、验证器区分度或等有效词元门禁
未通过，对比降为探索性结果。

### Why CPT and RL Are Not Formal Experiments

CPT 主要学习代码、库和工具的分布知识；RL 用环境反馈优化任务成功；SFT 模仿已验证的任务—答案。
三者不是可互换的训练阶段。2026 年 ToolCPT 使用 18B token 的语料规模，而代码 RL 又需要在线
rollout、奖励执行和策略稳定性控制。两者都超出本项目用于数据价值测量的最小训练需要。因此只
保留代码语料治理和 RL-ready 奖励导出的软件级演示，不运行 CPT/RL 效果矩阵，也不发布相应提升。

### Evaluation and Decision Rule

- 外部通用代码护栏：冻结 LiveCodeBench version 6 的 Python/标准输入输出执行任务与官方
  `pass@1` 语义；子集或协议改变必须写 `protocol_deviation`，不得声称完整 leaderboard 分数。
- 外部数据任务锚点：冻结 DataSciBench 中由程序规则和最终产物确定评分的 Python 子集，保留其
  Intention-Function-Code 分项；因原协议是 agent 设置且包含不确定 ground truth，本项目结果明确
  标为 deterministic subset（确定性子集）。
- 外部 SQL 锚点：冻结 BIRD 或 Spider 2.0-lite 的本地可执行子集，报告 execution accuracy（执行
  准确率）并做查询结构与内容污染探针；它不替代 Python 主指标。
- 项目主指标：`DataEngineeringArtifactBench-v1` 中第一次生成的程序只有在执行、最终数据产物、
  schema、主键、空值/类型/关联约束、业务不变量和安全限制全部通过时才计入 `ArtifactPass@1`。
- 修复能力：给定失败测试或数据质量错误时一次生成补丁的 `RepairPass@1`。
- 未见场景：任务模板、来源仓库和输入数据集三重不相交的 `HeldOutArtifactPass@1`。
- 推理成本：生成 token、墙钟时间和执行成本；只作护栏，不与成功率合成单一总分。
- 安全代码：功能测试与安全测试同时通过的 `secure_pass@1`。
- 指令遵循：严格匹配准确率。
- 诊断指标：执行成功、产物格式、各类数据断言和约束分别报告通过率，但不能替代
  `ArtifactPass@1`。
- 保存逐项预测、测试输出和切片结果；使用 paired bootstrap（配对自助法）95% 置信区间，以及
  三个种子的均值和标准差。

训练 loss 和可选 RL-ready 奖励只用于诊断，不能作为最终能力指标。只有正向均值、95% 置信区间
下界大于 0、三个种子完成、有效训练词元与其他预算相等、验证器门禁通过、无超过预登记阈值的
外部护栏回退且谱系完整时，才允许发布“该 SFT 数据选择策略提高了本项目冻结数据工程套件的
一次生成成功率”。不得外推成“提高通用代码能力”；否则报告为负向、无变化、趋势或不确定。

## Progressive GPU Budget Gate

`P` 定义为预登记时 OpenBayes RTX 5090 的实际每卡时人民币价格，当前报价 `P=2.9`；
`H_start = floor(5000 / P) = 1724` 是启动预算可购买的卡时，
`H_max = floor(10000 / P) = 3448` 是论证后允许的最高卡时。预登记运行必须保留 15% 作为失败重跑
和最终复现预算。`H_planned_start = floor(0.85 × 5000 / P)` 是启动档可规划卡时，
`H_planned_max = floor(0.85 × 10000 / P)` 是最高档可规划卡时。若校准证明核心 SFT 的两组、三个
种子或一次必要复现无法在启动档完成，可在看正式结果前提交预算例外记录。按当前报价，两个可规划
上限分别为 1465 和 2931 卡时；报价改变时必须重新计算，不能沿用这些数值。

| 阶段 | 训练规模 | 目的 | 晋级条件 |
|---|---:|---|---|
| 软件门禁 | 0 GPU | 契约、数据、命令 dry-run（试运行）、预算计算和证据降级测试 | 全部自动测试通过；无模型收益结论 |
| 兼容性冒烟 | 3B–4B 链路；8B 候选 0.25M 有效词元 | 冻结模型、CUDA、精度、显存、吞吐、checkpoint 和评测链路 | 峰值显存保留至少 10% 余量；真实参数更新；检查点可重载；谱系齐全 |
| 单种子校准 | 两配方各 1M 有效词元 | 验证同池匹配、等词元、评测灵敏度和失败恢复 | `planned=observed`；逐项评测完整；不发布正式提升 |
| 正式最低档 | `2 recipes × 3 seeds`，每运行预算由校准后冻结 | 优先保证反事实对照和重复次数 | 六个运行加 15% 余量不超过获批上限 |
| 正式目标档 | 仍为六个运行，只统一提高每运行有效训练词元 | 预算允许时提高统计分辨率 | 只能在任何正式结果可见前冻结 |

不在计划阶段虚构每个 SFT 运行的 token 数；单种子校准产出每百万有效训练词元和每个 optimizer
step 的卡时，再选择最低档或目标档。选择顺序是先保留两个配方、三个种子和公平对照，再统一增加
每运行预算。实际租到 1–8 张卡时，每卡运行一个独立作业；每批轮换配方到物理实例。

DDP、FSDP（全分片数据并行）和 ZeRO（零冗余优化器）均不进入首版正式矩阵。多卡只用于并行独立
运行，不把训练系统复杂度当作数据工程成果。

默认租卡节奏如下；卡数表示同时占用的卡，不改变每个正式运行的冻结预算：

| 阶段 | 建议卡数 | 使用方式 |
|---|---:|---|
| 软件链路与 8B 模型门禁 | 1 | 顺序完成 3B–4B 链路和 8B 单卡真实 SFT 门禁 |
| 两配方单种子校准 | 1–2 | 顺序或并行运行，冻结实际预算和停止规则 |
| 6 个正式 SFT 运行 | 2–4 | 默认 2–4 个独立单卡作业分批完成；资源稳定时最多八卡并行 |
| 评测与必要复现 | 1–4 | 按冻结运行并发，避免为推理长期保留空闲卡 |

启动预算的初始卡时封套如下；这是停止上限，不是要求花完的配额：

| 用途 | 卡时上限 | 按 2.9 元/卡时的金额上限 |
|---|---:|---:|
| 环境、3B–4B 冒烟与 8B 模型门禁 | 60 | 174 元 |
| 两配方单种子校准 | 120 | 348 元 |
| 6 个正式 SFT 运行 | 720 | 2,088 元 |
| GPU 评测与必要诊断 | 150 | 435 元 |
| 计划小计 | 1,050 | 3,045 元 |

5,000 元中的 750 元作为不可预支的 15% 失败重跑与最终复现储备，另有 1,205 元计划余额。任何阶段
实测低于上限时保留余额，不因为“尚有预算”而扩大词元或追加有利配方。

允许从 5,000 元扩支的必要理由仅限：保持已冻结的核心 SFT 对照完整、完成三个种子、替代基础设施
失败的同配置重跑，或完成至少一次独立复现。扩支必须在查看相关正式结果前记录报价、冒烟吞吐、
预计剩余运行和金额；不得用于给表现较好的配方追加训练、事后扩大预算或筛选有利种子。CPT、
RL、额外模型规模和非必要界面不构成扩支理由。

Ray CPU 集群不消耗上述 GPU 卡时封套，但不是“免费资源”。首次创建集群前必须生成独立的
`ray_budget_projection.json`，记录 head/worker 每小时价格、对象存储与网络价格、预热和 15 次正式
测量的预计节点时、停止上限及审批；运行后以账单回填实付金额。若用户决定 5,000 元覆盖全部云
资源，则该停止上限与 GPU 预算合并计算，并优先缩小每次 SFT 的有效训练词元，不削减 Ray 的
1/2/4 节点真实证据或核心 SFT 公平对照。

OpenBayes 当前公开页面只给出 CPU 资源最低 0.3 元/小时、CPU-x/xxlarge 1.1 元/小时起等展示价，
不能据此推算正式集群总价。预算文件必须保存账户实际可选资源、head/worker 规格、同时运行数量、
对象存储和网络的下单前报价；切换提供商时重新审批，不沿用旧报价。

## 12-Week Delivery Plan

| 周 | 可验证交付 | 完成门禁 |
|---:|---|---|
| 1 | 仓库初始化、`uv.lock`、Ray/模型兼容性矩阵、来源清单、研究证据台账、GPU 报价与候选门禁设计 | Ray 2.58.0 与 Python/Linux 冒烟；完成 OpenBayes CPU 容器私网/Ray 端口/共享存储探针或冻结普通 Linux 虚拟机备选；模型候选顺序、`P` 和 `H_start` 被记录；尚不声称多节点或训练兼容性已通过 |
| 2 | Pydantic/Arrow 契约、DVC 数据版本、许可明确的来源快照、本地与单节点 Ray adapter | 固定来源可重建；两个 adapter 的逻辑哈希和样本决策一致 |
| 3 | Ray 批量算子、密钥/个人信息治理、原始/语法树哈希、MinHash 分带与污染校准集 | 1 GiB 单节点 pipeline 冒烟通过；标注对的 precision/recall、误报和漏报可见 |
| 4 | 版本化生成模板、模型适配器、候选样本与父子谱系 | 固定输入重跑产生相同清单或解释的非确定性字段 |
| 5 | 静态质量、测试强度、错误实现/mutation canary | 生成测试能拒绝已知错误实现，否则不晋级 |
| 6 | Linux gVisor executor、preflight、资源/网络 canary | 正确、错误、超时、越权和不稳定样本均得到预期状态 |
| 7 | 数据切片、质量/多样性/敏感性报告；64 GiB Ray 工作负载的 1/2/4 节点各 5 次实测；冻结可验证任务池 | 数据卡与谱系完整；多节点输出等价，算子指标、失败恢复、扩展效率、瓶颈和实付成本可核验 |
| 8 | RL-ready 奖励导出与重放；TRL/PEFT 薄 SFT 适配、训练方法门禁和兼容性冒烟 | 奖励可重放但不声称 RL；只冻结一种训练方法；adapter 只消费清单并记录证据 |
| 9 | 外部 benchmark 适配与数据工程扩展评测，冻结任务模板/仓库/数据集三重不相交套件 | 外部协议偏离、基础模型逐项结果、污染审计和护栏阈值冻结 |
| 10 | 评测发现到数据动作，冻结 `SFT-ClosedLoop` 和 `SFT-RandomMatched` | 只读取开发集；反馈关系可双向追踪；同池匹配通过 |
| 11 | 在预算门禁内执行六个正式多种子 SFT 运行并评测 | 所有预登记运行、失败和成本均被记录；不启动 CPT/RL |
| 12 | 模型与 Ray 统计分析、独立重跑、负结果保留、证据清单、证据日志和项目报告 | 每条结论通过 evidence verify；难点与证据摘要链接实际证据；无真实多节点、执行或训练证据的表述分别降级 |

### Scope Cut and Budget Escalation Order

出现时间或启动预算风险时，按以下顺序处理，且不削减谱系、公平性或诚实报告：

1. 取消 64 GiB 以上的额外 Ray 压力档、模型扩展档和可视化界面；保留 1/2/4 节点核心测量。
2. 取消 RL-ready 奖励导出的非核心可视化和额外格式，但保留验证器原始执行记录。
3. SFT 从目标档降至最低档，但保留两个配方和三个种子。
4. 减少来源仓库和合成候选量，不减少污染检查、执行隔离或逐项评测。
5. 若核心 SFT 最低档和必要复现仍无法在 5,000 元内完成，按上述规则论证扩至最多约 10,000 元。

## Project Structure

### Documentation (this feature)

```text
specs/001-code-data-factory/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── artifacts.md
│   └── cli.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
pyproject.toml
uv.lock
dvc.yaml
dvc.lock
src/code_data_factory/
├── cli.py
├── contracts/
├── sources/
├── governance/
├── dedup/
├── distributed/           # 共享业务算子的本地/Ray adapter 与运行证据采集
├── benchmarks/            # BENCHMARK_ONLY 回放、伸缩与故障注入
├── generation/
├── verification/
├── datasets/
├── experiments/
├── evaluation/
├── feedback/
└── evidence/
tests/
├── unit/
├── contract/
├── integration/
└── fixtures/
configs/
├── sources/
├── quality/
├── distributed/
├── execution/
├── experiments/
└── evaluation/
schemas/                  # 由 Pydantic 契约生成的 JSON Schema
data/
├── raw/                  # DVC 跟踪，不直接进入 Git
├── interim/
├── benchmarks/           # 可重建、不得进入训练/评测
└── releases/
artifacts/
├── data-runs/
├── runs/
├── evaluations/
└── reports/
docker/
├── executor/
└── trainer/
docs/
├── ARCHITECTURE.md
└── evidence-journal.md
reports/
```

**Structure Decision**: 采用一个 Python 包和一个命令行入口。模块按证据链职责分开，所有规范数据
通过契约交接；不增加 Web 前端、微服务、工作流服务器或独立元数据服务。

## Post-Design Constitution Check

| 宪章门禁 | Phase 1 产物中的落实位置 | 复核 |
|---|---|---|
| 真实训练证据 | `data-model.md` 的 `TrainingRun`/`PublishedClaim`；`contracts/artifacts.md` 的 claim gate | PASS |
| 固定预算公平归因 | 本计划实验矩阵；`ExperimentPlan` 不可变状态和预算等式 | PASS |
| 端到端谱系 | 统一谱系键、`DataPipelineRun`、`ArtifactRef`、DVC/MLflow 职责边界 | PASS |
| 证据分级和失败关闭 | 独立的 evidence level、verification outcome、test strength 状态机 | PASS |
| 完整诚实结果 | 运行终态不可删除；报告清单覆盖失败、负向和无变化 | PASS |
| 研究资料时效 | `research.md` 的独立大模型方法证据台账 | PASS |

设计后未出现新的宪章冲突。复杂度表留空，因为没有例外需要说明。

## Risks and Controls

| 风险 | 控制与降级 |
|---|---|
| 租赁价格使估算卡时不成立 | 只以报价、实付账单和实测吞吐为准；5,000 元为软上限，必要时按门禁扩至最多约 10,000 元 |
| RTX 5090 数量波动或同节点多卡不可用 | 每张卡运行一个独立配方/种子；按实际 1–8 张分批调度；正式方案不依赖同节点多卡或 DDP |
| OpenBayes 容器互通、Ray 端口或共享写入探针失败 | 立即停止候选集群并保留探针证据；改租 1/2/4 个同构普通 Linux CPU 虚拟机。若最终只能获得单机多进程环境，SC-014 标为未满足且不声明分布式扩展 |
| Ray block 太少或 worker 未实际跨节点执行 | 固定 block 数至少为四节点最大 map 并行槽的 8 倍，保存 tasks-per-node 和节点快照；配置数不能替代实际任务分布 |
| 对象存储、shuffle 或热点桶掩盖 CPU 扩展 | 分别保存输入输出基线、spill、backpressure、shuffle 和热点桶分布；报告瓶颈及负加速，不筛选最优轮次 |
| Ray 重试导致重复或部分发布 | 稳定记录 ID、attempt 前缀、有限系统重试、业务异常失败关闭；全部完成并核对逻辑哈希后才提交 manifest |
| 32 GB 单卡显存不足或余量过小 | 在正式结果前执行全参数/LoRA/QLoRA 可行性门禁；拒绝无法保留公平对照、三个种子和 15% 余量的方法，冻结通过门禁的一种方法并统一用于全部组，不为单一配方单独降级 |
| OpenBayes 根盘或执行环境重建导致产物丢失 | 所有证据和检查点实时写入 `/openbayes/home`；只读大文件使用数据仓库绑定；每批次先验证恢复路径 |
| 余额不足导致运行被强制关停 | 启动前校验本批预计金额加 15% 余量，启用通知并保存周期检查点；关停按失败运行保留 |
| 8B 主模型处于评测地板/天花板或对小数据差异不敏感 | 在正式结果前用冻结初始模型和非正式校准集检验；失败则按冻结候选顺序替换，成功后不再换模型；允许最终得到无变化结论 |
| CPT/RL 使训练喧宾夺主 | 两者不进入正式矩阵；RL-ready 只导出可重放数据，训练适配器只支持两配方 SFT |
| gVisor 与某些测试不兼容 | 记录兼容性失败；无法安全执行则保持 `SOFTWARE-VALIDATED`，不回退到不安全执行 |
| 合成测试“自证正确” | 使用已知错误实现或确定性 mutation canary；失败则降低 test strength |
| 近似去重误杀多样性 | 在标注样本对上校准，报告 precision/recall 和切片覆盖变化；LSH 不直接作最终判定 |
| 开发集反馈泄漏测试集 | 测试仓库和索引在闭环结束前不可见；重复簇跨 split 禁止 |
| DVC 与 MLflow 形成双事实源 | Parquet/JSON/YAML 加哈希是事实源；MLflow 只保存运行索引和 artifact reference |
| MLflow 或数据工具安全漏洞 | 固定审查版本、绑定 `127.0.0.1`、禁 webhook 和不可信 pickle；升级前复核官方公告 |

## Complexity Tracking

无宪章违规需要例外。Ray 是用户明确要求且由参考需求材料支持的有界数据执行后端，复用同一业务算子
并拒绝引入 Ray Train/Tune/Serve；它不构成组织级数据平台。CPT/RL 不进入正式训练，RL-ready
产物复用现有验证记录；SFT 适配器保持最小，只作为数据价值测量仪器。
