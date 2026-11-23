# GateGuard Agent 提示词 D 电力数据与正常采集

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

负责 data/inputs/、data/workloads/、data/manifests/normal/、scripts/data/prepare_power.py、docs/data-normal.md 和自己采集的 data/raw/normal/<run_id>/。你准备业务输入、场景配置和执行采集，不编写 examples/power_gateway/ 或系统核心。processed/splits 由 F 唯一维护。

## 开发任务

1. 先准备公开电力输入并保留来源、许可、原始 hash、字段/单位、清洗规则和缺失值报告。推荐 UCI 家庭用电数据作采集回放输入，标明它不是变电站记录；可选 pandapower 配电网仿真，输出明确标 synthetic。
2. 与 C 冻结业务输入：每条至少 source_time、device_id、voltage_v、current_a、active_power_kw、quality/source_type；没有来源的量为 null 或明确生成，不能把同一户复制成多台真实设备。单位不能仅改列名，例如标幺电压转换必须有相应基准。
3. 从 C 的网关功能准备正常场景配置：启动、采样、不同速率、查询、报表、跨日期、日志轮转、独立维护身份更新配置、异常退出重启。记录职责真值和必要操作，配置维护权限不交给采集主体。
4. G0 可先清洗数据、写 manifest 和校验 fixture；G1 使用 C 的 ScenarioRunner/CLI 与 A collector 采一小批真实数据，交 F 和组长/B 检查。通过后再扩大场景和重复次数，避免仅靠大量重复记录充数据量。
5. 通过统一入口保存 events/outcomes/manifest/metadata/initial/final/checksums，不覆盖原始 run。正常运行中的失败尝试如实保留，不能标为成功；异常场景不混进授权训练。
6. 将数据/场景按 service/family/run 组织，给 F 划分；同一服务的验证变化可用不同日期、速率和生命周期参数。额外 nginx 服务必须有自己的训练和 profile。

## 明确参考这些项目

- R06 pandapower：优先作为 Python 依赖使用；`pandapower/networks/cigre_networks.py` 参考低压/中压网络构建，`pandapower/timeseries/run_time_series.py` 与 `doc/timeseries/timeseries_example.rst` 参考时序输入和输出组织。你生成离线业务输入，仿真库不必运行在守护关键路径。
- UCI 官方数据页见 07；数据授权与下载工具授权分别登记。公开电力 CSV 只提供业务输入，权限学习仍需在 Ubuntu 采真实文件事件。
- 仅准备数据和配置，若 C 的输入接口需要变更写提案；不另起一套网关实现。

## 本角色验收与交接

输入可复现、来源/单位/缺失值清楚；normal 场景覆盖业务生命周期；标准包通过 F 的结构/hash/真值核验；数据未把模拟物理值冒充真实设备采集。Windows 可完成准备，真实主机事件在 VM 采集。

交 C：输入样例、字段单位、场景参数和期望业务结果；交 B/组长：正常访问与职责证据；交 E：可安全破坏的合成记录；交 F：完整 raw 包与 family/seed。你的数据交付不以训练效果好坏删改原始结果。
