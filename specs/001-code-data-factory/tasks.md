---
description: "Dependency-ordered implementation tasks for Agent trajectory data engineering, specification 2.1"
---

# Tasks: Agent 工具调用轨迹数据工厂

**Revision**: 2.1 | **Created**: 2026-09-08 | **Revised**: 2026-09-10 | **Status**: 44 项保留原验收；64 项未完成，含新增的 6 项来源/准入迁移任务。
**Input**: [spec.md](spec.md)、[plan.md](plan.md)、[research.md](research.md)、
[data-model.md](data-model.md)、[contracts/](contracts/)、[quickstart.md](quickstart.md)。spec/plan/tasks 为 2.1；其他文档中冲突的来源/准入约定待 T103 同步，以 plan 的 2.1 迁移节为准。
**Prerequisites**: 阅读项目宪章 3.0.2、上述设计、任务所属契约，以及可用时的本机私有决策记录（不提交）。
本次保留 T001–T044 的已完成状态及原任务正文，不用新需求改写其历史证据。T045–T047 尚未执行，
现改为外部示范试点/批量治理/发布；移入 US1（用户故事 1）。新增 T103–T108 承接旧契约和实现迁移。
编号为稳定任务身份，新增依赖可能指向更大编号；实际执行按显式依赖和下述阶段，不能按编号递增盲跑。
T017 的任务构建、T024 的原构建输入、T025–T026 的软件发布/导出等均只保留 2.0 证据；T108/T047
完成后才满足新版外部示范准入与实际发布。已勾选不代表新版交付自动完成。

## Format and Execution Rules

- 任务采用 `- [ ] T编号 [P可选] [US编号] 描述与路径`。US 表示用户故事，P 表示明确列出的并行波次。
  编号不再表示执行顺序；显式依赖优先，满足依赖的独立分支可以提前执行。
- 功能需求 FR、成功标准 SC 的编号均指规格 2.1。最小可行版本称 MVP；SFT 为监督微调，RL 为
  强化学习；CPU 为中央处理器、GPU 为图形处理器，GiB 为 2^30 字节的吉比字节。
- 测试任务来自规格中明确要求的契约、失败处理、公平性和验收场景；先验证失败原因，再实现并重跑。
  不为简单文档或原样上游包装添加逐行镜像测试，不复制开源组件已有的算法测试。
- 复用 Ray Data、datasketch、smolagents、TRL/PEFT、DVC、MLflow、DuckDB 和官方 BFCL 评测。
  仅实现任务语义、数据适配、质量/选择、验证断言与证据；禁止另造 Agent 循环、训练/调度平台或索引算法。
- 每项包含业务验证或实际运行的任务须保存输入/配置版本、结果、失败与产物引用。运行任务只有在
  指定验收通过后才勾选；依赖缺失时记录未完成，不能用软件替身、旧日志或计划结果代替。
- 所有数据集发布均指本地不可变产物提交；不授权上传外部平台或 Git 提交。外部采样/租机必须已有
  资源授权、报价和冻结停止上限；任务清单本身不增加现金授权。
- 正式 SFT 示范来自外部开源数据集；本地任务、固定动作、评测输出和 RL 探针不得混入。外部发布
  不依赖本地环境或模型生成，训练消费/重放/结果/奖励资格分开，未知不伪造成功。
- 首版不安排自行采样生产训练数据。修复保留父记录，新来源/修复重过治理进入下一候选池；冻结实验中途不单独补某组。
- 本版不再展开正式 RL 优化；接口/真实采样/长程/稀疏奖励兼容必须完成，不能降为可选。

## Path Conventions

一个 Python 包 `src/code_data_factory/`；命令入口 `src/code_data_factory/cli.py`，命令名称为 `cdf`。
测试在 `tests/{unit,contract,integration,fixtures}/`，配置在 `configs/`，数据在 `data/`，运行证据在
`artifacts/`，报告在 `reports/`。已有模块按需迁移，尚缺路径按任务创建，不重复搭建已实现组件。
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

