# 租用 Linux 环境恢复与依赖验证契约

**适用范围**：规格 2.0 的 T003、T012，以及任何需要在 OpenBayes 或其他租用 Linux 实例恢复本项目的
后续任务。

**目的**：用可观察、可停止、无凭据的步骤恢复冻结依赖，避免把新实例误判为旧环境续接，避免在坏的
下载链路上消耗租用时间，并把依赖读写证据与隔离执行、Ray、训练和模型价值证据严格分开。

本契约不授权关机、续租、创建实例、修改计费设置、上传私有数据或使用任何凭据；这些操作必须由用户
另行明确授权。

## 1. 已验证基线与不可外推项

2026-09-08 的替换 OpenBayes 实例为 Linux 6.8.0-138-generic、x86_64、glibc 2.35。冻结的 Python
3.12.13 环境通过依赖兼容性检查，并完成 Pydantic/PyArrow Parquet 写入与读回。实际探针为
`artifacts/dependencies/linux_probe.json`，其 SHA-256 记录于依赖清单和 foundation checkpoint。

该结果仅为 `SOFTWARE_VALIDATED`：证明冻结依赖在该 Linux 实例安装、兼容和基础 Parquet 读写可用；
不证明受限隔离、真实 Ray 集群、模型采样、参数更新、训练完成或模型收益。

同日的新租用实例虽然仍将 `/openbayes/home` 挂载为 Ceph 存储，但不包含先前的 checkout、uv、下载的
Python、缓存或 `.venv`。因此，`/openbayes/home` 只可在**实际复用同一 workspace/storage identity** 时
被视为加速缓存；Git 或另一份可信源码/锁文件传输才是跨新实例的恢复来源。不要根据相同账号、主机名
或文档泛称直接声称已恢复旧环境。

## 2. 必须保存的非敏感记录

每次远端恢复须生成或更新一份恢复回执，至少包含：

1. workspace 分类：`NEW_INSTANCE_RECOVERY`、`VERIFIED_SAME_WORKSPACE_REUSE` 或 `UNVERIFIED`；
2. 项目与锁文件身份（路径、版本或 SHA-256，不含私有 URL/令牌）；
3. 平台、架构、解释器版本、持久挂载和可用磁盘；
4. 候选下载源、代表性锁定 Linux wheel、每源固定观察窗口和完成/失败/超时结果；
5. 实际 artifact 下载路径是否与选择的源一致；
6. 首次 bootstrap、第二次 bootstrap、依赖兼容性和 Parquet probe 的结果；
7. 证据文件路径、SHA-256、时间和证据层级；
8. 未执行、未授权或仍不能证明的能力。

禁止记录 SSH 密码、access token、会话 cookie、原始私有日志、私有数据正文或完整命令行中的秘密。

## 3. 新实例恢复协议

### 3.1 先分类，再下载

在安装任何完整依赖前，读取并记录：内核/架构、Python/uv 版本、`/openbayes/home` 的挂载、可用磁盘，
以及 checkout、持久 uv、下载 Python、缓存、`.venv` 是否存在。任何预期路径缺失时都按
`NEW_INSTANCE_RECOVERY` 处理，不得把它写成“重启恢复”。

新实例必须先将含 `pyproject.toml` 和 `uv.lock` 的可信 checkout 放到：

```text
/openbayes/home/code-data-factory
```

不得从 `/tmp`、`/root` 或 `/opt/venv` 作为需要跨启动保留的项目、解释器、虚拟环境、缓存或证据目录。

### 3.2 先做有时间上限的镜像预检

选择一个代表性的、体积足以暴露链路问题的锁定 Linux wheel，对每个候选源使用相同的固定连接/读取
观察窗口（默认 10–20 秒；如需变更，记录原因）。结果只能是 `COMPLETED`、`FAILED` 或 `TIMED_OUT`。
在预检没有成功源时，停止全量安装并报告阻塞；不得让无法证实有进展的全量下载无限等待。

2026-09-08 的同机参考样本是 45.4 MiB 的 `pyarrow==23.0.1` Linux wheel：PyPI/Fastly 180 秒超时、
清华约 5 秒、华为云约 4 秒。华为云是当前默认源，因为该次实测最快；它不是对所有区域、日期或实例
的永久结论。实例、区域、镜像或时间发生实质变化时必须重测。

### 3.3 验证真正的 artifact 路径

设置 index 不等于所有锁定文件都会通过该 index 下载。`uv.lock` 可能包含原始 distribution artifact URL，
`uv sync --default-index ...` 仍可能访问不健康的 Fastly/PyPI 路径。对至少一个锁定包确认真正请求的
artifact 路径；若它绕过已测成功的镜像，立即停止该下载策略。

本项目的允许恢复路径是：从冻结锁导出带哈希 requirements，用
`uv pip install --require-hashes` 从已测成功的源安装第三方包，然后离线构建项目自己的非 editable
wheel。此流程不得放松 `uv.lock` 中的版本或哈希约束。

### 3.4 首次启动、重复启动与兼容性

从可信 checkout 执行：

```bash
bash scripts/openbayes/bootstrap.sh
```

