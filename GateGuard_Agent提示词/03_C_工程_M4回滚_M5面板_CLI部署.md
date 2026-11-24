# GateGuard Agent 提示词 C 工程与业务集成

> 文档与契约版本 3.1，2026-11-24。

## 共同目标与执行环境

GateGuard 是面向电力边缘服务的 Linux 文件权限策略生成、访问控制与可验证恢复工具，定位于操作系统应用开发赛道的系统工具方向。主要解决服务文件权限配置与维护困难、收紧代价缺少验证依据、损坏恢复结果难核验三个问题。通过业务职责与正常行为证据生成候选策略，以真实内核拒绝和恢复证据验证价值；不把电压异常当越权。

比赛按三人协作组织：A/B/C 是三名参赛成员，组长是其中一人。D/E/F 仅为辅助数据准备任务编号，任务目录不代表新增参赛成员；辅助来源与实际贡献按事实记录并按当届要求披露。

ABC 实现项目与工具；B 负责策略研究设计、实现与实验方案，组长组织运行、审定参数/发布及最终结论，两者可由同一人承担。D/E/F 为三项辅助数据任务，按 12 准备、采集、质检和整理。C 负责模拟网关、可信主体/资源映射，D 不承担网关主体开发。

Windows VS Code + 本地 Python 3.12 用于数据与离线学习；Remote-SSH + Ubuntu 24.04 VM 用于 Linux/C/BPF、业务采集和系统实验。后续再验证 openEuler。Linux-only 功能在 Windows 返回 PLATFORM_UNSUPPORTED，纯 Python 模块不在导入时依赖 Linux 包；两边不共用 venv。正式能力以 VM 内实际探测为准。

主线 BPF LSM 内核同步裁决，用户态学习/编译和处理审计；fanotify 兼容版只支持 open 语义。后端不支持规则必须报错，不静默放宽。权限内损坏可能不产生 deny，恢复单独触发；恢复先确认合成数据已变化，隔离、留证、停服、释放引用、切卷、重建保护，再重启校验。

比较人工职责、精确汇总、简单目录归纳和自研约束归纳收紧四种实验配置，知识输入与执行语义如实披露。电力特色落实在采集/报表/维护职责、生命周期和合法数据损失验证；成熟系统机制不单独算创新。B 的具体搜索、评分、权重和阈值待后续算法讨论。界面深蓝/青色、中文状态，围绕“立规矩、守边界、恢业务”。

## 开工前必须阅读

将整个 Markdown 提示词目录同步到代码仓库，先读 00、08、11 业务与权限依据、12 数据交接规范、09 环境，再读本角色与 07 对应条目；这些文件均在当前目录。介绍书为扩展背景，不是分发启动依赖。文件均为待实现约定，保留未测/不支持状态。

仓库为 `https://github.com/Ming49Rui/GateGuard`，集成基线为 `main`，工作分支从当前工作副本识别并按团队安排使用。缺初始化文件按所有权创建或提案，不因骨架尚不存在反复追问。共享工作树不擅自切换、提交、推送或覆盖他人；明确建立独立工作树后再按团队流程使用。

## 共享契约和所有权

契约唯一基线为 08，schema_version 为 `3.1`。模式为 learning/permissive/enforcing；标签为 normal/violation/boundary/recovery；结果为 success/failed/unknown；裁决为 allow/deny/would_deny/unsupported。open 意图不等于实际写成功，LSM allow 不等于 syscall 成功。缺少跨流关联保留 null，不靠 PID 与时间接近伪造关联。

B 独占 contracts/、policy/、store/、guard/decision.py 与共享 Schema/接口实现文档；A 管 collector/、BPF、其余 guard/ 和 cgroup 原语；C 管模拟业务、response/、web/、cli、根依赖与部署；D/E 管各自场景输入和 raw 采集包；F 管 processed/splits 和数据质检工具。任何跨所有权修改先在 `docs/notes/<角色>-proposal.md` 提案；接口变更由 B 整理并交组长确认版本，根依赖由 C 汇总。

公共 API 必须采用 08 的完整签名，包括 TargetSpec/RunContext、Policy.learn/validate_replay/compile、Guard.install 的版本和绑定校验、Response.recover 的 request_id 幂等；不能每人自行简化。交接记录写 `docs/handoffs/<角色>.md`。

## 并行工作和联调关口

G0 并行确认 11 的主体/资源/授权规格与粗粒度约束首版，A 探测、B 模型/fixture、C 工程与身份/业务骨架，DEF 按 12 准备输入/场景/质检；G1 小批真实包准入后扩大；G2 Windows 学习、Linux 编译安装与正常业务；G3 独立损坏恢复；G4 冻结对照/消融、迁移与交付。

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
11. 与 B 在 G0 发布 11 的 SubjectCatalog/ResourceCatalog/BusinessSpec 首版及实际进程图。不同策略职责使用可区分的普通进程/受控 cgroup；如需同进程集中数据库则明确主机保护粒度，不能宣称记录级或 API 用户级鉴权。
12. 按 08/12 校验 record_id、UTC/单位/quality/source_type，保存输入 hash 与业务序号。资源布局由受信启动配置固定，数据内 device_id 不自动创建授权；配置原子替换与轮转的 create/rename/remove 必要动作先登记，业务 phase 不自行动态提权。
13. 统一场景入口输出 spec_refs、Outcome、metadata、文件事实和完整 checksum；无 Guard/执行配对用 comparison_id 和等价独立初态。给 DEF 真实命令、已实现功能和未支持项。为 F 留原始路径与对象映射证据；不要求 DEF 直接调用特权原语。

## 明确参考这些代码

- R04 Snapper 的 `snapper/Btrfs.cc` 与 `snapper/Comparison.cc`：参考快照生命周期和差异检查。优先借设计、通过现有命令编排，不直接引入其整套 C++/DBus 系统。
- R05 btrfs-progs 的 `cmds/subvolume.c`：核对创建、查看和删除语义；以系统安装的 btrfs CLI 为运行依赖。`libbtrfsutil/python/tests/test_subvolume.py` 可参考测试组织，其文件授权与根目录不同。
- 上述代码不替你实现 cgroup 停服、旧引用释放、恢复后 BPF 重绑定、业务健康和合法损失报告，这些是 GateGuard 必须补齐的工程贡献。

## 本角色验收

G0 工程/业务能启动；G1 DEF 通过统一场景入口得到合格真实 run；G2 Windows profile 回传可安装且正常业务通过；G3 有损坏前后证据，切卷后保护和业务均核验，故障不伪报成功。普通面板不能执行任意特权命令，恢复重复请求不覆盖现场。

交 A：目标生命周期/关闭监听时机；交 B：存储/CLI 参数需求；交 DEF：场景启动、健康、采集/恢复命令；交组长：完整复现与最终演示入口。