**Goal**: 外部已有示范→规范化/治理→合格候选池→正式数据版本与 SFT 视图。
**Independent Test**: 原夹具验证治理软件；T103–T108 迁移准入，T045–T047 用真实外部数据验证
发布/导出。即使本地任务环境和模型生成不可用，合格示范仍可发布；不能把夹具算作实际数据交付。

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
- [X] T029 [US1] 执行固定来源审计、候选近重复至少 100 对人工抽审和漏检探针，保存 `artifacts/data-audit/source_report.json`、`artifacts/data-audit/dedup_review.parquet`；据结果冻结规则，不合格不扩量；语义向量复核仅在实测缺口成立时另记启用决定。（依赖：T028）
- [X] T030 [US1] 运行本地/Ray、全量/增量等价和提交前/后各一次故障恢复，保存 `artifacts/data-runs/equivalence/manifest.json`；用同一登记簿验证逻辑哈希/决策一致与无重复发布。（依赖：T029）
- [X] T031 [US1] 从规范导入/草稿重建一次版本并测试撤销传播、SFT 掩码和原始失败保留，保存 `artifacts/checkpoints/us1-software.json`，仅报告有实际证据的用途与数据数量。（依赖：T030）
- [X] T032 [US1] 在本机私有决策记录（不提交）中记录 US1 数据治理取舍、SC-001/004–007 的软件证据和剩余真实发布门禁，并把检查回执关联到 `artifacts/checkpoints/us1-software.json`。（依赖：T031）

**Checkpoint (2.0 retained)**: T013–T032 只保留原软件治理证据；以下迁移完成前不声称外部训练数据已交付。

### 2.1 Migration and External Data Delivery

T103–T108 是本次新增、尚未执行的工作。原研究中的 Toucan 审计和原导入的 HISTORICAL_ONLY
状态只是输入；必须重新按用途审核，不因本次文档修改而把任何旧记录直接晋级。

- [X] T103 [US1] 同步 `specs/001-code-data-factory/data-model.md`、`specs/001-code-data-factory/contracts/artifacts.md`、`specs/001-code-data-factory/contracts/cli.md`、`specs/001-code-data-factory/research.md`、`specs/001-code-data-factory/quickstart.md`、`specs/001-code-data-factory/checklists/requirements.md` 与 `README.md` 的来源/准入迁移；定义外部示范与可执行任务、训练审核与结果/奖励证据的独立契约版本及旧记录迁移，撤销已失效的自采样发布说明，不沿用旧检查单通过状态。（依赖：T032）
- [X] T104 [US1] 在 `tests/contract/test_external_eligibility.py`、`tests/integration/test_external_publication.py` 编写独立正反例：完整不可重放示范按规则接受、缺定义/上下文拒绝、源标签不变成执行 PASS/奖励、修复父链及本项目采样混入拒绝；发布测试禁用模型生成与本地环境。（依赖：T103）
- [X] T105 [US1] 在 `src/code_data_factory/contracts/tasks.py`、`src/code_data_factory/contracts/trajectory.py`、`src/code_data_factory/contracts/verification.py` 实现外部示范/上游任务引用与可执行 TaskPackage 分开建模、版本化准入决策/质量依据/重放能力及来源声明分离，环境/采样字段允许明确缺失；旧对象不就地改用途，更新模式导出。（依赖：T104）
- [X] T106 [US1] 修改 `src/code_data_factory/sources/audit.py`、`src/code_data_factory/sources/toucan.py`、`configs/sources/toucan-sft.json` 及按实际新来源增加的适配器，保留上游工具定义、消息/调用/返回/答案和分片记录定位；取消统一 HISTORICAL_ONLY 的硬编码，候选由准入政策判定；确定性修复留父链，不执行来源表达式或重跑工具补正文。（依赖：T105）
- [X] T107 [US1] 在 `src/code_data_factory/processing/quality.py`、`src/code_data_factory/datasets/build_input.py`、`src/code_data_factory/datasets/publish.py`、`src/code_data_factory/datasets/export_sft.py` 和 `configs/quality/external-sft.yaml` 实现分用途质量与发布，训练成员引用审核证据而非统一 outcome=PASS；源身份/原生工具语义/切分/敏感/上下文及真实目标映射通过才发布，拒绝本项目生成与评测记录，不调用模型/工具重新生成示范，发布只读取冻结输入和审核记录。（依赖：T106）
- [X] T108 [US1] 更新 `src/code_data_factory/cli.py`、`dvc.yaml`、`src/code_data_factory/datasets/quality_reports.sql`、`src/code_data_factory/checkpoints/us1.py` 使外部输入贯穿构建/发布/导出与原始→规范→合格→发布计数、保留率/词元/成本；运行核心/交互软件契约、迁移、增量等价/撤销/掩码及无环境发布回归，保存 `artifacts/checkpoints/external-migration.json` 并复核本机私有记录，软件测试不得算 SC-016 的真实外部交付。（依赖：T107）

