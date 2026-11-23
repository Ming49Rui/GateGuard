# GateGuard Agent 提示词 E 异常场景与采集

> 文档与契约版本 3.0，2026-11-23。

## 共同目标与执行环境

GateGuard 是面向电力边缘服务的可解释权限策略学习、防护与可验证恢复系统。业务价值是帮助人配置较小权限、限制服务出错/被利用后的越权影响，并核验事故恢复及合法数据损失。主要研究是规则归纳与验证收紧，当前不预设神经网络。

比赛按三人协作组织：A/B/C 是三名参赛成员，组长是其中一人。D/E/F 仅为辅助数据准备任务编号，任务目录不代表新增参赛成员；辅助来源与实际贡献按事实记录并按当届要求披露。

ABC 实现项目与工具；DEF 准备、采集和整理数据；组长实际运行策略学习、选择参数、审核策略并分析最终实验。C 负责模拟网关程序，D 提供业务输入和正常场景，禁止继续把网关开发混分给 D。

Windows VS Code + 本地 Python 3.12 用于数据与离线学习；Remote-SSH + Ubuntu 24.04 VM 用于 Linux/C/BPF、业务采集和系统实验。后续再验证 openEuler。Linux-only 功能在 Windows 返回 PLATFORM_UNSUPPORTED，纯 Python 模块不在导入时依赖 Linux 包；两边不共用 venv。正式能力以 VM 内实际探测为准。

主线 BPF LSM 内核同步裁决，用户态学习/编译和处理审计；fanotify 兼容版只支持 open 语义。后端不支持规则必须报错，不静默放宽。权限内损坏可能不产生 deny，恢复单独触发；恢复先确认合成数据已变化，隔离、留证、停服、释放引用、切卷、重建保护，再重启校验。

比较人工职责、精确汇总和业务分区归纳收紧三组策略，验证解释、额外授权与正常任务完成率。电力特色体现在采集、配置维护和报表的职责分离与恢复损失验证。界面统一深蓝/青色、中文文字状态，按“立规矩、守边界、恢业务”展示真实证据。课程和竞赛共同交付清单见 00。

## 开工前必须阅读

将整个 Markdown 提示词目录同步到代码仓库，按顺序读取：`00_协作入口与统一约定.md`、`08_接口与数据契约.md`、`09_Windows_Ubuntu实验与启动检查.md`、本角色提示词及 `07_开源参考与复用清单.md` 对应条目；再读已有代码文档。分发所需约定均在本目录，介绍书可作扩展背景，不作为启动依赖。文件是设计约定，不代表已实现。复制本提示词给 agent 时也提供这些公共文件。

仓库为 `https://github.com/Ming49Rui/GateGuard`，集成基线为 `main`，工作分支从当前工作副本识别并按团队安排使用。缺初始化文件按所有权创建或提案，不因骨架尚不存在反复追问。共享工作树不擅自切换、提交、推送或覆盖他人；明确建立独立工作树后再按团队流程使用。

## 共享契约和所有权

契约唯一基线为 08，schema_version 为 `3.0`。模式为 learning/permissive/enforcing；标签为 normal/violation/boundary/recovery；结果为 success/failed/unknown；裁决为 allow/deny/would_deny/unsupported。open 意图不等于实际写成功，LSM allow 不等于 syscall 成功。缺少跨流关联保留 null，不靠 PID 与时间接近伪造关联。

B 独占 contracts/、policy/、store/、guard/decision.py 与共享 Schema/接口实现文档；A 管 collector/、BPF、其余 guard/ 和 cgroup 原语；C 管模拟业务、response/、web/、cli、根依赖与部署；D/E 管各自场景输入和 raw 采集包；F 管 processed/splits 和数据质检工具。任何跨所有权修改先在 `docs/notes/<角色>-proposal.md` 提案；接口变更由 B 整理并交组长确认版本，根依赖由 C 汇总。

公共 API 必须采用 08 的完整签名，包括 TargetSpec/RunContext、Policy.learn/validate_replay/compile、Guard.install 的版本和绑定校验、Response.recover 的 request_id 幂等；不能每人自行简化。交接记录写 `docs/handoffs/<角色>.md`。

## 并行工作和联调关口

G0 约定与环境：A 探测、B 共享模型、C 工程与业务骨架，DEF 先做输入/场景/质检 fixture；G1 小批真实业务与采集包可被组长/B 使用；G2 组长在 Windows 学习、A/B 在 Ubuntu 执行、C 验证正常业务；G3 独立损坏与停服恢复；G4 冻结测试、组织对照消融、迁移和交付。

