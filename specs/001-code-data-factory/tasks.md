---
description: "Dependency-ordered implementation tasks for Agent trajectory data engineering, specification 2.0"
---

# Tasks: Agent 工具调用轨迹数据工厂

**Revision**: 2.0 | **Created**: 2026-09-08 | **Status**: Ready for implementation；全部任务尚未执行。
**Input**: [spec.md](spec.md)、[plan.md](plan.md)、[research.md](research.md)、
[data-model.md](data-model.md)、[contracts/](contracts/)、[quickstart.md](quickstart.md)，均为规格 2.0。
**Prerequisites**: 阅读项目宪章 3.0.2、上述设计、任务所属契约，以及可用时的本机私有决策记录（不提交）。
本文件替换旧代码任务清单，旧版本任务编号不可当作本版完成证据；历史日志中的编号按当时版本解释。

## Format and Execution Rules

- 任务采用 `- [ ] T编号 [P可选] [US编号] 描述与路径`。US 表示用户故事，P 表示明确列出的并行波次。
  数字是默认执行顺序；每项显式依赖优先，满足依赖的独立分支可以提前执行。
- 功能需求 FR、成功标准 SC 的编号均指规格 2.0。最小可行版本称 MVP；SFT 为监督微调，RL 为
  强化学习；CPU 为中央处理器、GPU 为图形处理器，GiB 为 2^30 字节的吉比字节。
- 测试任务来自规格中明确要求的契约、失败处理、公平性和验收场景；先验证失败原因，再实现并重跑。
  不为简单文档或原样上游包装添加逐行镜像测试，不复制开源组件已有的算法测试。
- 复用 Ray Data、datasketch、smolagents、TRL/PEFT、DVC、MLflow、DuckDB 和官方 BFCL 评测。
  仅实现任务语义、数据适配、质量/选择、验证断言与证据；禁止另造 Agent 循环、训练/调度平台或索引算法。
- 每项包含业务验证或实际运行的任务须保存输入/配置版本、结果、失败与产物引用。运行任务只有在
  指定验收通过后才勾选；依赖缺失时记录未完成，不能用软件替身、旧日志或计划结果代替。
- 所有数据集发布均指本地不可变产物提交；不授权上传外部平台或 Git 提交。外部采样/租机必须已有
  资源授权、报价和冻结停止上限；任务清单本身不增加现金授权。
- 本版不再展开正式 RL 优化；接口/真实采样/长程/稀疏奖励兼容必须完成，不能降为可选。

## Path Conventions

一个 Python 包 `src/code_data_factory/`；命令入口 `src/code_data_factory/cli.py`，命令名称为 `cdf`。
测试在 `tests/{unit,contract,integration,fixtures}/`，配置在 `configs/`，数据在 `data/`，运行证据在
`artifacts/`，报告在 `reports/`。这些为待创建路径，当前不存在并不表示任务已经完成。
通用事实由契约表和带哈希产物保存；索引/报告从事实重建。共享文件的编辑按依赖串行，`[P]` 不允许
同时修改 `cli.py`、依赖锁、共享契约或证据日志。

## Phase 1: Setup

**Purpose**: 最小包、可重复依赖和开发检查；不创建空平台或占位业务成功结果。

- [X] T001 创建 Python 3.12 包和 `cdf` 入口声明于 `pyproject.toml`、`src/code_data_factory/__init__.py`，分离数据、交互、训练依赖组；用 `uv` 管理，不预建空服务或通用基类。（依赖：无）
- [X] T002 [P] 在 `ruff.toml`、`mypy.ini`、`tests/conftest.py` 配置静态检查与临时目录测试约定，区分离线契约和需真实资源的测试标记。（依赖：T001）
- [X] T003 [P] 按 research 的组件门禁解析正式版本并生成 `uv.lock`、`artifacts/dependencies/dependency_manifest.json`，记录官方版本/许可/安全审查及 Linux 安装读写探针；若缺 Linux 只留未完成记录，不把本机安装当通过。远端恢复遵守[租用 Linux 环境恢复与依赖验证契约](contracts/rented-environment-recovery.md)。（依赖：T001）
- [X] T004 初始化 DVC 的项目元数据 `.dvc/config`、`.dvcignore` 和 `.gitignore`，保护 `.private/`、`.codex/`、原料、模型与日志；验证现有忽略规则不被覆盖，数据/运行事实不依赖远程服务。（依赖：T002、T003）

**Checkpoint**: 包与依赖可重现，离线测试入口可用；尚不声称数据、采样或训练完成。

## Phase 2: Foundational Contracts

**Purpose**: 多个故事共享的最小实体、事实保存和资源门禁；不把全部业务塞入基础层。