- [X] T045 [US1] 按 `configs/sources/external-training.json`、`configs/quality/external-sft.yaml` 对实际外部来源做试点：保留上游版本/许可/原始分片及工具定义，按来源和能力切片抽审至少 30 条（不足全审并注明局限）；保存 `artifacts/data-audit/external-pilot/manifest.json`、`artifacts/data-audit/external-pilot/trajectory_review.parquet` 和来源—评测能力映射，无合格来源则继续外部选源，不自行采样补足。（依赖：T108）
- [X] T046 [US1] 在 `configs/data/external-production.yaml` 冻结外部分片、质量规则、切分登记及批处理费用/规模上限，复用 Ray 治理实际原料并输出 `data/candidates/external/manifest.json`；根据实际保留率、独立任务/派生数、能力覆盖和有效词元决定扩量，至少一个真实来源非空；拒绝/待复核/修复可对账，本项目任务或采样进入数必须为零。（依赖：T045）
- [X] T047 [US1] 将 T046 的外部合格池发布至 `data/releases/external/`、导出至 `data/exports/external/`，验证全部目标可追溯上游消息及修复父链；禁用本地交互环境和模型生成重建，成员/逻辑哈希相同，缺审核证据版本拒绝；保存 `artifacts/checkpoints/us1-external.json`，完成 SC-016–018 与原 US1 实际发布回验，记录实际词元/质量/成本，不依赖 T044 或 T058。（依赖：T046）

**Checkpoint (2.1 required)**: T047 完成真实外部训练发布，SC-016–018 可追溯；无环境/采样仍可运行主线。


## Phase 4: User Story 2 - 判断工具轨迹是否真正完成任务 (Priority: P1)

**Goal**: 复用 Agent/工具组件，获得独立、可重复且不向模型泄漏真值的交互证据。
**Independent Test**: 至少 35 个正负哨兵、100 个固定动作任务重复执行；原 30 条采集抽查转为 T045 外部示范审核。此分支不生产首版训练池。

### Tests

- [X] T033 [US2] 在 `tests/contract/test_interaction.py` 编写多调用对应、隐藏工具拒绝、实际可见上下文、额外终答预算和封存后独立评分的契约测试。（依赖：T012）
- [X] T034 [US2] 在 `tests/fixtures/verification/` 准备七类各至少五个独立金标准案例，并在 `tests/integration/test_verifier_controls.py` 验证错参数/错依赖/假成功/截断/环境故障/未知和两条合法不同路径。（依赖：T033）

### Implementation

