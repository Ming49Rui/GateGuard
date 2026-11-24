# GateGuard Agent 提示词 D 电力数据与正常采集

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

负责 data/inputs/、data/workloads/、data/manifests/normal/、scripts/data/prepare_power.py、docs/data-normal.md 和自己采集的 data/raw/normal/<run_id>/。你准备业务输入、场景配置和执行采集，不编写 examples/power_gateway/ 或系统核心。processed/splits 由 F 唯一维护。

## 开发任务

1. 先读 11 的业务职责和 12 的交接规范，与 C/B 明确输入、文件布局、正常生命周期及必要动作。电力数据只驱动业务，不承载主机权限真值；设备 ID 不自动产生授权。
2. 保留公开输入原文件、许可与 hash；首轮规范导出 UTF-8 JSONL。每条字段固定为 record_id、source_time、device_id、voltage_v、current_a、active_power_kw、quality、source_type；格式/空值/单位/时区/有限数值规则见 08/12，不另创同义字段。
3. 维护 input-provenance.json：来源、字段/单位/时区转换、缺失与异常处理、生成器/seed、原始行到 record_id 的映射、输入输出 hash。UCI 回放不伪称变电站记录；pandapower 仅作可选 synthetic 输入，不把未提供的量补造为实测。
4. 准备 startup/sampling/query/report/rotation/reload/restart/maintenance 场景；实际支持范围与 C 对齐。配置维护独立主体，记录跨日期、低频需求和轮转的源/目标动作；业务阶段只辅助分析，不当作请求自报授权条件。
5. G0 可清洗、写 manifest 与 fixture；G1 用 C 的统一入口和 A 的真实 collector 小批采集，再交 F/B 准入。每包包含 08 的原始事件、独立结果、规格引用、元数据、文件真值和校验和；工具未实现不造实测结果。
6. normal 中失败/unknown 与数值缺失如实保留，成功但冲突已知职责的记录交 B/C 核查，不自动进入授权训练。原始 run 不覆盖，修订用新版本并记原因。
7. 提交 service/family/run、seed、输入派生与 comparison 关系和业务覆盖表，供 F 分组。数据量以多样性与生命周期覆盖为准，不以重复事件充数量；独立 normal 测试不得参与后续选参。

## 明确参考这些项目

- R06 pandapower：优先作为 Python 依赖使用；`pandapower/networks/cigre_networks.py` 参考低压/中压网络构建，`pandapower/timeseries/run_time_series.py` 与 `doc/timeseries/timeseries_example.rst` 参考时序输入和输出组织。你生成离线业务输入，仿真库不必运行在守护关键路径。
- UCI 官方数据页见 07；数据授权与下载工具授权分别登记。公开电力 CSV 只提供业务输入，权限学习仍需在 Ubuntu 采真实文件事件。
- 仅准备数据和配置，若 C 的输入接口需要变更写提案；不另起一套网关实现。

## 本角色验收与交接

输入可复现、来源/单位/缺失值清楚；normal 场景覆盖业务生命周期；标准包通过 F 的结构/hash/真值核验；数据未把模拟物理值冒充真实设备采集。Windows 可完成准备，真实主机事件在 VM 采集。

交 C：输入样例、字段单位、场景参数和期望业务结果；交 B/组长：正常访问与职责证据；交 E：可安全破坏的合成记录；交 F：完整 raw 包与 family/seed。你的数据交付不以训练效果好坏删改原始结果。