- [X] T005 在 `tests/fixtures/contracts/` 建立手写正确/错误记录，覆盖独立任务、多轮尝试、调用乱序/缺失、未知判定、旧主版本和私有参考；在 `tests/contract/test_core_records.py` 声明预期拒绝规则。（依赖：T004）
- [X] T006 在 `src/code_data_factory/contracts/tasks.py` 定义来源、产物引用、任务包、能力声明与切分组的 Pydantic 模型，约束任务独立于示范、来源/模板根和模型可见/验证私有资源分离。（依赖：T005）
- [X] T007 在 `src/code_data_factory/contracts/trajectory.py` 定义 Attempt、事件、上下文和依赖边，区分 attempt_id/model_call_id，保留 MODEL_GENERATION 等五类执行者及不完整中断尾部。（依赖：T006）
- [X] T008 在 `src/code_data_factory/contracts/verification.py`、`src/code_data_factory/contracts/schema_export.py` 定义独立验证/奖励、证据层级和 Arrow 模式导出至 `schemas/2.0.0/`，确保封存尝试不回写 outcome，未知奖励不填零。（依赖：T007）
- [X] T009 在 `src/code_data_factory/contracts/artifacts.py` 实现规范序列化、物理/逻辑哈希、产物引用检查及原子清单提交；用 `tests/contract/test_artifact_integrity.py` 验证篡改、重入和半提交拒绝。（依赖：T008）
- [X] T010 在 `src/code_data_factory/contracts/resources.py`、`configs/execution/resource-policy.yaml` 实现共用报价/授权引用/停止上限与费用台账，分别记录 CPU、GPU、存储和外部模型失败重试费用，缺授权或报价禁止外部运行。（依赖：T009）
- [X] T011 在 `src/code_data_factory/cli.py` 实现统一结构化输出、错误码 0/2–8、标准错误日志和 dry-run 语义；在 `tests/contract/test_cli_envelope.py` 验证尚未实现的业务不能返回伪成功。（依赖：T010）
- [X] T012 运行核心契约与模式兼容验证，保存 `artifacts/checkpoints/foundation.json`，同期在本机私有决策记录（不提交）中记录身份/状态/哈希取舍或无新增工程议题回执；远端回执字段和证据层级遵守[租用 Linux 环境恢复与依赖验证契约](contracts/rented-environment-recovery.md)。（依赖：T011）

**Checkpoint**: 基础契约通过，旧版本/歧义关联/私有参考/未知奖励都不能静默晋级。

## Phase 3: User Story 1 - 生产可追踪的任务与轨迹数据版本 (Priority: P1)

**Goal**: 公开原料→规范记录→治理/去重/分组→增量版本；为实际验证和训练提供可追踪输入。
**Independent Test**: 用独立手写夹具测试导入、发布与撤销、本地/Ray 等价和 SFT 导出；夹具证据
仅软件级。正式可执行数据发布须等 US2 的真实验证，不能由此阶段的夹具替代。

### Tests

- [X] T013 [P] [US1] 在 `tests/contract/test_source_import.py`、`tests/contract/test_sft_export.py` 验证原始/规范字段映射、歧义隔离、失败原池不变、必要上下文与模型输出控制词元损失标记。（依赖：T012）
- [X] T014 [P] [US1] 在 `tests/integration/test_dataset_governance.py` 验证同源/模板/重复组切分、桥接冲突、撤销影响、增量/全量一致及写入前后失败，手写预期输入独立于业务实现。（依赖：T012）

### Implementation

- [X] T015 [US1] 在 `src/code_data_factory/sources/audit.py` 复用 `huggingface_hub`/PyArrow 读取固定来源，按 `configs/sources/toucan-sft.json`、`configs/sources/documents.json` 保存版本/许可/敏感检查、实际工具范围与依赖缺失报告。（依赖：T013）
- [X] T016 [US1] 在 `src/code_data_factory/sources/toucan.py` 实现历史序列安全解析和事件映射，保留 raw 引用与唯一推断关联来源；禁止执行输入表达式，缺环境记录仅进 HISTORICAL_ONLY。（依赖：T015）
- [X] T017 [US1] 在 `src/code_data_factory/tasks/build.py`、`configs/tasks/pilot.yaml` 构建三个任务族的 100 个独立先导任务草稿，固定资料/数值真值/工具/来源与模板根；每族至少 20 个，尚不标可执行；提供分组预分配接口，变体生成须读取登记簿。（依赖：T016）
- [X] T018 [US1] 在 `src/code_data_factory/processing/dedup.py` 复用 datasketch MinHash/局部敏感哈希实现候选适配及精确去重，保存投影、种子、阈值和代表选择证据，不按工具序列直接合并不同任务。（依赖：T014、T017）
- [X] T019 [US1] 在 `src/code_data_factory/processing/quality.py`、`configs/quality/build.yaml` 实现独立质量维度与决策账本，支持未知/拒绝/修复新记录及可靠错误片段标记；只消费验证记录，不自造成功标签。（依赖：T018）
- [X] T020 [US1] 在 `src/code_data_factory/tasks/splits.py` 实现来源—模板派生连通组与固定切分登记，粗任务族只分层；连接不同已冻集合的新对象须隔离并触发失效，训练前变体继承原归属。（依赖：T019）
- [X] T021 [US1] 在 `src/code_data_factory/datasets/quality_reports.sql` 使用 DuckDB 重算独立任务/轨迹数、质量、配比、拒绝、奖励缺失及单位产出成本；无产出成本为空，过程失败与终态分别计数。（依赖：T020）
- [X] T022 [US1] 在 `src/code_data_factory/processing/backends.py` 复用 Ray Data 提供本地/Ray 同算子读取、分组、转换与落地，事件按尝试和序号还原、大观察走引用、块按字节限额，禁止执行生成代码。（依赖：T021）
- [X] T023 [US1] 在 `src/code_data_factory/processing/commit.py` 实现输入/规则/登记簿驱动的增量分区与全局受影响簇重算，复用 DVC 缓存及 Ray 重试，记录恢复事件，清单提交幂等且无部分发布。（依赖：T022）
- [X] T024 [US1] 在 `dvc.yaml`、`src/code_data_factory/datasets/build_input.py` 连接原料/任务/实际尝试/验证/切分清单，落实 `data/build-inputs/pilot.json` 契约，不能只读历史原料丢掉实际执行结果。（依赖：T023）
- [X] T025 [US1] 在 `src/code_data_factory/datasets/publish.py` 定义数据版本/成员/决策关系并发布本地不可变数据卡、报告、谱系和哈希；用途与实际证据门禁不通过即阻断，夹具仅作软件测试。（依赖：T024）
- [X] T026 [US1] 在 `src/code_data_factory/datasets/export_sft.py`、`configs/experiments/export-sft.yaml` 复用冻结分词器/模板导出完整上下文、选定目标与逐词元映射；排除观察/输入包装损失、保留输出控制词元，过长或错误定位未知的样本拒绝。（依赖：T025）
- [X] T027 [US1] 在 `src/code_data_factory/sources/revoke.py` 实现来源撤销与数据/运行/结论的关系查询，删除分发内容或标记失效、只留必要非敏感审计；后续实验实体按同一引用协议加入索引。（依赖：T026）
- [X] T028 [US1] 在 `src/code_data_factory/cli.py` 接入 `source audit/revoke`、`task build`、`trajectory import`、`data build --resume`、`dataset publish/export-sft`，完成各命令 schema/失败码与产物契约检查。（依赖：T027）
- [ ] T029 [US1] 执行固定来源审计、候选近重复至少 100 对人工抽审和漏检探针，保存 `artifacts/data-audit/source_report.json`、`artifacts/data-audit/dedup_review.parquet`；据结果冻结规则，不合格不扩量；语义向量复核仅在实测缺口成立时另记启用决定。（依赖：T028）
- [ ] T030 [US1] 运行本地/Ray、全量/增量等价和提交前/后各一次故障恢复，保存 `artifacts/data-runs/equivalence/manifest.json`；用同一登记簿验证逻辑哈希/决策一致与无重复发布。（依赖：T029）
- [ ] T031 [US1] 从规范导入/草稿重建一次版本并测试撤销传播、SFT 掩码和原始失败保留，保存 `artifacts/checkpoints/us1-software.json`，仅报告有实际证据的用途与数据数量。（依赖：T030）
- [ ] T032 [US1] 在本机私有决策记录（不提交）中记录 US1 数据治理取舍、SC-001/004–007 的软件证据和剩余真实发布门禁，并把检查回执关联到 `artifacts/checkpoints/us1-software.json`。（依赖：T031）