- [X] T035 [US2] 在 `src/code_data_factory/interaction/tools.py` 复用 DuckDB 全文检索、decimal、zoneinfo 与 Pint 包装四个受限工具，冻结单位/时区/资料版本；运算枚举与数值入参，不引入任意代码解释器。（依赖：T017、T034）
- [X] T036 [US2] 在 `src/code_data_factory/interaction/environment.py`、`configs/execution/local-tools.yaml` 实现独立会话与平台提供的 Linux 非特权只读容器/资源/默认断网检查，模型在外部受控调用；不写沙箱内核，环境不合格不能晋级。（依赖：T035）
- [X] T037 [US2] 在 `src/code_data_factory/interaction/smolagents_adapter.py` 使用 ToolCallingAgent 和步骤回调，包装实际模型请求/原始输出，关闭隐式规划及无关工具，绑定独立会话而非重写 Agent 循环。（依赖：T036）
- [X] T038 [US2] 在 `src/code_data_factory/interaction/budgets.py`、`configs/execution/collect.yaml` 实现调用前预算守卫，覆盖批量工具/辅助终答；初始限制按 plan 的 8 次、4096/8192 词元、8192/65536 字节和 120 秒，超限明确记录。（依赖：T037）
- [X] T039 [US2] 在 `src/code_data_factory/interaction/events.py` 实现实际请求/输出/调用/返回的事件落地、完整与不完整尾部封存、取消/中断/环境故障，重试只限安全动作且不复用整任务身份。（依赖：T038）
- [X] T040 [US2] 在 `src/code_data_factory/verification/tasks.py`、`configs/quality/verifier.yaml` 实现独立结果值/引用/约束断言及依赖诊断，使用固定真值/独立公式；未知/不稳定不给确定判定，验证器不暴露为模型工具。（依赖：T039）
- [X] T041 [US2] 在 `src/code_data_factory/interaction/replay.py` 实现日志 inspect 和固定动作真实 replay 两种入口，验证冻结初始资源/工具版本、保存新尝试和差异；缺原环境不能偷偷换工具。（依赖：T040）
- [X] T042 [US2] 在 `src/code_data_factory/verification/rewards.py`、`configs/quality/reward-terminal-v1.yaml` 实现已验证 PASS→1、FAIL→0、UNKNOWN→null 的独立版本记录，过程诊断不混入终局奖励，原证据不可覆盖。（依赖：T041）
- [X] T043 [US2] 在 `src/code_data_factory/cli.py` 接入 `environment check`、`trajectory collect/inspect/replay`、`verify run`，对统一输出和所有终态进行契约核对。（依赖：T028、T042）
- [X] T044 [US2] 在合格 Linux 环境完成 100 先导任务各两次固定动作执行与至少 35 例全部金标准对照，保存 `artifacts/verifications/pilot/manifest.json`；逐任务审计依据，失败先修复并停止扩大采样。（依赖：T032、T043）
- [X] T048 [US2] 保存 `artifacts/checkpoints/us2.json` 并更新本机私有决策记录（不提交），关联原 100 任务固定动作、35 例正负对照和独立判定；复核迁移对执行语义/环境版本的影响，受影响证据按新版本重跑，未受影响才引用旧回执；明确这些资产仅用于验证/评测，模型真实采样另由 T058 验收，外部数据发布另由 T047 验收，不将任一分支证据互相替代。（依赖：T044、T108）

**Checkpoint**: 有可执行验证资产和独立结果判定；工具成功不能替代任务成功，也不能替代外部训练示范准入。

## Phase 5: User Story 6 - 扩展 RL 与长程轨迹 (Priority: P1)

**Goal**: 不重建核心即可对接一个现成训练器，并检验长程上下文、受控恢复和稀疏奖励。
**Independent Test**: 两入口固定动作等价；两任务各两次真实采样；32/128 步存读、上下文改写与恢复；
成功/全零/未知/截断四类各至少两个任务重评分。无需 RL 参数优化。

### Tests

- [ ] T049 [US6] 在 `tests/contract/test_training_consumer.py`、`tests/integration/test_long_horizon.py` 声明真实词元/输出标记、缺字段拒绝、未知奖励、32/128 步和不可恢复环境的预期行为，替身与真实运行标记分离。（依赖：T048、T108）

### Implementation

