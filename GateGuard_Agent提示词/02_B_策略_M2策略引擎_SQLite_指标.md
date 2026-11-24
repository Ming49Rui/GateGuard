# GateGuard Agent 提示词 B 策略与学习工具

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

实现 src/gateguard/contracts/、policy/、store/、guard/decision.py，schemas/、对应关键测试、docs/data-contract.md、interfaces.md、policy.md，以及供组长使用的学习配置示例。根依赖由 C 汇总。你同时负责研究设计、方法实现与实验方案，组长组织运行、审定参数/发布与最终结论；两种职责可由同一人承担。

## 开发任务

1. G0 先与 C 核对 11 的模拟业务、主体和资源布局，D/E 提交必要需求与反例，汇总 BusinessSpec/LearningConstraints/资源与主体目录。将待确认假设与批准规格分开，不能用运行成功直接证明授权。
2. 发布 08 的 schema 3.1 共享模型、JSON Schema、完整 fixture 与校验函数，含规范引用、Outcome、NormalizedEvent、学习/评测视图和错误码。fixture 明确标记，不算真实系统证据；不能只把 3.0 版本字符串改掉。
3. 负责研究问题、候选方法与实验方案：在职责/能力约束下平衡业务覆盖、额外授权和规则复杂度。具体搜索、评分函数、权重、阈值及最终算法留待组长/B 的算法讨论，不在本轮文档方案中预设最优解。
4. Policy.learn 只加载 learning-view 中准入 normal train、资源目录和粗粒度约束；正常 validation 只供验证/选参。实现 manual/exact/grouped 接口，grouped 用显式配置区分简单目录归纳与自研方法，知识输入和消融开关留痕。完整 test 真值、development 反例不参与候选生成。
5. 保留主体—逻辑资源—动作、来源 run/event、阶段与低频必要性证据。提出有界 exact/directory 候选，不自动将日期/数字换成任意通配，不跨业务分区，不自动删除低频权限。对成功但冲突已知职责的记录报警而非授权。
6. 定义并输出覆盖、授权扩张、规则复杂度与收紧影响，区分已知硬约束符合性和可选择范围内的归纳代价。额外授权仅按预先固定的有限清单报告；算法不得借用该清单的冻结 test 预期优化规则。没有实测改进如实报告。
7. explain 提供来源与规则增删影响；validate_replay 只报告离线覆盖，并交 C 正常 Linux 验证清单。解释完整/正确率独立评估，不能把关闭解释呈现当成权限安全消融，没有人工实验不报告审核效率提升。
8. Windows 可导入 contracts/policy/store 的离线部分，不依赖 BPF/cgroup/root。Linux compile 使用当前 Capabilities/Bindings，与 A 冻结 ABI，动作、目录深度或版本无法表达时返回含 rule_id 的诊断，禁止静默放宽和固化旧 PID/inode。
9. 实现 candidate/validated/approved/installed 生命周期；安装后还需 C 真实正常业务验证。异常仅提供待审核候选，不自动白名单化。SQLite 单写、WAL、busy_timeout、索引、一致导出与只读查询按契约供 C 调用。
10. 提供可复现配置、输入 hash、来源解释、对照说明与 handoff。根依赖交 C 汇总，F 负责派生数据实现；B 定义共享语义和关键校验，不复制 F 的数据管道。组长组织运行与最终决策，B 对研究设计和方法实现负责。

## 明确参考这些代码

- R03 KubeArmor 的 `KubeArmor/types/types.go`：参考 file/process/host policy 的结构和动作含义；重建为本项目纯 Python 的服务—资源—动作模型，不引入完整 Kubernetes/Go 控制平面。
- R03 的 BPF enforcer 与 A 一起阅读，用于核对规则能否实际表达；文件许可证与类型文件不同。
- R09 Discovery Engine：仅参考 README 所述“行为可见性到策略”的流程及公开说明。本次未核验出明确代码授权，不复制或移植源码；不能把公开可读理解为可任意改造。
- 可复用清单没有找到可直接替代本项目离线归纳、解释与收紧方法的完整合适底座，该部分由团队实现，并用独立对照证明贡献。

## 本角色验收

G0：业务规格/学习约束的输入边界明确，共享契约 3.1 与两种视图能被 A/C/DEF 使用；G1：读取第一批真实数据并排出质量问题；G2：组长能在 Windows 独立运行学习，输出不带本机绝对路径或旧 kernel binding，回传后 A/B 实际判定一致。候选规则来源可追溯，不支持规则可见，安装失败不半更新。

交 A：bundle/策略语义；交 C：稳定 Python API、参数与存储接口；交 DEF：Schema/fixture/数据要求；交组长：可运行学习工具与报告，不把未经执行的算法当成已有效。