**Checkpoint**: US1 软件治理可独立演示；正式合格池与实际质量指标由 T047 回验，不得冒充已执行验证。

## Phase 4: User Story 2 - 判断工具轨迹是否真正完成任务 (Priority: P1)

**Goal**: 复用 Agent/工具组件，获得独立、可重复且不向模型泄漏真值的交互证据。
**Independent Test**: 至少 35 个正负哨兵、100 个固定动作任务重复执行、30 条真实轨迹抽查。

### Tests

- [ ] T033 [US2] 在 `tests/contract/test_interaction.py` 编写多调用对应、隐藏工具拒绝、实际可见上下文、额外终答预算和封存后独立评分的契约测试。（依赖：T012）
- [ ] T034 [US2] 在 `tests/fixtures/verification/` 准备七类各至少五个独立金标准案例，并在 `tests/integration/test_verifier_controls.py` 验证错参数/错依赖/假成功/截断/环境故障/未知和两条合法不同路径。（依赖：T033）

### Implementation

- [ ] T035 [US2] 在 `src/code_data_factory/interaction/tools.py` 复用 DuckDB 全文检索、decimal、zoneinfo 与 Pint 包装四个受限工具，冻结单位/时区/资料版本；运算枚举与数值入参，不引入任意代码解释器。（依赖：T017、T034）
- [ ] T036 [US2] 在 `src/code_data_factory/interaction/environment.py`、`configs/execution/local-tools.yaml` 实现独立会话与 Linux 非特权只读容器/资源/默认断网检查，模型在外部受控调用；不写沙箱内核，环境不合格不能晋级。（依赖：T035）
- [ ] T037 [US2] 在 `src/code_data_factory/interaction/smolagents_adapter.py` 使用 ToolCallingAgent 和步骤回调，包装实际模型请求/原始输出，关闭隐式规划及无关工具，绑定独立会话而非重写 Agent 循环。（依赖：T036）
- [ ] T038 [US2] 在 `src/code_data_factory/interaction/budgets.py`、`configs/execution/collect.yaml` 实现调用前预算守卫，覆盖批量工具/辅助终答；初始限制按 plan 的 8 次、4096/8192 词元、8192/65536 字节和 120 秒，超限明确记录。（依赖：T037）
- [ ] T039 [US2] 在 `src/code_data_factory/interaction/events.py` 实现实际请求/输出/调用/返回的事件落地、完整与不完整尾部封存、取消/中断/环境故障，重试只限安全动作且不复用整任务身份。（依赖：T038）
- [ ] T040 [US2] 在 `src/code_data_factory/verification/tasks.py`、`configs/quality/verifier.yaml` 实现独立结果值/引用/约束断言及依赖诊断，使用固定真值/独立公式；未知/不稳定不给确定判定，验证器不暴露为模型工具。（依赖：T039）
- [ ] T041 [US2] 在 `src/code_data_factory/interaction/replay.py` 实现日志 inspect 和固定动作真实 replay 两种入口，验证冻结初始资源/工具版本、保存新尝试和差异；缺原环境不能偷偷换工具。（依赖：T040）
- [ ] T042 [US2] 在 `src/code_data_factory/verification/rewards.py`、`configs/quality/reward-terminal-v1.yaml` 实现已验证 PASS→1、FAIL→0、UNKNOWN→null 的独立版本记录，过程诊断不混入终局奖励，原证据不可覆盖。（依赖：T041）
- [ ] T043 [US2] 在 `src/code_data_factory/cli.py` 接入 `environment check`、`trajectory collect/inspect/replay`、`verify run`，对统一输出和所有终态进行契约核对。（依赖：T028、T042）
- [ ] T044 [US2] 在合格 Linux 环境完成 100 先导任务各两次固定动作执行与至少 35 例全部金标准对照，保存 `artifacts/verifications/pilot/manifest.json`；逐任务审计依据，失败先修复并停止扩大采样。（依赖：T032、T043）
- [ ] T045 [US2] 在已授权模型/预算内采集实际先导轨迹并抽查至少 30 条，保存 `artifacts/interactions/pilot/manifest.json`、`artifacts/data-audit/trajectory_review.parquet`；逐轮输入、依赖、结果和全部失败成本完整。（依赖：T044）
- [ ] T046 [US2] 按 `configs/tasks/production.yaml` 冻结独立分组后扩大训练候选，目标上限 5000 任务、每题最多四次、总计最多 20000 次尝试，保存 `artifacts/interactions/production/manifest.json`；只使用训练分组，单列未达量/被过滤原因。（依赖：T045）
- [ ] T047 [US2] 通过完整构建输入清单生成 `data/releases/verified/` 与 `data/exports/verified/`，重跑发布/掩码/谱系门禁并记录实际质量/成本；同池候选无未验证任务、历史观察或跨集合泄漏。（依赖：T026、T046）
- [ ] T048 [US2] 保存 `artifacts/checkpoints/us2.json` 并更新本机私有决策记录（不提交），关联先导、正负对照、示范抽审及 US1 实际发布回验，分别声明软件、隔离执行与未训练边界。（依赖：T047）