- [ ] T050 [US6] 在 `src/code_data_factory/interaction/checkpoints.py` 实现仅受控只读语料/会话工作区的状态快照与恢复，记录随机状态、父尝试和分支点；缺能力返回 unsupported，不把日志回看当恢复。（依赖：T049）
- [ ] T051 [US6] 在 `tests/fixtures/long_horizon/`、`configs/execution/long-horizon.yaml` 构建 32/128 步确定性案例，含取值依赖、大观察引用、截断前后可见输入和一次摘要替换；不训练摘要模型。（依赖：T050）
- [ ] T052 [US6] 在 `src/code_data_factory/interaction/trl_adapter.py`、`configs/execution/trl-tools.yaml` 适配 TRL 环境工厂，复用 reset/四个工具/验证器；辅助和评分方法保持私有，优先沿用上游循环，必要扩展只按已证明接口缺口补采样回调。（依赖：T051）
- [ ] T053 [US6] 在 `src/code_data_factory/interaction/sampling_records.py` 定义消费 profile、SamplingAttachment 与 CompatibilityReceipt，直接保存上游真实词元和输出 mask/策略身份；长度不等、伪身份、历史重编码或不支持的上下文重写必须拒绝。（依赖：T052）
- [ ] T054 [US6] 在 `src/code_data_factory/verification/rescore.py`、`tests/fixtures/sparse-rewards/`、`configs/quality/reward-terminal-v2.yaml` 实现固定证据重评分与按任务/尝试的奖励分布报告，两个版本差异可为零但须解释，不引入自动密集奖励。（依赖：T053）
- [ ] T055 [US6] 在 `src/code_data_factory/cli.py` 接入 `compatibility check` 三模式及 `reward rescore`，回执按接口替身、真实采样、长程/恢复逐项记录，缺真实运行不签发笼统兼容成功。（依赖：T054）
- [ ] T056 [US6] 执行两入口固定动作、32/128 步存读、上下文改写、受控恢复/不支持拒绝及四类稀疏奖励重评分，保存 `artifacts/compatibility/contract/`、`artifacts/compatibility/long-horizon/`，包括状态/哈希/词元关联检查。（依赖：T055）
- [ ] T057 [US6] 在 `configs/experiments/model-candidates.yaml`、`artifacts/compatibility/model-profile.json` 固定 Qwen3-8B 首选与 Qwen3-4B 事前备选顺序及实际 revision/模板/思考模式，完成推理/词元通道资源探针；不声称 SFT 已可训练，费用接 T010。（依赖：T012、T103）
- [ ] T058 [US6] 用 T057 模型在验证分支合格环境完成至少两个任务各两次真实训练器采样，保存 `artifacts/compatibility/sampling/`，核对实际输入输出词元、mask、版本、成本及未调用优化器；不能用成功脚本代替真实模型失败轨迹，探针输出不进入正式 SFT 池。（依赖：T056、T057）
- [ ] T059 [US6] 汇总 SC-011–013 至 `artifacts/checkpoints/us6.json` 并更新本机私有决策记录（不提交），注明后续 RL 仅增加算法/预算附件，真实长程能力与 RL 参数更新尚未验证。（依赖：T058）

**Checkpoint**: 首版强制扩展验收完成；未取得真实采样、恢复或长程证据的项保持未完成。

## Phase 6: User Story 3 - 以评测反馈调整数据并形成归因闭环 (Priority: P2)

**Goal**: 开发失败→证据/原因假设→同池数据配方；提供后续真实训练与复评所需输入。
**Independent Test**: 固定开发评测可独立验证反馈软件；真实闭环最终验收在 T084，不能要求 US3
先完整关闭才能开始依赖其配方的 US4。

### Tests

- [ ] T060 [US3] 在 `tests/contract/test_evaluation_feedback.py` 验证固定分母、失败重试、开发/test 权限、原因假设与事实分离、目标干预不被匹配消除，并拒绝最终测试引用进入反馈。（依赖：T108）

### Implementation

