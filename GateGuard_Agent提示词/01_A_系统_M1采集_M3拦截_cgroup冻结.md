# GateGuard Agent 提示词 A 系统

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

实现 collector/、guard/（排除 B 的 decision.py）、bpf/、preflight、cgroup 原语、相关关键测试，以及 collector/enforcement/capabilities 文档。C 编排事故恢复，你不另写恢复状态机；不修改 B/C/DEF 文件或根依赖。

## 开发任务

1. 首先在 Ubuntu VM 真实检查 OS、kernel、LSM、BTF、cgroup v2 和工具链，形成 Capabilities。缓存配置只作线索；加载最小受限目标程序确认。需要启动参数或内核改动时给组长具体影响、回退和验证办法。
2. 按 08 实现 Collector.start/stop，输出成功/失败/未知及真实 syscall 结果；按目标 cgroup 过滤。线程级 entry/exit 关联，记录丢失与 clock_id；open flags 不冒充 write。
3. 与 B 在 G1 前冻结 map ABI：键值布局、主体/资源映射、动作位、上限、字节序、版本原子切换、绑定 generation 和失效处理。用户态 judge 与内核执行使用同一规则含义。
4. 实现 BPF LSM 主线；逐项验证 file_open、file_permission、创建/删除/改名/截断/mmap 路径，尊重前序 LSM 拒绝。不预设所有 helper 都可用，不在内核跑正则；标识须考虑 Btrfs 子卷、链接、重命名和 inode 复用。
5. 实现 Guard.capabilities/install/set_mode；有不支持规则或过期 binding 时拒绝安装。完整新 map 准备成功后原子切换，失败保留旧版本。记录正常退出和崩溃后的 link/map 生命周期，提供状态查询与受控卸载。
6. cgroup.freeze 等待 frozen=1、有超时；拒绝根组/守护组/非登记目标。实现 terminate，探测并验证 cgroup.kill 或受控 SIGKILL，等待 populated=0；冻结后不能只发 SIGTERM 等待普通退出。thaw 由 C 在隔离条件满足时编排。fanotify 可后置实现，限定专用挂载点与 open 策略，不能静默替换 LSM 精细策略。
7. 提供恢复前释放监听引用、恢复后重建资源映射的接口。审计队列满不改变已有内核裁决；错误和丢失可见。
8. 与 C/B 验证 collector/reporter/maintainer 的实际进程与 cgroup 映射，不信任请求 role/device_id/comm；同组子进程不宣称不同权限。采集与安装绑定均引用受信登记，恢复后旧实例/旧对象失效。
9. 按 08 补 source/target 双路径、当前挂载与对象证据、未解析状态。rename/create 与硬链接边界不能只凭 Windows 字符串归一化判断；为 F 提供可追溯的解析结果和限制。

## 明确参考这些代码

- R01 libbpf-bootstrap：`examples/c/lsm.c`、`lsm.bpf.c`、`bootstrap.bpf.c` 和 Makefile，作为 loader/CO-RE/事件通道的改造起点。原 lsm 示例会拒绝 bpf()；只借机制，先改作用域和钩子，不原样运行。
- R02 BCC：`libbpf-tools/opensnoop.bpf.c` 与 `opensnoop.c`，参考线程配对、flags、返回值和事件上报；`tools/opensnoop.py` 用作 Python PoC/对照，不建立两套长期采集器。
- R03 KubeArmor：`KubeArmor/BPF/enforcer.bpf.c`、`enforcer_path.bpf.c`，参考 file_open/file_permission/路径操作执行与审计，移除其宿主依赖前先分析资源与主体模型。相关 BPF 文件为 GPL-2.0，不能按根 Apache-2.0 直接换头。

精确 URL、快照 SHA 和许可见 07。交付来源映射和自研增量：单机 cgroup 主体、电力资源分区、策略 bundle、操作覆盖与恢复重绑定。

## 本角色验收

G0：最小探测和受限 LSM 结果；G1：采集包符合契约；G2：同一普通身份下无 Guard 可写，执行后读允许写拒绝，其他动作逐项实测。unsupported/unverified 单列，LSM deny 与 syscall errno 均保存。冻结不影响 shell/IDE/守护，故障退出可救援。

交 B：Capabilities、ABI、安装与审计语义；交 C：TargetSpec 生命周期、freeze/thaw、关闭/重建；交 DEF：采集入口与限制。Ubuntu 通过后再测 openEuler，不能混写结果。