脚本把 Python、cache、`.venv` 和 probe 放在 `/openbayes/home` 下，并以保留既有环境的方式创建虚拟
环境。首次成功后必须立即再执行一次相同命令；第二次结果才是“当前 workspace 内已有环境可重复启动”
的证据。不得在没有明确理由和授权时删除 `.venv` 或用清空方式掩盖第二次启动失败。

完成后使用：

```bash
/openbayes/home/.pylibs/bin/uv pip check --python .venv/bin/python
```

检查依赖兼容性。uv 创建的虚拟环境不保证包含 pip，因此不得把 `python -m pip check` 缺失误判为依赖
失败，也不得仅为此检查额外安装 pip。

## 4. 离线 wheelhouse 的使用边界

仅当新鲜的同机镜像预检确实慢、受限或计费敏感时，才考虑 wheelhouse。wheelhouse 必须匹配 x86_64
Linux 与 CPython 3.12，并与当前 `uv.lock` 身份绑定；不得复制 macOS `.venv` 或 macOS wheel。锁文件变化后，
原 wheelhouse 必须重新验证或重建。它节省远端下载时间，但引入额外的传输、存储和维护成本，不能默认
优于已测高速镜像。

## 5. 失败关闭矩阵

| 观察 | 必须动作 | 禁止动作 |
|---|---|---|
| 新实例没有旧 `/openbayes/home` 内容 | 传输/克隆可信源码和锁，再走恢复协议 | 假设旧环境仍在或手工重建未锁定环境 |
| 默认源超时或缓慢 | 执行短时镜像预检，选择有成功记录的源 | 持续等待无进展的全量下载 |
| 实际 artifact 绕过选择的源 | 切换到 hash-pinned 安装路径 | 声称仅设置 `--default-index` 已保证镜像生效 |
| 已有 `.venv` 导致启动失败 | 修复并复验保留既有环境的重复启动 | 未经授权删除/清空环境 |
| 基础 probe 通过 | 保存软件级证据和限制 | 标为隔离、Ray、训练或模型收益完成 |
| 需要关停当前 workspace 才能验证持久性 | 请求明确授权 | 为测试便利自行关停用户租用实例 |

## 6. 验收与交接

一次远端依赖恢复只有在以下条件同时满足时，才可记录为 Linux `SOFTWARE_VALIDATED`：

1. workspace 分类、锁文件身份和平台事实均已保存；
2. 至少一个候选下载源在固定窗口内完成代表性锁定 wheel，实际 artifact 路径已检查；
3. 第三方依赖安装保持冻结版本和哈希；
4. bootstrap 在同一已恢复 workspace 连续成功两次；
5. 依赖兼容性与 Parquet probe 均通过，并保存结果 SHA-256；
6. 回执没有秘密，且明确列出隔离、分布式、训练和模型价值仍未验证。

后续 agent 交接时应引用本契约、[OpenBayes 环境指南](../../../docs/openbayes-environment.md)、
[证据日志 CH-010](../../../docs/evidence-journal.md#ch-010租用容器重启后仍可重建锁定依赖)及实际 probe，
而不能只说“环境已配置”。

## 7. GitHub 来源测试与 `main` 合并门禁

远端 Linux 测试的源码必须来自 GitHub 的非 `main` 候选分支，而不是 Mac 工作区归档或 SCP 复制。一次
候选的最小可审计身份是 `branch_name`、GitHub candidate SHA、来源方法、锁文件 SHA，以及 Git checkout SHA
或 GitHub exact-commit archive SHA-256。Git checkout 测试开始前 checkout SHA 必须等于 GitHub candidate SHA。

标准顺序如下：

1. 从新鲜 `origin/main` 创建命名清晰的非 `main` 测试分支；所有代码、依赖、配置和可运行文档只在该分支
   提交。
2. 本地只暂存审计过的路径，运行适当的本地检查，再把候选分支推送到 GitHub。
3. OpenBayes 优先在独立、干净的测试 checkout 中从 GitHub clone/fetch 该分支，核对 checkout SHA 与 GitHub
   candidate SHA 一致后，才执行测试。若 Git smart-HTTP 在有界时间内失败、但 GitHub API 可解析 branch ref
   且 Codeload 可下载完整 candidate SHA，则可改为 `GITHUB_EXACT_COMMIT_ARCHIVE`：记录 API branch-ref SHA、
   exact-commit API 结果、完整 SHA 的 Codeload URL、archive SHA-256 和解压目录；不得下载可变 branch archive。
   两种来源方法均须在干净目录执行 bootstrap、第二次 bootstrap、依赖检查、Linux probe 及任务要求的测试。
4. 任一远端检查失败时，`main` 不变；修复后的新 SHA 必须重新推送、重新从 GitHub 获取并重测。
5. 全部远端检查成功后，再次获取 `origin/main`。若它移动，候选必须基于新 tip 重建并重测；若未移动，
   仅允许将 `main` fast-forward 到同一个已测 SHA 后推送。禁止把未测 merge commit、远端本地副本或
   force-push 写入 `main`。

完整的通用约束见根目录 [AGENTS.md](../../../AGENTS.md#github-to-openbayes-test-gate)。该 Git 交付门禁不改变
本契约第 1 节的证据边界。