- [ ] T061 [US3] 在 `src/code_data_factory/evaluation/suites.py`、`configs/evaluation/tool-tasks.yaml` 构建开发/最终测试各至少 200 任务、三个族各至少 40、测试至少 50 未见组合且至少 20 独立来源—模板连通组；冻结标识/私有参考与切分登记，组不足阻断归因；工具名可不同，但与外部训练数据的能力语义对应须可解释，外部测试和本地任务均不流入 SFT 池。（依赖：T045、T060）
- [ ] T062 [US3] 在 `src/code_data_factory/evaluation/interactive.py` 实现实际逐步执行评测和 TaskSuccess@1（一次完整尝试成功率），固定全分母与系统故障最多一次原配置重试，另报有效执行覆盖、恢复/未见组合/成本/约束；未解决系统故障阻断因果结论。（依赖：T061）
- [ ] T063 [US3] 在 `src/code_data_factory/evaluation/bfcl.py`、`configs/evaluation/bfcl-local-v4.yaml` 复用 BFCL 官方评测程序，解析 `f7cf735` 完整提交及数据/许可、冻结本地多轮/无关工具子集和协议偏离；需执行不可信代码的子集隔离不通过则拒绝。（依赖：T062）
- [ ] T064 [US3] 以 T057 模型运行项目及外部开发评测，保存 `artifacts/evaluations/base-development/` 和候选池事前难度估计，模型/模板/工具版本清楚；此阶段不解锁最终 test。（依赖：T046、T057、T063）
- [ ] T065 [US3] 在 `src/code_data_factory/evaluation/findings.py`、`src/code_data_factory/evaluation/findings.sql` 使用 DuckDB 汇总错误/依赖/上下文切片，形成 Finding 的原始证据、假设、反证及置信程度，不称为已证明因果。（依赖：T064）
- [ ] T066 [US3] 在 `src/code_data_factory/datasets/feedback.py`、`configs/quality/feedback.yaml` 实现 DataAction/复验关系和发现驱动选择；首轮只在同一冻结外部合格池重选，新增外部来源/修复先重过治理进入下一候选池版本，不单独混入处理组，不启动训练数据自采样。（依赖：T065）
- [ ] T067 [US3] 在 `src/code_data_factory/datasets/recipes.py` 从外部合格池构建 RandomMatched 与 ClosedLoop 草稿，匹配来源/粗任务族/深度/长度/验证强度/基线难度，保留失败类型覆盖差异，保存联合支持、共同剔除与平衡报告至 `data/recipes/main/`。（依赖：T047、T066）
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
- [ ] T078 [US4] 复核两个视图的外部来源/修复链与无自采样混入，发布实际数据视图、批次和匹配报告并冻结 `artifacts/experiments/sft-main/experiment_plan.json`，验证报价/总预算、全部依赖及当前模型版本一致；模型备选切换时按下述“版本失效规则”重新建立相关证据后才能登记。（依赖：T047、T077）
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
- [ ] T101 将全部 FR-001–044、SC-001–018 映射到任务、测试、真实产物和当前状态，输出 `reports/final/requirements-traceability.md` 与机器清单，任何未完成强制验收保持 OPEN。（依赖：T100）
- [ ] T102 更新 `README.md` 与 `reports/final/report.md`，并同步更新本机私有决策记录（不提交）；按实际结果展示数据工程、开源复用、扩展兼容和归因，保留限制/失败；不宣称正式 RL 或长程模型收益。（依赖：T101）

## Dependencies and Execution Order

### Story Dependency Graph

```text
已完成 Foundation / US1 原软件 (T001–T032)
  -> T103–T108 契约/准入迁移 -> T045 外部试点 -> T046 治理候选池 -> T047 发布/导出
                                                  |-> US5 多节点 T087–T091
T045 + 反馈软件 -> 开发评测；T046 + T057 模型身份 -> 开发发现
T047 + 开发发现 -> T067 同池配方 -> US4 校准/六次训练/复评 -> T084 归因闭环
已完成工具验证 T033–T044 -> T048 检查点 -> US6 兼容/长程/真实采样
US4 + US5 多节点 -> US5 全谱系/报告/复现 -> 最终验收
```

T103–T108 先修分用途契约与旧发布实现，再开展真实外部试点。T045–T047 的依赖链不包含
T033–T044、T048–T059；无可执行环境/模型生成仍须完成外部数据发布。
US6 复用 T108 的记录迁移，但其真实采样不阻塞正式数据池。T057 模型身份可提前确定，不以长程
测试或采样成功解锁开发评测。T047 是数据发布回验，T084 才完成 SC-008 的真实训练闭环。
US5 多节点分支在 T047 后独立推进；不必等待训练。所有新前置关系均在下方逐项依赖中声明。

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
FR-001–004/014/018/020/022/025 的新版来源/准入部分由 T103–T108 与 T045–T047 补验；
表中的旧任务映射只覆盖原功能部分。SC-016–018 不继承旧检查点。

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
| FR-040 | T003、T012、T032、T048、T059、T070、T085、T098、T101–T103、T108 |
| FR-041 | T103–T108、T045–T047、T066–T067、T078 |
| FR-042 | T103–T108、T045、T047 |
| FR-043 | T104、T107–T108、T047 |
| FR-044 | T045–T047、T066–T067、T078 |

