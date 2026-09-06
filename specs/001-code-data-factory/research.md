# Research Decisions: Code Data Factory

**Research date**: 2026-09-04  
**Current large-model evidence cutoff**: 2026-04-01  
**Target environment**: Linux; OpenBayes NVIDIA GeForce RTX 5090, 32 GB per GPU, up to 8 concurrent GPUs

## Research Method and Evidence Boundary

当前大模型研究和方法方案只使用满足上述 evidence cutoff（证据截止日期）的原始论文、官方项目页
或正式发布记录。检索条件覆盖：2026 code data generation、code data selection、
execution verified code data、training data attribution、evaluation feedback 和 code sandbox。引用前
核对原始页日期、版本及是否存在更新版本；大模型方法来源访问日期为 `2026-09-03`，Ray 组件
专项复核访问日期为 `2026-09-04`。

通用 Python 和基础设施组件不使用发布日期淘汰规则。它们按当前维护状态、稳定版本、许可、
兼容性、安全记录和本项目职责重叠来选择。本文中的版本是规划基线；实施第 1 周会在 Linux 镜像
中做兼容性冒烟并由 `uv.lock`、平台运行时镜像标识和可获得的镜像 digest 固定最终组合；平台
未暴露 digest 时必须记录限制，不能用自填值冒充。

## Decision 1: Project Shape

**Decision**: 构建单人、命令行驱动、同时支持本地与 Ray Data 分布式批处理的 Python 数据工厂；
训练和安全执行是外部适配能力，不构建通用训练平台、调度平台或在线服务。

**Rationale**: 参考需求材料中与本项目最相关的是代码数据生成、治理、质量、多样性、执行验证、
评测闭环和数据价值量化。

**Alternatives considered**:

- Spark/Kubernetes：不再增加第二个分布式计算引擎或容器编排层；首版用 Ray 做有界多节点实践。
- Dagster/Prefect/Airflow：Data Version Control（数据版本控制，DVC）stage 已能表达当前批处理依赖，
  排除第一版。
- Web dashboard：静态 Markdown/JSON 报告和 MLflow 本地界面足够，排除第一版。

## Decision 2: Core Data and Lineage Stack

**Decision**: 使用 `uv + Pydantic v2 + PyArrow/Parquet + DuckDB + Ray Data/Ray Jobs + DVC +
MLflow Tracking`。

**Rationale**:

- `uv` 管理 Python、依赖解析和精确锁文件。
- Pydantic 管理单条业务记录、清单与命令输出；Arrow Schema 管理物化表，二者共享
  `contract_version`。
- Parquet 是规范化明细格式；DuckDB 直接查询 Parquet 并生成质量、切片、归因和报告聚合。
- Ray Data 负责可信数据的分块读取、批量转换、重分布和分片写出；Ray Jobs 负责向已有集群提交
  一次性作业。两者都不保存业务事实状态。
- DVC 记录数据内容、流水线依赖和大型产物；MLflow 记录单次训练/评测的参数、指标和产物引用。
- 事实源始终是有哈希的 Parquet/JSON/YAML，任何界面都不成为第二套状态。

**Component review**:

| 组件 | 规划基线 | 维护/许可与适配检查 | 采用结论 |
|---|---:|---|---|
| [uv](https://github.com/astral-sh/uv/releases) | 0.12.9 | 2026-09-01 发布；持续维护 | 采用 |
| [Pydantic](https://github.com/pydantic/pydantic/releases) | 2.13.5 | 2026-08-28 发布；MIT | 采用 |
| [PyArrow](https://arrow.apache.org/docs/python/install.html) | 25.0.1 | 2026-08-10 发布；支持目标 Python；Apache-2.0 | 采用 |
| [Parquet](https://parquet.apache.org/docs/) | 当前规范 | 跨工具列式格式 | 采用 |
| [DuckDB](https://duckdb.org/docs/stable/clients/python/overview) | 1.5.5 | 进程内查询；MIT | 采用 |
| [Ray Data](https://docs.ray.io/en/latest/data/data.html) | 2.58.0 | 2026-08-23 发布；Linux/Python 3.12 wheel 可用；Apache-2.0 | 采用并在 `uv.lock` 固定 |
| [DVC](https://github.com/treeverse/dvc/releases) | 3.67.1 | 数据版本与 stage DAG；Apache-2.0 | 采用 |
| [MLflow](https://mlflow.org/docs/latest/ml/tracking) | 3.15.2 | 运行跟踪；Apache-2.0；需执行安全加固 | 采用 |

**Alternatives considered**:

- Polars：成熟但与 DuckDB 的有界 Parquet 分析职责重叠；有性能证据后再引入。
- Pandera：表约束已由 Arrow Schema、DuckDB assertions（断言）和 Pydantic 元数据覆盖。
- Git LFS/lakeFS：前者缺少 stage 复现语义，后者超出个人项目范围。
- Weights & Biases：增加外部软件即服务依赖，不作为事实源。
- DataTrove `RayPipelineExecutor`：具备成熟分片执行和去重积木，但与 Ray Data 再形成一套 pipeline
  抽象；首版继续复用已有扫描/MinHash 组件，并只维护一个 Ray Data adapter，避免双执行语义。

## Decision 3: Code Governance and Deduplication

**Decision**: 治理链采用许可 allowlist、明显密钥和个人可识别信息阻断、Python 解析校验、三层重复
检测和冻结评测污染索引。三层为原始 SHA-256、抽象语法树规范化 SHA-256，以及 token shingle
MinHash locality-sensitive hashing（局部敏感哈希）候选加精确相似度复核。

**Rationale**: 精确哈希成本低，语法树规范化能识别仅格式/命名变化，MinHash 适合召回近似候选。
局部敏感哈希只做候选检索，最终重新计算 Jaccard 或 containment，避免把概率结构当确定证据。
整个重复簇分配到同一切分，能降低训练/评测泄漏。

**Selected components**:

- [datasketch 2.0.0](https://pypi.org/project/datasketch/) 用于 MinHash/LSH 候选检索。
- [detect-secrets 1.5.0](https://pypi.org/project/detect-secrets/) 仅在合成 canary 验证其扫描配置有效后启用。
- [Presidio Analyzer 2.2.364](https://github.com/data-privacy-stack/presidio/releases) 只使用结构化 recognizer；
  高置信结果隔离，姓名/地点等歧义项进入复核，零发现不等于无个人信息。

**Alternatives considered**:

- 自研语义去重模型：增加训练与服务复杂度，第一版排除。
- SemDeDup：项目已归档且许可不适合本项目的可复用交付，不采用。
- LLM-as-a-Judge 单独治理：不可复现且不能作为密钥、个人信息或正确性证明，不采用。
- Semgrep Community Edition：只可能在后续使用项目自有本地规则；不把零告警写成安全证明。

## Decision 4: Secure Execution

**Decision**: 在独立 Linux CPU 主机使用 Docker Engine 固定镜像和 gVisor `runsc` 的 `systrap`
平台。必须通过主机侧 preflight、网络/权限 canary、资源限制和重复执行后，样本才可能成为
`EXECUTION-VALIDATED`。

**Rationale**: Docker 解决镜像和资源约束，但默认 `runc` 仍共享宿主内核；gVisor 增加用户态内核
隔离。gVisor 官方在 2026 年的 agentic reinforcement learning（智能体强化学习）沙箱材料也明确
把不可信生成代码的隔离作为实际应用场景。训练 GPU 主机不执行不可信代码，避免云凭据、模型
服务密钥、Docker socket 或设备被样本触达。

**Alternatives considered**:

- Docker + `runc`：只给软件级验证，不给安全执行级证据。
- Firecracker：隔离更强，但镜像、内核和虚拟机生命周期会挤占 12 周主线；保留为未来加固。
- nsjail：作为 gVisor 不兼容时的研究候选，不在第一版形成第二执行后端。
- 本地 subprocess：不具备安全边界，禁止执行不可信样本。

**Primary sources**: [gVisor platform documentation](https://gvisor.dev/docs/user_guide/platforms/),
[gVisor installation](https://gvisor.dev/docs/user_guide/install/),
[gVisor 2026 blog index](https://gvisor.dev/blog/),
[Docker security](https://docs.docker.com/engine/security/),
[Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/).

## Decision 5: Quality Verification Stack

**Decision**: Python 质量基线使用 Ruff、pytest、coverage.py 和仅覆盖核心契约/状态/runner 接口的
mypy。生成测试必须提供 negative control（负对照）：已知错误实现或确定性变异必须被拒绝。

| 组件 | 规划基线 | 用途 |
|---|---:|---|
| [Ruff](https://pypi.org/project/ruff/) | 0.16.5 | 格式、lint 和可重复静态规则 |
| [pytest](https://pypi.org/project/pytest/) | 9.1.1 | 单元、契约、集成和样本测试 |
| [coverage.py](https://pypi.org/project/coverage/) | 7.16.0 | 覆盖证据，不把覆盖率当正确性 |
| [mypy](https://pypi.org/project/mypy/) | 2.3.1 | 核心边界类型检查 |

**Rationale**: 这些组件覆盖工程质量和测试强度，同时不自研代码分析器。编译、测试执行、覆盖记录
和负对照拒绝是不同证据，使用正交字段保存，不能折叠为一个 `verified=true`。

## Decision 6: Training Stack and Model Boundary

**Decision**: 使用 Hugging Face TRL 的 `SFTTrainer`、PEFT 和 Accelerate，底层使用
Transformers/PyTorch；薄适配层只支持两个数据配方的 SFT。全参数微调、低秩适配
（Low-Rank Adaptation，LoRA）和量化低秩适配（Quantized LoRA，QLoRA）进入事前可行性门禁，
正式矩阵只冻结一种方法，不做方法效果比较。每个运行使用一张 RTX 5090，按租赁时实际可获得的
1–8 张卡并行不同配方/种子；首版不使用 Distributed Data Parallel（分布式数据并行，DDP），也不
实现 RL trainer 或 rollout 服务。

**Rationale**: 项目目标是测量数据选择而不是自研训练器。预选 QLoRA 会把尚未实测的显存假设写成
既定方案；相反，事前门禁用真实反向传播、峰值显存、数值稳定性、检查点重载和六次运行成本选择
一个统一方法。这样允许 LoRA 或资源可行时的全参数微调，同时避免把三种方法扩展成训练研究矩阵，
把复杂度留给任务生成、验证器、治理、Ray 处理、匹配和谱系。

**Model decision**: 第一核验顺位采用 [`Qwen/Qwen3-8B`](https://huggingface.co/Qwen/Qwen3-8B) 的
Instruct checkpoint，正式使用前重新核验官方模型卡、精确 revision、许可、chat template 和工具
调用格式。它位于足以避免 3B–4B 容量地板、又可在 32 GB 单卡上做量化策略更新/推理校准的区间。
正式选择以基线任务成功率、真实参数更新、显存余量、保存和重载成功为门禁；
3B–4B 只作链路冒烟，27B 不进入首版。

第二候选是 [`Qwen/Qwen2.5-Coder-7B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)。
它的优势是代码域先验和指令遵循更强；风险是简单任务接近天花板，使小规模数据差异更难测。因此
只有第一候选的兼容性、显存或基线灵敏度门禁失败时才启用，而不是根据正式分数择优。

**Memory estimate**: 8.2B 参数的 BF16 权重下限约为 `8.2 × 2 = 16.4 GB`；32 GB 单卡理论上只剩
约 15.6 GB 容纳激活、梯度、优化器状态、CUDA workspace（工作区）和碎片。这只是容量估算，不是
可运行证据。因此三种方法都从 2,048 词元、微批量 1 和相同校准样本开始；峰值超过实测可用显存
90%、出现非有限 loss、无法保存/重载或使六次正式运行超预算，都判为失败。不能因为仅完成前向
推理就宣称训练兼容。

[`Qwen/Qwen3.5-9B-Base`](https://huggingface.co/Qwen/Qwen3.5-9B-Base) 不作主候选：官方模型卡把它
标为带 Vision Encoder（视觉编码器）的因果语言模型，会把多模态依赖带入明确排除的范围；它更
“新”不是覆盖范围门禁的理由。

**Alternatives considered**:

- LLaMA-Factory：成熟且功能丰富，但额外配置语义不利于把有效训练词元等式做成一等契约。
- 自研 PyTorch loop：不增加本项目的数据工程验证价值且增加复现风险，排除。
- 全参数训练：允许参加可行性门禁；若需要新增分布式训练平台、削减三个种子或挤占数据工程交付，
  即使理论上可运行也拒绝。它不与 LoRA/QLoRA 形成效果矩阵。
- BF16 LoRA：无权重量化，若真实显存、稳定性和成本门禁通过，可以成为正式统一方法。
- QLoRA：作为显存受限候选，不再预设为默认；必须核验 bitsandbytes 内核兼容性和检查点重载。
- DDP/FSDP/ZeRO：扩大实现和验证面，且不解决本项目的 RL 数据问题，首版排除。

**OpenBayes platform decision**: 当前公开按量价是 2.9 元/RTX 5090 卡时，价格页只确认单卡实例；
最多 8 张来自用户确认的租赁并发上限，不推断为同节点多卡规格。正式运行采用 Python 脚本执行；
仓库、环境、日志、检查点和清单写到持久目录 `/openbayes/home`，冻结数据和基础模型以只读方式绑定
到 `/openbayes/input/input0-4`。容器根文件系统不作为产物位置。运行前验证余额、资源形态、显存、
驱动、两个角色之间的网络/同步和恢复路径；NVIDIA 官方规格明确 RTX 5090 不支持 NVLink，不能
预设跨卡训练或同步具有线性加速。

**Platform sources**: [OpenBayes resource pricing](https://openbayes.com/gear/),
[NVIDIA RTX 5090 specifications](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/),
[PyTorch DDP](https://docs.pytorch.org/docs/stable/notes/ddp.html),
[PyTorch FSDP](https://docs.pytorch.org/docs/stable/fsdp.html),
[compute billing and usage](https://openbayes.com/docs/quota-and-usage/),
[container storage persistence](https://openbayes.com/docs/gear/storage-persistence/),
[container execution model](https://openbayes.com/docs/gear/),
[uv environment persistence](https://openbayes.com/docs/gear/uv/).

## Decision 7: Simple SFT Attribution and Target Capability

**Decision**: 不再把“通用代码生成分数”作为项目的能力目标，也不运行正式 CPT/RL 矩阵。主能力
是模型在受约束数据工程任务中一次生成 Python 转换或修复程序的端到端成功率；只有最终数据产物、
隐藏断言和任务约束全部通过才成功。正式比较是三个固定种子下的
`SFT-ClosedLoop - SFT-RandomMatched`。

两组必须来自同一个可验证任务—答案池，并匹配来源、任务类型、难度、输入规模、测试强度和基线
模型成功率。初始 checkpoint、有效训练 token、更新步数、数据曝光/排序、优化设置、验证器、解码
和评测完全相同，唯一目标差异是是否按 development 失败模式选择数据。

**Rationale**:

- CPT 学习代码、库和工具的分布知识；RL 用环境反馈优化任务成功；SFT 模仿已验证答案。三者不是
  二选一，但项目必须选择可在 12 周内以最少训练变量归因的一层。
- 2026 年代码 RL 研究显示执行奖励与代码能力相关，同时也暴露二元奖励稀疏、弱测试和选择器漂移
  会诱发捷径或负收益。这正是正式实验不用 RL 的理由；项目保留任务、verifier（验证器）、奖励和
  失败数据的 RL-ready 导出，以展示数据工程能力，但不承担 RL 系统复杂度。
- 以最终数据产物和隐藏不变量判定一次生成是否成功，比通用代码分数、文本相似度或单个单元测试
  更贴近数据工程任务；它还能把安全执行、质量治理、Ray 数据处理和反馈闭环连接成一个垂直切片。
- ToolCPT 使用 18B token 的语料，说明 CPT 可以强化工具知识，但该量级不能由个人 5,000–10,000 元
  预算严谨复现。把小 CPT 做成正式结论既统计功效不足，也会稀释项目的数据工程主线。

**Current large-model method evidence**:

| 来源 | 可验证日期 | 支持的方案点 | 更新/替代检查 |
|---|---|---|---|
| [CodeEvo, ACL 2026](https://aclanthology.org/2026.acl-long.438/) | 2026-07 | 代码训练数据应随模型反馈演化，支持反馈闭环方向 | ACL Anthology 正式版本；未发现同题更新正式版本 |
| [ScaleBox, ACL 2026](https://aclanthology.org/2026.acl-demo.30/) | 2026-07 | 生成代码执行需要可扩展、隔离的 sandbox 证据 | ACL Anthology 正式版本；与 gVisor 官方实现文档交叉核对 |
| [The Data Frontier, ACL 2026 Tutorial](https://aclanthology.org/2026.acl-tutorials.2/) | 2026-07 | 数据选择、质量和归因应形成完整研究对象 | ACL Anthology 教程正式版本 |
| [Step Length Confounding, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.918/) | 2026-07 | 控制长度/词元等混杂因素 | ACL Anthology 正式版本 |
| [From Selection to Refinement, ACL 2026](https://aclanthology.org/2026.acl-long.1889/) | 2026-07 | 不只选择数据，还要把评测发现映射到精炼动作 | ACL Anthology 正式版本 |
| [IGDS, ACL 2026](https://aclanthology.org/2026.acl-long.283/) | 2026-07 | 数据选择策略需要用真实训练效果验证 | ACL Anthology 正式版本 |
| [Demystifying Data Organization, ACL 2026](https://aclanthology.org/2026.acl-long.1262/) | 2026-07 | 数据排序、局部多样性和课程连续性也会影响 SFT/CPT，应固定或记录顺序 | ACL Anthology 正式版本 |
| [EVO-Curate, ACL 2026](https://aclanthology.org/2026.acl-long.505/) | 2026-07 | 动态难度与多样性调度支持把训练反馈作为数据选择信号 | ACL Anthology 正式版本 |
| [CoEvolve, ACL 2026](https://aclanthology.org/2026.acl-long.1055/) | 2026-07 | 用失败与不确定性反馈合成并验证新任务，支持闭环但不复制论文收益 | ACL Anthology 正式版本 |
| [Beyond Quantity, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.768/) | 2026-07 | 代码轨迹多样性可比单纯扩量更有价值，支持覆盖与多样性对照 | ACL Anthology 正式版本 |
| [ToolCPT, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.776/) | 2026-07 | 代码与工具知识 CPT 有研究价值，但其 18B 词元规模不能直接搬到个人预算 | ACL Anthology 正式版本 |
| [CODERL+, ACL 2026](https://aclanthology.org/2026.acl-long.164/) | 2026-07 | 仅靠最终二元测试奖励存在语义与信用分配缺口，奖励需要执行语义支撑 | ACL Anthology 正式版本 |
| [ExecVerify, ACL 2026](https://aclanthology.org/2026.acl-long.631/) | 2026-07 | 可验证的中间执行状态和分难度数据可支撑 RL，并把执行推理迁移到生成 | ACL Anthology 正式版本 |
| [Powering Verifiable Learning, ACL 2026](https://aclanthology.org/2026.acl-long.1099/) | 2026-07 | 可泛化 RL 依赖问题、候选解和验证产物的联合生成与严格可验证性 | ACL Anthology 正式版本 |
| [Feedback-Driven Tool-Use, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.109/) | 2026-07 | 自动构建环境、轨迹数据和可验证任务完成奖励支持工具使用 RL | ACL Anthology 正式版本 |
| [AgenticQwen, ACL Industry 2026](https://aclanthology.org/2026.acl-industry.37/) | 2026-07 | 工业工具使用模型使用多轮 RL 与错误驱动的数据飞轮，支持任务级而非代码文本级目标 | ACL Anthology 正式版本 |
| [ZeroCoder, arXiv](https://arxiv.org/abs/2604.07864) | 2026-04 | 自生成代码/测试可支持 RL，但固定 selector 也可能降低代码生成表现，要求跟踪选择器漂移 | arXiv 原始论文；未作为已复现项目收益 |

这些论文只支持方案方向，不把论文收益复制成项目结果。项目自己的每个提升结论仍必须完成真实
训练、公平对照和逐项评测。

## Decision 8: Evaluation and Statistics

**Decision**: 评测采用分层套件，不再让一个完全自建的 `TaskSuccess@1` 承担全部说服力：

| 层 | 冻结对象与标准指标 | 在本项目中的角色 | 边界 |
|---|---|---|---|
| 外部通用代码 | LiveCodeBench version 6 的 Python/标准输入输出执行任务，`pass@1` | 当前代码功能保持护栏；证明模型没有只适配项目格式 | 固定官方 release、生成协议和隐藏测试；如果只能运行子集，必须标为 subset，不能宣称完整 leaderboard 分数 |
| 外部数据任务 | DataSciBench 中能够以程序规则和最终执行产物确定评分的 Python 数据任务，保留 Intention-Function-Code 分项 | 数据中心任务的外部设计锚点与错误分类参考 | 原 benchmark 是 agent benchmark 且部分 ground truth 不确定；首版只适配确定性子集并发布 protocol deviation，不伪装为官方总分 |
| 外部 SQL | 冻结 BIRD 或 Spider 2.0-lite 的可本地执行子集，使用 execution accuracy（执行准确率） | 覆盖 schema linking、值落地和未见数据库泛化 | 主要是 SQL，不替代 Python 数据产物主指标；必须做结构与内容污染检查 |
| 项目主套件 | `DataEngineeringArtifactBench-v1`，使用一次生成 `ArtifactPass@1` | 固定预算数据归因的主指标 | 明确标为项目扩展；只填补外部 benchmark 未覆盖的数据质量与业务不变量，不与外部分数合成 |

`ArtifactPass@1` 的分子是第一次生成的程序同时满足执行成功、最终数据产物格式、schema、主键、
空值/类型/关联约束、任务业务不变量和安全限制的任务数，分母是本次冻结套件的全部有效任务数。
另报告 `RepairPass@1`、任务模板/来源仓库/输入数据集三重不相交的
`HeldOutArtifactPass@1`、逐类断言通过率、执行成本和安全结果；诊断分项不能替代主指标，也不合成
人为加权总分。

**Current evidence after 2026-04-01**:

- [DataSciBench, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.181/) 在 2026-07
  发布，使用自然且具挑战的数据科学任务、半自动加人工核验的 ground truth，以及
  Intention-Function-Code 框架对执行结果做指标和程序规则评测，说明当前数据任务评测已经超出
  单一函数单测；它的 uncertain ground truth 也正是本项目只取确定性子集的原因。
- [CollabCoder, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.1393.pdf) 使用当时最新的
  LiveCodeBench version 6，并明确把最终代码交给官方隐藏测试执行；
  [ReflexiCoder, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.1872/) 同时报告
  HumanEval(+)、MBPP(+)、BigCodeBench 和 LiveCodeBench，支持把 LiveCodeBench 作为当前通用代码
  护栏，而不是把旧 HumanEval 单独当作主结论。
- [VET, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.1544/) 在 BIRD 和
  Spider 2.0-lite 上报告执行准确率，并通过真实数据库中间结果验证 SQL 推理；
  [SPENCE, ACL 2026](https://aclanthology.org/2026.acl-long.926/) 指出自然语言到 SQL benchmark 的
  查询及结构相似污染会夸大准确率，因此 SQL 层必须保存污染探针和受影响指标隔离。
- [SWE-AGILE, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.868/) 与
  [CodeFlowBench, ACL 2026](https://aclanthology.org/2026.acl-long.201/) 证明 SWE-bench Verified、
  仓库级和多轮 codeflow 仍是前沿评测方向；但它们要求 agent scaffold、多轮上下文或仓库环境，
  会改变本项目的一次生成 SFT 测量对象，因此只记录为首版范围边界，不进入六次正式评测。

**Rationale**: 外部层提供当前研究可比性，项目层提供真实数据工程任务所需而通用代码 benchmark 缺少的
数据产物、质量约束和业务不变量。两层分别报告可以避免自建指标自说自话，也避免为了跑 SWE agent
benchmark 把第一版扩展成 agent/RL 项目。每个数据配方比较报告三个种子的均值/标准差和 paired
bootstrap 95% 置信区间；区间跨 0 时报告趋势或不确定。

**Alternatives considered**:

- 只看训练 loss：不能证明代码能力或泛化。
- 只用 LLM judge：不能替代可执行测试。
- 只用 HumanEval/MBPP 等公开函数题：2026 前沿研究仍会报告它们，但通常与 LiveCodeBench、
  BigCodeBench 或仓库级任务共同使用；单独使用无法支撑本项目的数据工程能力目标。
- 完整 SWE-bench/CodeFlowBench：外部说服力强，但 agent scaffold、多轮推理和仓库环境会使训练与
  推理工程喧宾夺主，首版排除。
- 只用 DataSciBench 官方总分：部分任务 ground truth 和评分并非纯确定性，且原协议是 agent 设置；
  首版只发布可重放确定性子集及协议偏离。
- Shapley value：运行数超过预算且需要更强可加性假设，排除；切片归因最多预登记三个切片，
  先单种子探索，再对最有希望的一项做三种子 `WithSlice - ReplaceSlice` 确认。

## Decision 9: Budget and Progressive Scaling

**Decision**: 人民币 5,000 元是 GPU 启动软上限。当前 OpenBayes 报价 `P=2.9` 元/卡时，
使用预登记时的报价快照和实测吞吐计算可运行档位，
先做 0.25M 有效词元兼容性冒烟，再做两组各 1M 的单种子校准，最后按每百万有效训练 token 的
实测卡时预登记六个正式 SFT 运行。只有为保持核心 SFT 公平对照、三个种子、
基础设施失败重跑或必要复现，
且在查看相关正式结果前记录理由时，才可扩至最多约 10,000 元。

**Rationale**: 按当前报价，5,000 元可购买 1724 卡时，10,000 元可购买 3448 卡时；扣除 15%
预留后最多分别规划 1465 和 2931 卡时。RTX 5090 的市场可用量和报价仍可能变化，最多八卡只是
公开实例并发上限。
用金额、真实账单、每百万有效词元卡时和 15% 失败余量控制支出，能在不猜价格或拓扑的情况下
保持实验公平。优先保留对照和三个种子，然后才增加每次运行数据量。扩支不能用于追逐正向结果。

**Alternatives considered**:

- 直接运行 120M 或更大总词元：跳过兼容性和灵敏度验证，容易浪费预算。
- 只跑一个大规模种子：无法区分随机波动，不满足正式提升结论。
- 用模拟吞吐和云价替代账单：只能用于草案，不进入最终成本证据。

## Decision 10: Security and Operational Boundaries

**Decision**: MLflow 只绑定 `127.0.0.1`，使用本地 SQLite 与文件产物，不启用 webhook 或共享模型
注册服务，不加载不可信 pickle。DuckDB 只执行仓库控制的参数化 SQL，扩展采用 allowlist。DVC
凭据只存在环境变量或用户配置，不提交仓库。

**Rationale**: 本地组件也有进程权限和服务端攻击面，不能把“只在个人项目使用”当作安全控制。
MLflow 官方 2026 安全公告要求当前版本和部署方式进入组件审核；DuckDB 本身不是不可信代码或
SQL 的沙箱。

**Primary sources**: [MLflow security advisories](https://github.com/mlflow/mlflow/security),
[MLflow SSRF advisory](https://github.com/mlflow/mlflow/security/advisories/GHSA-7gwp-5pfp-969j),
[DuckDB security policy](https://github.com/duckdb/duckdb/security),
[DVC security status](https://github.com/treeverse/dvc/security).

## Decision 11: Ray Data Distributed Processing and Scaling Evidence

**Decision**: 固定 `ray[data,default]==2.58.0` 为规划基线，用 Ray Data 作为代码数据批处理后端，
用 Ray Jobs 向已有 Linux 集群提交作业；保留调用同一业务算子的本地 adapter 作为小数据正确性
基线。不引入 Ray Train、Ray Tune 或 Ray Serve。

**Rationale — official facts**:

- [Ray 2.58.0 release](https://github.com/ray-project/ray/releases/tag/ray-2.58.0) 于
  2026-08-23 发布；当前文档与 Python Package Index（Python 包索引，PyPI）提供 Linux/Python
  3.12 构建。通用组件不受大模型研究日期门槛限制，但这仍提供当前维护状态证据。
- [Ray Data key concepts](https://docs.ray.io/en/latest/data/key-concepts.html) 说明 `Dataset` 以 block
  （数据块）为分布式处理单位，使用惰性与 streaming execution（流式执行）；`sort`、`groupby`
  等全局 shuffle 会形成物化屏障。
- [Ray Data transformations](https://docs.ray.io/en/latest/data/transforming-data.html) 支持在
  `map_batches` 中用 `TaskPoolStrategy` 限制无状态任务池、用 `ActorPoolStrategy` 复用有状态昂贵
  初始化。首版使用 `batch_format="pyarrow"`；不使用已弃用的 `concurrency` 参数。
- [Ray Data internals](https://docs.ray.io/en/latest/data/data-internals.html) 说明 block 位于分布式对象
  存储，执行器根据资源与 backpressure（背压）调度上下游；流式执行允许处理超过集群内存的数据，
  但不能消除 shuffle 的内存与通信成本。
- [Ray Data monitoring](https://docs.ray.io/en/latest/data/monitoring-your-workload.html) 提供进度、
  Dashboard、日志、`Dataset.stats()` 和按 dataset/operator（数据集/算子）标记的 Prometheus 指标；
  dataset 级累计行数不能直接当端到端吞吐，最终算子输出才是口径。
- [Ray Data performance guidance](https://docs.ray.io/en/latest/data/performance-tips.html) 明确对象存储
  工作集超限会 spill 到磁盘，并可能显著变慢；因此 spill、block、batch 和 shuffle 必须实测，
  不能把“无内存溢出”写成已完成性能优化。
- [Ray Core task fault tolerance](https://docs.ray.io/en/latest/ray-core/fault_tolerance/tasks.html) 会对
  worker 或机器异常导致的系统任务失败做有限重试，但普通用户代码异常默认不重试。这不是业务
  exactly-once（精确一次）语义。

**Project mapping and evidence boundary**:

- [OpenBayes container communication](https://openbayes.com/docs/gear/internal-ssh/) 证明同一创建人的运行中
  容器可通过私有 `10.x` Internet Protocol（互联网协议，IP）地址和 Secure Shell（安全外壳协议，
  SSH）互通；[execution model](https://openbayes.com/docs/gear/) 同时说明
  每次执行是独立容器、工作目录按执行保存或绑定。官方文档没有直接承诺 Ray 的全部端口、IP 在
  完整基准期间稳定或并发容器共享可写文件系统。因此 OpenBayes CPU 容器只作为首选候选：通过
  私网端口、实际 Ray 任务分布和共享对象存储读写探针后才能用于正式多节点证据，否则切换普通
  Linux CPU 虚拟机。[Resource page](https://openbayes.com/gear/) 的 CPU 展示价只作候选估算，正式
  预算使用账户下单前报价。
- 无状态解析、哈希、质量特征和过滤用 Arrow batch + task pool；需要复用可信模型/扫描器的阶段
  才使用 actor pool。worker 内不得再启动全机大小的进程池，避免嵌套并行超卖 CPU。
- MinHash signature 和 band key 可并行生成并按键重分布；Ray 只提供执行和 shuffle，局部敏感
  哈希参数、热点桶控制、精确复核、连通簇与保留策略仍由项目组件及契约负责。
- 真实多节点证据使用不参与数据计算的 head node 加 1、2、4 个同构工作节点；单机 `ray.init()`
  多进程只标记软件级兼容性。`C_max` 定义为四节点配置的最大 map 并行槽数；输入 block 数固定为
  至少 `8 × C_max`，避免“配置了 4 个 worker，实际却没有足够可并行 block”。8 倍是本项目的实验
  余量，不是 Ray 官方硬性要求。
- 规模输入从冻结来源确定性回放为 64 gibibyte（吉比字节，GiB；`2^30` 字节）逻辑有效载荷，
  明确 `BENCHMARK_ONLY`，报告物理存储和
  解压逻辑字节，且不得进入训练、开发或测试。其目的是暴露调度、背压、spill、shuffle、倾斜和
  存储瓶颈，不是伪造真实语料规模。
- 1、2、4 节点各做一次预热和 5 次随机顺序测量，保存原始轮次、`Dataset.stats()`、节点分布、
  吞吐、墙钟时间、CPU、worker heap、对象存储、spill、shuffle、backpressure、重试和成本。
  不预设没有 pilot 支撑的线性加速阈值；只有正确性完全等价、任务真实分布到多节点且吞吐变化
  超过不确定区间时，才发布对应的扩展收益，否则发布瓶颈和负结果。
- Ray Data checkpoint 仍按当前 beta 能力看待，首版只做可选实验；稳定 `sample_id`、阶段 manifest、
  attempt 前缀、逻辑内容哈希和原子发布门禁仍是恢复与幂等基础。不得声称外部副作用具有
  exactly-once。
- 不可信代码继续只在独立 gVisor 主机运行；Ray 只能汇合其结构化结果。完成 Ray 作业与完成安全
  执行、真实训练或数据带来模型提升之间不存在自动证据晋级。

**Alternatives considered**:

- 只保留本地批处理：可作正确性基线，但不能展示多节点调度、重分布和资源调优。
- 直接使用 Ray Core tasks/actors：需要自行实现 block、流式背压和读写连接，超出需求。
- 同时引入 Spark：扩大 12 周验证面，且本轮没有公平横向基准，不能宣称 Ray 优于 Spark。
- Ray Train：解决分布式训练 worker 和 checkpoint，不是本项目的数据处理缺口；现有
  TRL/PEFT/Accelerate 的固定预算矩阵继续保持单一训练路径。

## Resolved Unknowns

| 原未知项 | 已决策结果 |
|---|---|
| 开发和运行平台 | Linux |
| GPU 平台、显存和数量 | OpenBayes NVIDIA GeForce RTX 5090，单卡公开规格 32 GB；最多并发 8 张，是否同节点必须租机后确认 |
| GPU 当前报价 | 2.9 元/卡时；5,000 元对应 1724 卡时，10,000 元对应 3448 卡时；正式计划前重新保存报价快照 |
| 训练形态 | 两配方、三种子的薄 SFT 数据归因；不做正式 CPT/RL，RL-ready 数据只作软件级产物 |
| 预算 | GPU 启动软上限 5,000 元；必要性论证后最高约 10,000 元；卡时由报价和实测反推 |
| 主语言 | Python 3.12 优先，兼容性门禁失败时全局统一 3.11 |
| 编排 | CLI + DVC stage，不引入服务型 orchestrator（编排器） |
| 分布式数据处理 | Ray Data 2.58.0 规划基线；本地正确性路径 + 1/2/4 同构 Linux 工作节点实测；优先探测 OpenBayes CPU 容器，端口/任务分布/共享存储探针失败则使用普通 Linux CPU 虚拟机；Ray Jobs 只提交一次性作业 |
| 安全执行 | 独立 Linux CPU 主机 + gVisor；不可用则软件级降级 |
| 数据和运行事实源 | 有哈希的 Parquet/JSON/YAML；DVC 管数据，MLflow 管运行索引 |
| 正式模型与实验规模 | 第一候选 Qwen3-8B Instruct checkpoint；3B–4B 仅冒烟；先校准，再冻结六个 SFT 运行的统一有效训练词元预算 |
