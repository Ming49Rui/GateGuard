# GateGuard Agent 提示词 C 工程与业务集成

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

实现 examples/power_gateway/（模拟网关代码归你）、response/、web/、cli.py、__main__.py、deploy/、根依赖/构建入口、scripts/install/rescue/demo/setup_sandbox，以及 README/design/threat-model/rollback/ui-style/provenance/demo 文档和集成测试。不修改 A/B 的核心模块或 DEF 数据工具；调用其公开 API。

## 开发任务

1. 建立可安装工程、Windows/Linux 分离依赖、CLI 门面和文档。离线子命令在 Windows 可运行；Linux-only 命令返回约定错误。数据目录/输出目录可配置，版本锁定，不写死某成员电脑路径。
2. 编写模拟电力网关，消费 D 提供的标准化记录，支持采样、查询、报表、配置重载、轮转、优雅退出与健康检查；主体职责为采集/报表/维护，启动身份及 cgroup 与 A 联调。D 不承担应用程序主体开发。
3. 业务仅操作固定逻辑分区，不提供任意路径读写或执行接口。实现 Gateway.health，包含实际采样/查询/报表结果；quiesce/flush/业务序号供快照记录。外部电力数据缺失或单位错误返回可解释错误。
4. 实现 ScenarioRunner.run，管理登记实验沙箱与目标，调用 A 采集，执行受控场景驱动，输出 08 的标准 run 包。E 提供异常驱动/参数，DEF 通过同一门面采集，不复制特权操作。drivers 用固定命令参数，不拼用户 shell。
5. 只在登记 VM loop 文件中创建 Btrfs 子卷，live 独立挂载，管理快照/审计位于保护外且目标无权访问。格式化、删除和卸载前核对绝对路径、设备、marker、subvol ID；禁止真实系统盘。
6. 实现 Incident 状态机及 Response.recover/status：隔离并确认、留证、调用 A 的 terminate 等退出、释放 fd/cwd/mmap/监听、卸载切卷、重建 A/B 的 binding 与保护、启动并校验。默认不要求被冻结的可疑进程执行优雅退出；确需解冻时先按 08 验证独立隔离。EBUSY 不用 lazy unmount 掩盖，失败保留现场。
7. baseline/periodic/incident 分开，incident 不自动可信，periodic 可能污染；恢复点有审核和校验条件。记录内容、声明元数据、保护重建、业务健康、RTO/RPO 与合法记录/字节损失；request_id 幂等，异步接受不等于成功。
8. 控制台采用深蓝/青色和文字状态，围绕“立规矩、守边界、恢业务”。显示来源解释、策略 diff、真实事件、恢复点影响和报告。Flask 普通用户、回环绑定，经 SSH 转发在 Windows 浏览器访问；鉴权 Unix socket 助手只接受登记动作和资源。
9. systemd 分离业务/守护/Web。watchdog 有真实通知才启用；故障清理不能在保护失效时放行可疑进程。记录 Windows 与 VM 解释器、依赖和源码同步办法。
10. 保留过程历史、开源来源、自研增量、教学说明和演示视频链接；三条展示分别为正常学习、越权拒绝和独立损坏恢复。配合组长进行最终评测，不替组长冻结训练参数。

## 明确参考这些代码

- R04 Snapper 的 `snapper/Btrfs.cc` 与 `snapper/Comparison.cc`：参考快照生命周期和差异检查。优先借设计、通过现有命令编排，不直接引入其整套 C++/DBus 系统。
- R05 btrfs-progs 的 `cmds/subvolume.c`：核对创建、查看和删除语义；以系统安装的 btrfs CLI 为运行依赖。`libbtrfsutil/python/tests/test_subvolume.py` 可参考测试组织，其文件授权与根目录不同。
- 上述代码不替你实现 cgroup 停服、旧引用释放、恢复后 BPF 重绑定、业务健康和合法损失报告，这些是 GateGuard 必须补齐的工程贡献。

## 本角色验收

G0 工程/业务能启动；G1 DEF 通过统一场景入口得到合格真实 run；G2 Windows profile 回传可安装且正常业务通过；G3 有损坏前后证据，切卷后保护和业务均核验，故障不伪报成功。普通面板不能执行任意特权命令，恢复重复请求不覆盖现场。

交 A：目标生命周期/关闭监听时机；交 B：存储/CLI 参数需求；交 DEF：场景启动、健康、采集/恢复命令；交组长：完整复现与最终演示入口。