| 成功标准 | 关键实际验收任务 | 不能代替的证据 |
|---|---|---|
| SC-001 | T027、T031、T047、T092、T096 | 真实成员/撤销关系，不能只有空表 |
| SC-002 | T044 | 100 个独立任务、各两次真实固定动作执行 |
| SC-003 | T034、T044、T048 | 至少 35 个独立正负对照按预期分类 |
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
| SC-016 | T045–T047、T067、T078 | 真实外部非空池、100% 上游/修复追溯、零本项目采样、实际合格示范/词元非零及各阶段对账 |
| SC-017 | T104–T108、T045 | 四类独立准入/拒绝/未知/修复案例，非笼统 PASS |
| SC-018 | T104、T107–T108、T047 | 真实外部输入在无环境/无模型生成条件下独立发布及缺证据拒绝 |

## CLI Coverage

CLI 表示命令行界面；这里只映射 [命令契约](contracts/cli.md)，不增加新命令。

| 命令组 | 任务 |
|---|---|
| `source audit/revoke`、`task build`、`trajectory import` | T015–T017、T020、T027–T028、T103、T106、T108 |
| `data build --backend/--resume`、`dataset publish/export-sft` | T018–T026、T028、T103–T108、T046–T047 |
| `environment check`、`trajectory collect/inspect/replay`、`verify run` | T035–T043 |
| `reward rescore`、`compatibility check` | T049–T058 |
| `evaluate run`、`feedback build` | T060–T068 |
| `experiment calibrate/preregister/run` | T071–T079 |
| `benchmark run` | T087–T091 |
| `report build`、`evidence verify`、`reproduce` | T092–T096 |

## Implementation Strategy

### MVP First

T001–T032 的软件基础已有原范围验收，不重新勾选或扩张含义。本版最小可行交付是 T103–T108
完成准入迁移，再以 T045–T047 实际从外部数据构建训练版本与视图。T033–T044 的验证资产保留
使用，但不作为这一主线的前置条件。RL/长程、固定条件训练和分布式验收仍为完整首版必需。

### Incremental Delivery

1. T103–T108：同步派生契约，修正硬编码历史用途、可执行任务强依赖和统一 PASS 发布门禁。
2. T045–T047：审查真实外部示范、批量治理、发布/导出；数量由可用数据/覆盖/词元确定。
3. T048–T059：独立验证与 RL/长程兼容；T057 模型身份可提前，探针不成为训练数据来源。
4. T060–T085：开发评测→同池选择/配比→校准/预登记→六次训练/复评→真实归因闭环。
5. T087–T091 多节点分支与模型实验独立推进，T092–T102 汇总谱系、复现和全部需求验收。

12 周是 plan 的排期目标；按已有回执继续、遵循依赖，不为日期要求跳过门禁或扩大训练生成。

### Stop and Scope Rules

- 只暂停缺依赖的分支；保留失败产物，继续可独立完成的数据工程工作。外部数据不足优先选源和
  治理，不启动旧 T046 的自行采样；训练目标来自外部已有示范，不用本地任务或评测输出替代。
- CPU/GPU/模型服务费用统一进入项目费用视图；GPU 5000 元启动软上限、最高可论证 10000 元和
  15% 储备沿用 plan，外部费用需独立已授权上限，不据任务数量增加预算。
- 实际上游接口不足时记录具体缺口，优先适配已有扩展点；不得直接转向自建平台或新增第二套引擎。
- 模型收益不是预设结果；数据处理成功、扩展夹具通过或正奖励不能替代六次训练与独立评测。
- 32/128 步固定案例、真实采样、64 GiB 多节点、同池三种子和归因闭环都不可静默删为可选。
- 每个故事检查点须在本机私有决策记录（不提交）中解释实际机制、替代、取舍、结果与证据，或明确
  记录无新增工程议题的回执。任务完成、检查点完成和整个项目完成分别判断。