**Checkpoint**: 有可执行且独立验证的真实数据池；工具成功不能替代任务成功，US1 真实数据验收可回验。

## Phase 5: User Story 6 - 扩展 RL 与长程轨迹 (Priority: P1)

**Goal**: 不重建核心即可对接一个现成训练器，并检验长程上下文、受控恢复和稀疏奖励。
**Independent Test**: 两入口固定动作等价；两任务各两次真实采样；32/128 步存读、上下文改写与恢复；
成功/全零/未知/截断四类各至少两个任务重评分。无需 RL 参数优化。

### Tests

- [ ] T049 [US6] 在 `tests/contract/test_training_consumer.py`、`tests/integration/test_long_horizon.py` 声明真实词元/输出标记、缺字段拒绝、未知奖励、32/128 步和不可恢复环境的预期行为，替身与真实运行标记分离。（依赖：T048）

### Implementation

- [ ] T050 [US6] 在 `src/code_data_factory/interaction/checkpoints.py` 实现仅受控只读语料/会话工作区的状态快照与恢复，记录随机状态、父尝试和分支点；缺能力返回 unsupported，不把日志回看当恢复。（依赖：T049）
- [ ] T051 [US6] 在 `tests/fixtures/long_horizon/`、`configs/execution/long-horizon.yaml` 构建 32/128 步确定性案例，含取值依赖、大观察引用、截断前后可见输入和一次摘要替换；不训练摘要模型。（依赖：T050）
- [ ] T052 [US6] 在 `src/code_data_factory/interaction/trl_adapter.py`、`configs/execution/trl-tools.yaml` 适配 TRL 环境工厂，复用 reset/四个工具/验证器；辅助和评分方法保持私有，优先沿用上游循环，必要扩展只按已证明接口缺口补采样回调。（依赖：T051）
- [ ] T053 [US6] 在 `src/code_data_factory/interaction/sampling_records.py` 定义消费 profile、SamplingAttachment 与 CompatibilityReceipt，直接保存上游真实词元和输出 mask/策略身份；长度不等、伪身份、历史重编码或不支持的上下文重写必须拒绝。（依赖：T052）
- [ ] T054 [US6] 在 `src/code_data_factory/verification/rescore.py`、`tests/fixtures/sparse-rewards/`、`configs/quality/reward-terminal-v2.yaml` 实现固定证据重评分与按任务/尝试的奖励分布报告，两个版本差异可为零但须解释，不引入自动密集奖励。（依赖：T053）
- [ ] T055 [US6] 在 `src/code_data_factory/cli.py` 接入 `compatibility check` 三模式及 `reward rescore`，回执按接口替身、真实采样、长程/恢复逐项记录，缺真实运行不签发笼统兼容成功。（依赖：T054）
- [ ] T056 [US6] 执行两入口固定动作、32/128 步存读、上下文改写、受控恢复/不支持拒绝及四类稀疏奖励重评分，保存 `artifacts/compatibility/contract/`、`artifacts/compatibility/long-horizon/`，包括状态/哈希/词元关联检查。（依赖：T055）
- [ ] T057 [US6] 在 `configs/experiments/model-candidates.yaml`、`artifacts/compatibility/model-profile.json` 固定 Qwen3-8B 首选与 Qwen3-4B 事前备选顺序及实际 revision/模板/思考模式，完成推理/词元通道资源探针；不声称 SFT 已可训练，费用接 T010。（依赖：T056）
- [ ] T058 [US6] 用 T057 模型在合格环境完成至少两个任务各两次真实训练器采样，保存 `artifacts/compatibility/sampling/`，核对实际输入输出词元、mask、版本、成本及未调用优化器；不能用成功脚本代替真实模型失败轨迹。（依赖：T057）
- [ ] T059 [US6] 汇总 SC-011–013 至 `artifacts/checkpoints/us6.json` 并更新本机私有决策记录（不提交），注明后续 RL 仅增加算法/预算附件，真实长程能力与 RL 参数更新尚未验证。（依赖：T058）

**Checkpoint**: 首版强制扩展验收完成；未取得真实采样、恢复或长程证据的项保持未完成。

## Phase 6: User Story 3 - 以评测反馈调整数据并形成归因闭环 (Priority: P2)

**Goal**: 开发失败→证据/原因假设→同池数据配方；提供后续真实训练与复评所需输入。
**Independent Test**: 固定开发评测可独立验证反馈软件；真实闭环最终验收在 T084，不能要求 US3
先完整关闭才能开始依赖其配方的 US4。

### Tests