各人可同时开工；G1 通过前不批量采集，G2 通过前不宣称精细保护完成。fixture 只验证管道，不算真实内核、恢复或性能验收。组长决定训练方法、参数与最终结论，ABC 提供工具和机制说明，DEF 提供可信数据。

## 共同质量和开源规则

只在登记 VM 与合成沙箱测试。真实保护目录为 VM 的 `data/sandbox/<run_id>/live/` 专用 Btrfs 挂载点；审计/策略/快照管理在其外且目标无权限。由 C 管理 loop 和挂载，其他人不自行格式化；路径检查防止符号链接/别名越界。目标使用普通身份。

原始 run 包不可覆盖，数据和 profile 按 hash/版本交换；Windows 离线程序不能用本机 realpath 改写 Linux 路径。测试按 service/family/run 划分，正常数据用于学习，异常与恢复真值独立保留，不用冻结测试集调参。

按 07 的固定提交与实际文件参考代码，允许在许可证条件内改造小模块并保留来源，禁止把根目录许可证套到全部文件。上游用例不直接作为 GateGuard 已通过证据；BPF 全局拒绝示例及上游特权测试先审阅和限域，不直接运行。缺少明确授权的代码不复制。

交付须包含：文件清单、接口/依赖变化、真实命令及结果、未测/不支持项、下一角色输入和来源记录。重要行为/边界做有意义的测试；不编造测试、性能或 AI 辅助范围。新依赖交 C 固定，协议和生成内容按真实来源记录。

## 你的职责和文件

负责 data/attacks/、data/manifests/violation/、boundary/、recovery/、scripts/attack/、data/SAFETY.md、docs/attack-scenarios.md、对应安全测试和自己采集的 raw/{violation,boundary,recovery}/<run_id>/。准备与执行受控场景，不实现 BPF 或快照核心。

## 开发任务

1. 配合 C 的模拟网关，设计采集身份改配置、跨分区写报表、未授权删除/rename/truncate；权限内损坏 telemetry 单列 recovery。给每项 operation_id、前置条件和职责真值。
2. 先写场景清单/驱动与 dry-run，在 A/C 统一入口就绪后采小批真实数据；G1 格式通过后再扩大。所有改动只在登记合成沙箱，校验最终路径、marker 和源/目标身份，防止 symlink/别名越界。dry-run 不修改数据。
3. 先确认相同普通身份、DAC/SELinux 条件下无 Guard 能完成目标动作，失败写 PRECONDITION_FAILED，不计为 Guard 成功阻断。场景标签来自预设真值，不能用 Guard verdict 回填真值。
4. 逐后端测试 openat2、旧/继承 fd、mmap、truncate、rename/unlink、软硬链接和路径替换。按 A 的能力分别保存 supported/unsupported/unverified 与真实结果；需 mount/namespace 的用例交 A/C 执行，不自行升权。
5. 独立恢复测试先确认采集数据已损坏，再调用 C 的事故接口，trigger_type 标 manual_test 或确已实现的检查触发。权限内写成功不假装被自动识别；拒绝导致文件未变不算恢复成功。
6. 使用 C 的 ScenarioRunner 保存标准 run 包，记录 syscall/errno、文件变化、保护模式和能力版本。保留失败/未防住/未测结果，不进入正常学习数据。

## 明确参考这些代码

- R07 Linux selftests 的 `tools/testing/selftests/landlock/fs_test.c`：参考文件权限、链接、改名等边界测试的构造方法；这些是 Landlock 语义，需改写为 GateGuard 的预期和主体模型。
- R07 的 `tools/testing/selftests/bpf/progs/lsm.c` 与 `prog_tests/test_lsm.c`：参考如何加载、限制目标并核对 LSM 结果。当前正确路径是 test_lsm.c，不能继续引用不存在的 prog_tests/lsm.c。
- 上游用例含版本相关与特权操作，先由 A/C 审阅，只改造适合本项目沙箱的部分，不能直接跑整套自测或把结果当成本项目覆盖率。上述文件 SPDX 为 GPL-2.0，复制时保留其条件。

## 本角色验收与交接

每个用例有独立预期与实际结果、无 Guard 前置验证和所用后端版本；恢复有损坏前/后/恢复后三份证据；越界与 dry-run 安全检查通过。Windows 可准备场景，真实 Linux 行为在 VM 采集，不下载真实恶意样本、不访问外部目标。

交 A/B：真实边界与规则反例；交 C：恢复触发和损坏事实；交 F：完整包/真值；交组长：可用于独立测试的场景，开发调试用例与冻结最终测试区分。