- [ ] T060 [US3] 在 `tests/contract/test_evaluation_feedback.py` 验证固定分母、失败重试、开发/test 权限、原因假设与事实分离、目标干预不被匹配消除，并拒绝最终测试引用进入反馈。（依赖：T048）

### Implementation

- [ ] T061 [US3] 在 `src/code_data_factory/evaluation/suites.py`、`configs/evaluation/tool-tasks.yaml` 构建开发/最终测试各至少 200 任务、三个族各至少 40、测试至少 50 未见组合且至少 20 独立来源—模板连通组；冻结标识/私有参考与切分登记，组不足阻断归因。（依赖：T047、T060）
- [ ] T062 [US3] 在 `src/code_data_factory/evaluation/interactive.py` 实现实际逐步执行评测和 TaskSuccess@1（一次完整尝试成功率），固定全分母与系统故障最多一次原配置重试，另报有效执行覆盖、恢复/未见组合/成本/约束；未解决系统故障阻断因果结论。（依赖：T061）
- [ ] T063 [US3] 在 `src/code_data_factory/evaluation/bfcl.py`、`configs/evaluation/bfcl-local-v4.yaml` 复用 BFCL 官方评测程序，解析 `f7cf735` 完整提交及数据/许可、冻结本地多轮/无关工具子集和协议偏离；需执行不可信代码的子集隔离不通过则拒绝。（依赖：T062）
- [ ] T064 [US3] 以 T057 模型运行项目及外部开发评测，保存 `artifacts/evaluations/base-development/` 和候选池事前难度估计，模型/模板/工具版本清楚；此阶段不解锁最终 test。（依赖：T057、T063）
- [ ] T065 [US3] 在 `src/code_data_factory/evaluation/findings.py`、`src/code_data_factory/evaluation/findings.sql` 使用 DuckDB 汇总错误/依赖/上下文切片，形成 Finding 的原始证据、假设、反证及置信程度，不称为已证明因果。（依赖：T064）
- [ ] T066 [US3] 在 `src/code_data_factory/datasets/feedback.py`、`configs/quality/feedback.yaml` 实现 DataAction/复验关系和发现驱动选择；首轮只在同一冻结合格池重选，新生成/修复不得单独混入处理组。（依赖：T065）
- [ ] T067 [US3] 在 `src/code_data_factory/datasets/recipes.py` 构建 RandomMatched 与 ClosedLoop 草稿，匹配来源/粗任务族/深度/长度/验证强度/基线难度，保留失败类型覆盖差异，保存联合支持、共同剔除与平衡报告至 `data/recipes/main/`。（依赖：T066）
- [ ] T068 [US3] 在 `src/code_data_factory/cli.py` 接入 `evaluate run`、`feedback build`，确保正式测试解锁依赖预登记与数据冻结，不以命令参数绕过；评测和反馈均出明细与产物清单。（依赖：T067）
- [ ] T069 [US3] 执行开发评测夹具→发现→选择配方→发布草稿的集成验证，保存 `artifacts/checkpoints/us3-software.json`，验证每次非随机选择都有 finding/action，最终 test 内容与标识不进入反馈。（依赖：T068）
- [ ] T070 [US3] 在本机私有决策记录（不提交）中记录 US3 软件里程碑和 `artifacts/checkpoints/us3-software.json`，明确 SC-008 的真实训练复评依赖 T079/T083/T084，尚不能关闭完整反馈验收。（依赖：T069）

**Checkpoint**: 反馈软件与实际开发发现可交付；US3 完整训练闭环稍后 T084 回填。

## Phase 7: User Story 4 - 用固定条件实验测量数据价值 (Priority: P2)

**Goal**: 一个数据干预、相同训练方法与预算，两个配方三个种子，真实交互测量。
**Independent Test**: 夹具先证明公平/降级门禁；随后六次真实训练与评测，正/负结果均完整保留。

### Tests

- [ ] T071 [US4] 在 `tests/contract/test_experiment_fairness.py` 验证两配方/三个种子、等有效词元/步数/计算配置、完整目标片段和不泄漏 test；在 `tests/unit/test_attribution.py` 用手算配对结果检验组级重采样与无收益/回退判定。（依赖：T070）

### Implementation

- [ ] T072 [US4] 在 `src/code_data_factory/contracts/experiments.py` 定义 ExperimentPlan、TrainingRun、EvaluationRun 和终态登记，记录方法/模型/数据/批次/预算及预登记哈希；改变冻结条件只能新建计划。（依赖：T071）
- [ ] T073 [US4] 在 `src/code_data_factory/datasets/training_adapter.py` 复用 TRL/PEFT/Transformers 训练入口，消费 SFT 视图和掩码，记录实际损失词元/步数、初始权重、检查点/重载与 MLflow 索引，不实现优化器。（依赖：T072）
- [ ] T074 [US4] 在 `src/code_data_factory/datasets/batch_schedule.py` 构建完整轨迹/完整目标的确定性批次清单，精确匹配两配方有效损失词元/步数/批次形状/上下文；不靠尾部补目标词元，无法整数匹配则共同降档或拒绝。（依赖：T073）
- [ ] T075 [US4] 按 `configs/experiments/calibration.yaml` 执行单卡模型/方法可行性门禁并保存 `artifacts/experiments/calibration/method_selection.json`，全参数→LoRA→QLoRA 首个通过者统一采用，检查反向传播、至少 10% 显存余量、有限损失、保存重载和预算。（依赖：T074）
- [ ] T076 [US4] 运行两配方各一次单种子校准，保存 `artifacts/experiments/calibration/manifest.json`，核验等词元/步数、交互评测、吞吐与六次成本预测及 15% 储备；不以校准分数选择方法或正式超参数。（依赖：T075）
- [ ] T077 [US4] 在 `src/code_data_factory/evaluation/preregister.py`、`configs/experiments/sft-main.yaml` 固定目标差异、匹配容差、三种子、模型/方法/工具/模板、曝光预算、test 解锁和判定阈值；核对至少 20 统计组及 10000 次固定种子重采样，接入 `experiment calibrate/preregister/run` 命令。（依赖：T076）
- [ ] T078 [US4] 发布两个实际数据视图、批次和匹配报告并冻结 `artifacts/experiments/sft-main/experiment_plan.json`，验证报价/总预算、全部依赖及当前模型版本一致；模型备选切换时按下述“版本失效规则”重新建立相关证据后才能登记。（依赖：T077）
- [ ] T079 [US4] 执行 RandomMatched/ClosedLoop 各种子 17/29/43 共六次正式 SFT，保存 `artifacts/experiments/sft-main/training/` 的参数更新、检查点、词元/步数、日志、费用和全部终态；失败保留并标未达训练门禁，不筛选有利种子。（依赖：T078）
- [ ] T080 [US4] 数据/方法冻结后，对六次有效训练模型运行项目与 BFCL 固定最终测试，保存 `artifacts/evaluations/formal-test/`；每轮真实执行工具、固定分母和重试、外部分项与协议偏离分别报告。（依赖：T079）
- [ ] T081 [US4] 在 `src/code_data_factory/evaluation/statistics.py` 复用统计库汇总逐种子差值/均值/标准差和来源—模板组配对 95% 区间，保持组间配对，不将改写当独立样本，不以三个粗任务族代替统计组。（依赖：T080）
- [ ] T082 [US4] 生成 `reports/sft-main/attribution.json`，按预登记的 2 个百分点实际意义阈值、区间下界和护栏判定，完整呈现正向/无收益/回退/不确定/未完成，未解决环境故障或等预算失败阻止因果陈述。（依赖：T081）
- [ ] T083 [US4] 以训练模型按同一协议复评原开发切片，保存 `artifacts/evaluations/formal-development/`，只连接原 finding/action 的结果，不能利用最终 test 追加有利训练或修改配方。（依赖：T082）
- [ ] T084 [US4] 将真实开发发现→数据选择→发布→训练→复评闭环写入 `reports/sft-main/feedback_outcomes.parquet`，包含无改善/回退记录，生成 `artifacts/checkpoints/us3-training.json`，完成 SC-008 实际回验。（依赖：T083）
- [ ] T085 [US4] 保存 `artifacts/checkpoints/us4.json` 并更新本机私有决策记录（不提交），核对六次实际运行、公平性、外部/项目结果、费用和 SC-008–010；未达到所需证据时保持对应门禁未完成。（依赖：T084）

**Checkpoint**: 取得可归因的真实比较或完整诚实的未完成结果；“有正收益”不作必达目标，但实际
参数更新/公平对照/真实评测缺失不能算训练验收通过。

## Phase 8: User Story 5 - 独立核验数据生产与实验成果 (Priority: P2)

**Goal**: 可核验的分布式处理、端到端谱系、报告和复现。规模分支可在 US1/US2 后提前运行。
**Independent Test**: 64 GiB 固定数据的真实多节点/故障；重建数据、重算指标并删除一项证据验证拒绝。

### Tests

- [ ] T086 [P] [US5] 在 `tests/contract/test_evidence_publication.py` 编写缺哈希/缺运行/伪层级/负结果隐藏的反例，以及双向谱系和撤销对实验/结论的影响检查。（依赖：T012）

### Implementation

- [ ] T087 [P] [US5] 在 `configs/distributed/ray-scale-v1.yaml`、`src/code_data_factory/processing/scale_plan.py` 固定 CPU/存储报价、授权和停止上限、同构 1/2/4 节点、各一次预热/五次正式测量及随机顺序，检查私网/共享存储/依赖版本。（依赖：T030）
- [ ] T088 [US5] 在 `src/code_data_factory/processing/benchmark_input.py` 构造至少 64 GiB 固定轨迹/事件负载至 `artifacts/data-benchmarks/ray-scale-v1/input_manifest.json`，保留原任务和副本双身份，BENCHMARK_ONLY 不能进入训练/开发/test。（依赖：T047、T087）
- [ ] T089 [US5] 在 `src/code_data_factory/processing/scale_run.py` 复用 Ray Jobs/数据统计接入 `cdf benchmark run` 于 `src/code_data_factory/cli.py`，保存节点与进程分布、资源、溢写/重分布、吞吐、失败重试/费用；未支持指标标空。（依赖：T088）
- [ ] T090 [US5] 完成真实 1/2/4 节点各五次测量和预热、工作进程终止注入，保存 `artifacts/data-benchmarks/ray-scale-v1/raw_trials.parquet` 及每次运行证据；进程数不能冒充节点数，无授权/节点则记录未完成。（依赖：T089）
- [ ] T091 [US5] 用 `src/code_data_factory/processing/scale_report.py` 生成 `artifacts/data-benchmarks/ray-scale-v1/scale_report.json`，校验等价哈希、计数、全部原始轮次与恢复，给吞吐/成本/瓶颈及无加速结果；不升级为模型证据。（依赖：T090）
- [ ] T092 [US5] 在 `src/code_data_factory/evaluation/lineage.py` 汇总已存在来源/任务/验证/版本与训练/评测/发现关系，扩展撤销影响至模型与结论，生成 `reports/sft-main/lineage_index.json`，DVC/MLflow 索引不能替代语义关系。（依赖：T085、T086）
- [ ] T093 [US5] 在 `src/code_data_factory/evaluation/report.py` 生成 Markdown/JSON 结论清单，校验所有证据层级、公平门禁、负结果与限制，从同一事实重算质量/成本/模型指标；多节点证据缺失显示未完成。（依赖：T091、T092）
- [ ] T094 [US5] 在 `src/code_data_factory/evaluation/reproduce.py` 复用 DVC/冻结入口重建选定数据版本和指标，比较逻辑哈希/允许差异，执行前校验外部资源及数据用途，不拷贝旧日志冒充重跑。（依赖：T093）
- [ ] T095 [US5] 在 `src/code_data_factory/cli.py` 接入 `report build`、`evidence verify`、`reproduce`，用 `tests/contract/test_evidence_commands.py` 校验缺证据退出码、实际与降级状态和复现输入边界。（依赖：T094）
- [ ] T096 [US5] 独立重建一个真实数据版本、重算一项逐题指标，再移除一项必要证据验证阻断，保存 `artifacts/reproductions/verified/`、`artifacts/evidence-audit/`；恢复证据后报告状态与原事实一致。（依赖：T095）
- [ ] T097 [US5] 审查 `reports/sft-main/report.md`、`reports/sft-main/claims.json` 的表述、个人/敏感信息与成本分母，只准备可分发内容，不上传或提交；逐项说明任务/来源/节点/模型范围。（依赖：T096）
- [ ] T098 [US5] 保存 `artifacts/checkpoints/us5.json` 并更新本机私有决策记录（不提交），关联 SC-014/015 的真实节点与独立复现证据；所有用户故事须有实际工程议题记录或无新增回执。（依赖：T097）

**Checkpoint**: 评审者能独立复现和审计，不能凭软件/数据量或漂亮报告推断模型收益。

## Phase 9: Polish and Cross-Cutting Validation

**Purpose**: 只收尾本规格所需质量与可复现交付，不扩展平台或训练矩阵。

- [ ] T099 运行项目构建与适当的静态/契约/集成检查，保存 `artifacts/checkpoints/software-final.json`，核对锁文件、安装入口和模式；真实资源检查只引用已验证同版本记录或按必要失效项重跑。（依赖：T059、T070、T085、T098）
- [ ] T100 逐步核对 `specs/001-code-data-factory/quickstart.md` 与实际 `cdf` 输入输出和已产生运行证据，修正指南漂移，生成 `artifacts/checkpoints/quickstart.json`；不为复查命令再次无条件启动六次付费训练。（依赖：T099）
- [ ] T101 将全部 FR-001–040、SC-001–015 映射到任务、测试、真实产物和当前状态，输出 `reports/final/requirements-traceability.md` 与机器清单，任何未完成强制验收保持 OPEN。（依赖：T100）
- [ ] T102 更新 `README.md` 与 `reports/final/report.md`，并同步更新本机私有决策记录（不提交）；按实际结果展示数据工程、开源复用、扩展兼容和归因，保留限制/失败；不宣称正式 RL 或长程模型收益。（依赖：T101）

## Dependencies and Execution Order

### Story Dependency Graph

```text
Setup -> Foundation -> US1 软件治理 -> US2 实际执行/合格池
                                      |-> US6 兼容/长程/真实采样
                                      |-> US5 多节点分支 T087–T091
US2 + US6 模型身份 -> US3 开发评测/配方 -> US4 校准/六次训练/复评
                                               |-> US3 实际闭环回填 T084
US4 + US5 多节点分支 -> US5 全谱系/报告/复现 -> 最终验收
```

US1 夹具导出不是已验证正式发布；T047 补真实门禁。US3 的软件回执 T070 可解锁 US4，T084 才完成
SC-008；不得把 T084 设成 US4 的前置条件。US5 多节点分支仅依赖已可运行的数据处理，与模型训练
独立，可按计划第 7 周执行；不要机械等到 T085 才开始。

### Default Sequential and Parallel Rules

任务的显式依赖包含共享语义与产物依赖；无 `[P]` 的编辑默认串行，尤其 `cli.py`/日志/锁文件。
测试先验证预期失败，再实施对应模块；同阶段的独立测试可先并行编写。上游依赖失败只停止受影响
分支，继续可独立完成的数据/软件工作；未完成验收不勾选。

| 并行波次/例子 | 可并行任务或活动 | 前提与不能并行的部分 |
|---|---|---|
| Setup | T002、T003 | T001 后；各自文件独立，不共同修改 pyproject.toml |
| US1 | T013、T014 | T012 后，测试文件和输入独立 |
| US2 | 固定任务的两次隔离执行可跨任务并行 | T044 内，任务/尝试目录唯一，重复一致性仍逐任务核对；T037–T043 默认串行 |
| US6 | 长程两组固定夹具可并发运行 | T056 内，各自工作区；T058 真实采样按授权并发且每次独立记录 |
| US3 | 项目与外部开发评测可分开执行 | T064 内，固定相同模型身份、预算各计，反馈必须等两者终态 |
| US4 | 六次独立单卡运行可分批并发 | T079 内，不改变每次预算；不得让两组使用不同硬件/方法 |
| US5 | T086、T087 | 各自依赖满足后可并行；不同文件，T087 不需要模型训练结果 |

表中运行内并发交给现成 Ray/训练组件，不额外实现调度器；任务级 `[P]` 仅标记上述三个波次的六个任务。

### Version Invalidation Rule

T057 冻结的是实际采样模型身份，不证明其 SFT 可行性。若 T075 必须切换到已登记备选模型/模板，
必须新建版本并使旧模型关联的 T058/T064/T067 产物失效：重新执行真实采样探针、开发/难度评测、
匹配配方和导出/批次/校准后才能 T078 预登记。保留全部旧终态，不按模型分数择优，不混合两种
模型的反馈与正式实验。此为同一有向无环依赖图的新版本重建，不添加反向前置依赖或混入最终 test。

## Requirement and Acceptance Coverage

映射给出负责实现和关键验收的任务；实际完成状态及证据最终由 T101 生成，不据本表预先标通过。

| 功能需求 | 负责实现/验证任务 |
|---|---|
| FR-001–005 | T003、T015–T017、T025、T027–T029、T044–T048 |
| FR-006–008 | T005–T009、T013、T016、T033、T037–T039、T049–T053 |
| FR-009–014 | T033–T045、T049–T056 |
| FR-015–018 | T014、T018–T021、T029、T047、T054 |
| FR-019–021 | T009、T014、T022–T025、T027、T030–T032、T092、T096 |
| FR-022–023 | T013、T026、T042、T047、T053–T054、T071–T074 |
| FR-024 | T060、T064–T070、T083–T085 |
| FR-025–026 | T060、T067、T071–T079、T081–T082 |
| FR-027–030 | T060–T064、T068、T071–T085、T092–T102 |
| FR-031–037 | T049–T059、T072、T077–T078、T101–T102 |
| FR-038–039 | T022、T030、T087–T091、T098 |
| FR-040 | T003、T012、T032、T048、T059、T070、T085、T098、T101–T102 |

| 成功标准 | 关键实际验收任务 | 不能代替的证据 |
|---|---|---|
| SC-001 | T027、T031、T047、T092、T096 | 真实成员/撤销关系，不能只有空表 |
| SC-002 | T044 | 100 个独立任务、各两次真实固定动作执行 |
| SC-003 | T034、T044–T045 | 至少 35 个独立正负对照按预期分类 |
| SC-004 | T013、T026、T047 | 实际模板/词元目标与失败原池对账 |
| SC-005 | T014、T020、T029、T047 | 100 对人工复核及切分/污染检查 |
| SC-006 | T014、T023、T030 | 本地/Ray、增量/全量等价和两种提交故障 |
| SC-007 | T021、T047、T054 | 实际质量/配比/全费用及奖励分母 |
| SC-008 | T064、T067、T079、T083–T085 | 实际训练复评闭环，T070 软件结果不够 |
| SC-009 | T075–T080、T085 | 两配方三个种子真实训练与公平记录 |
| SC-010 | T061–T064、T080–T083 | 实际项目/外部交互评测、固定分母 |
| SC-011 | T052–T053、T056–T059 | 同语义双入口及两任务各两次真实采样 |
| SC-012 | T050–T051、T056、T059 | 32/128 步、改写、受控恢复与不支持拒绝 |
| SC-013 | T042、T054、T056、T059 | 两奖励版本、四类稀疏记录与原证据不变 |
| SC-014 | T087–T091、T098 | 64 GiB、真实 1/2/4 节点各五次及故障/费用 |
| SC-015 | T086、T092–T102 | 真实重建/重算/删证据阻断及六个故事回执 |

## CLI Coverage

CLI 表示命令行界面；这里只映射 [命令契约](contracts/cli.md)，不增加新命令。

| 命令组 | 任务 |
|---|---|
| `source audit/revoke`、`task build`、`trajectory import` | T015–T017、T020、T027–T028 |
| `data build --backend/--resume`、`dataset publish/export-sft` | T018–T026、T028、T047 |
| `environment check`、`trajectory collect/inspect/replay`、`verify run` | T035–T043 |
| `reward rescore`、`compatibility check` | T049–T058 |
| `evaluate run`、`feedback build` | T060–T068 |
| `experiment calibrate/preregister/run` | T071–T079 |
| `benchmark run` | T087–T091 |
| `report build`、`evidence verify`、`reproduce` | T092–T096 |

## Implementation Strategy

### MVP First

先完成 T001–T032，演示真实原料的治理/去重/切分/版本与明确证据边界；这是数据工程软件 MVP。
随后 T033–T048 加入 100 个先导任务及真实合格轨迹，形成可对外解释的完整数据产线。两者均不是
整个首版完成；T049–T059 的 RL/长程兼容及后续固定条件训练/分布式验收仍为必需。

### Incremental Delivery

1. 包/契约与原料审计 → US1 数据治理软件；任务先导先以草稿准备，真实可执行门禁在 T044。
2. 实际工具交互/验证 → 合格池、质量/成本及原始失败；不在先导通过前扩大采样。
3. RL/长程兼容 → 独立真实采样回执；同期推进独立多节点数据实验。
4. 开发评测/配方 → 单卡校准/预登记 → 六次正式训练/复评 → 回填真实数据反馈结果。
5. 多节点和模型证据汇聚 → 独立复现/删证据门禁 → 需求证据矩阵与可读报告。

12 周为 plan 的排期目标，实施先遵循依赖。第 1 周准备的 100 任务不能在尚无执行器时标已验证；
真实先导随 T044 门禁完成。不得因日历日期到达就越过契约、环境、费用或公平性检查。

### Stop and Scope Rules

- 只暂停缺依赖的分支；保留失败产物，继续可独立完成的数据工程工作。
- CPU/GPU/模型服务费用统一进入项目费用视图；GPU 5000 元启动软上限、最高可论证 10000 元和
  15% 储备沿用 plan，外部费用需独立已授权上限，不据任务数量增加预算。
- 实际上游接口不足时记录具体缺口，优先适配已有扩展点；不得直接转向自建平台或新增第二套引擎。
- 模型收益不是预设结果；数据处理成功、扩展夹具通过或正奖励不能替代六次训练与独立评测。
- 32/128 步固定案例、真实采样、64 GiB 多节点、同池三种子和归因闭环都不可静默删为可选。
- 每个故事检查点须在本机私有决策记录（不提交）中解释实际机制、替代、取舍、结果与证据，或明确
  记录无新增工程议题的回执。任务完成、检查点完成和整个项目完成分别判断。
