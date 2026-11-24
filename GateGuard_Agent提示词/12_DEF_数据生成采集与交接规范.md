# GateGuard D/E/F 数据生成、采集、规范化与交接

文档版本 3.1，2026-11-24。D/E/F 是三个辅助数据任务，不增加参赛成员。本文件是操作清单与填写示例；字段和语义以 [08 契约](08_接口与数据契约.md) 为唯一基线，业务依据以 [11](11_业务依据_权限矩阵与研究边界.md) 为准。采集和校验工具待 ABC/F 实现，不能把下列步骤当成已存在的一键命令。

## 1 统一目标与责任

交付能在另一台 Windows 上校验、学习并追溯回 Linux 实验的完整数据包。电力数值驱动业务；真实进程文件行为支持权限研究；违规与恢复提供独立评测。规范化不等于改变原始事实，也不要求先把电压归一化到 0—1。

| 角色 | 自己生成/维护 | 调用与交接 |
|---|---|---|
| D | 输入来源说明、标准化电力记录、normal manifests、自己采集的 raw/normal | 交 C 输入样例；用 C 场景入口与 A 采集器获取真实 run；交 F 完整包 |
| E | violation/boundary/recovery manifests、受控动作参数与自己采集的 raw | 使用相同业务、主体和资源规格；交 F 真值与完整证据，不另建采集器/特权入口 |
| F | 质量报告、规范化派生视图、划分、数据集封包、统计工具 | 调用 B 的结构校验，保留 raw 字节；交组长/B 数据视图与排除原因 |
| A/B/C | A 真实采集和动作覆盖；B 共享模型与校验；C 业务、身份/资源登记、统一运行和恢复 | 为 DEF 提供 fixture、命令、环境与限制；修复各自模块问题 |

## 2 开始前核对表

1. 阅读 00、08、11、12 和自己的角色提示词，确认同一文档/契约版本。
2. 取得已审核的 subject/resource catalog、BusinessSpec 与 LearningConstraints 及 hash。没有规范依据的预期标 unspecified，不能自行猜成违规。
3. 确认 C 的目标 service_id、instance_id、cgroup 与保护挂载登记，准备 seed、scenario_id、family_id 和预期业务结果。
4. Windows 可先清洗、写 manifest、检验 fixture；真实 run 在登记 Linux VM 内生成。fixture 不参与最终系统性能、阻断和恢复验收。
5. G1 先交少量代表性完整 run：正常生命周期、一个无 Guard 前置/执行模式配对违规、一个独立损坏恢复。恢复入口未就绪先交场景，不伪造完成记录。F/B 准入后再扩大。

## 3 D：输入格式与正常业务覆盖

### 3.1 标准化电力输入

首轮交换使用 UTF-8 JSONL（无 BOM、LF）；若源为 CSV，保留原文件并导出同义 JSONL，所有字段名见 08。JSON 数值不允许 NaN/Infinity；没有的量写 null，不能写空串或补成 0。时间转换到 UTC，原时区和转换依据写 input-provenance.json。记录 ID `record_id` 在本输入包唯一。

以下只是 synthetic 格式示例，不是实测设备数据：

```json
{"record_id":"synthetic-001","source_time":"2026-11-24T00:00:00Z","device_id":"meter-01","voltage_v":220.0,"current_a":1.0,"active_power_kw":0.20,"quality":"valid","source_type":"synthetic"}
```

| 字段 | 要求与错误处理 |
|---|---|
| record_id/device_id | 非空字符串；设备命名和来源映射固定；复制一户数据不能伪称多台真实设备 |
| source_time | UTC ISO 8601、Z 结尾；重复时间保留原因和来源行号，不默认删掉 |
| voltage_v/current_a/active_power_kw | 有限数值或 null；单位转换有公式、基准与来源；不从电压电流直接假设功率因数为 1 推算真实有功功率 |
| quality | valid/missing/invalid；含缺测写 missing，非法输入写 invalid；C 对每类如何跳过/拒绝/保留由场景固定 |
| source_type | public_replay/synthetic；公开回放不自动视为当前真实设备；合成/仿真明确标记 |

input-provenance.json 至少记录 schema_version、input_id、version、source_url（合成可 null）、license、original_sha256（无原文件则 null 并说明）、output_sha256、字段映射、单位转换、时区、缺失值处理、生成器/配置/seed、原始行到 record_id 的映射文件引用。许可未知的数据不当作可公开重分发载荷，交来源引用和替代合成输入。

### 3.2 正常场景清单

| 场景 | 必须核对的正常需求 |
|---|---|
| 启动/重启 | 指定配置读取、首次目录/文件创建；重启后实例身份更新 |
| 持续采样 | 已存在数据文件的正常写入、业务记录序号和质量处理 |
| 跨日期/负载变化 | 新日期文件、不同速率和输入量；不能只换 seed 重复同一轨迹充多样性 |
| 查询/报表 | reporter 读原始数据、写指定报表，确认原始数据未变 |
| 轮转 | 指明谁执行 rename/create/remove，源/目标目录与必要范围 |
| 维护/重载 | maintainer 修改配置；collector 仅重读；不临时授予 collector 配置写权限 |
| 异常退出后的启动 | 恢复业务所需访问，低频操作保留依据，不仅按频次筛掉 |

D 交的是业务需求与实际观测，不按学习效果删改样本。电压越界或缺值可以是输入质量/业务异常，但不直接标成权限 violation。

## 4 E：违规、边界和恢复必须分开

| label | 场景例子 | 正确验收证据 |
|---|---|---|
| violation | collector 写配置、写报表；reporter 修改原始数据 | BusinessSpec 独立预期 deny；相同身份无 Guard 前置可成功；执行模式真实裁决与 syscall 结果 |
| boundary | 旧/继承 fd、mmap、软硬链接、rename、路径替换 | 逐动作和后端记录能力、预期与事实；不是所有 boundary 都必然应拒绝 |
| recovery | 有权限写入的 telemetry 内容损坏 | 业务权限预期可为 allow；先证明内容变化，再独立触发恢复，核对恢复点、健康与损失 |

每项动作使用 operation_id，不能用一个 run 的 violation 标签替代每条操作的授权预期。rename 记 source/target，create 记 parent/new name；不能只记录最后一个路径。

前置运行与防护运行使用不同 run_id、独立初始沙箱，但相同 scenario/spec/seed 和等价文件初态，用 comparison_id 关联。关闭 Guard 不关闭系统 DAC/其他 LSM；前置失败标 PRECONDITION_FAILED，不能计为 Guard 成功。不得用 root 或另一个未绑定身份替目标执行。

真实漏洞公告只能支持测试动机。模拟越界读写不冒充真实 CVE 利用复现，不下载真实恶意样本。需要 mount/namespace 等特权边界测试交 A/C 审阅执行。

恢复的 trigger_type 使用 manual_test 或确已实现的检查触发。被拒绝后文件未变不能算恢复成功。保留损坏前、损坏后、恢复后三份文件事实；RTO/RPO、合法记录/字节损失由独立业务序号与文件证据计算。

## 5 原始 run 包：D/E 共同交付

目录结构与新增规范引用见 08 第 4、9 节。每个 run 至少包含 events.jsonl、decisions.jsonl、outcomes.jsonl、manifest.json、metadata.json、initial_files.json、final_files.json、specs/ 引用载荷、checksums.sha256。没有 Guard 时 decisions 是空文件，原因和模式写 metadata；未做恢复时 recovery_report.json 不要求伪造。

- manifest：场景/家族/服务、seed、业务规格和资源目录引用、动作参数、前置条件、授权预期及其依据；不事后用 verdict 改预期。
- metadata：采集者任务、run 与 comparison ID、目标身份、OS/内核/工具/代码提交、clock_id、能力/绑定引用、输入 hash、采集丢失与关联情况；未知填写 null/说明。
- events：A 采集的原始事实，open 意图、LSM allow、syscall success 分开。缺关联允许 null，不用时间相近补造 operation_id。
- outcomes：C 场景动作的实际完成情况，包括实际结果/errno 和证据引用；不复制 Guard 裁决作为实际结果。
- 文件事实：每个路径的类型、内容 hash（不适用则 null）、大小、已检查元数据、业务序号；缺项说明，不用一个 hash 证明全部元数据。
- checksums 校验和：相对路径和小写 SHA-256，覆盖全部载荷，不包含自身。封包后 raw 只读；修正用新 run/新包并记录 supersedes 原因。

临时 PID/inode/cgroup 的真实值可留在 raw/运行绑定中；共享策略和学习特征不固化它们。公共交付不携带真实凭据或业务隐私；无法共享的样本记录排除原因，另生成标明来源的合成样本，不静默修改 raw 字节。

## 6 F：规范化只产生派生视图

1. 调用 B 的 Dataset.validate 做结构/hash/引用检查，再做业务语义质检；区分错误、警告与未检查。
2. 原始 run 字节复制到可校验包，不能覆盖。规范化输出到 processed/<dataset_id>/normalized/<run_id>/events.jsonl，采用 08 的 NormalizedEvent。
3. 主体依据受信 target 登记映射；资源依据本次 resource catalog 和当前绑定证据映射。请求内 device_id、进程 comm、自报 phase 不能授予权限。
4. 同一正常动作产生多个 hook 时保留 source_event_refs，仅在关联有依据时聚合；未关联不强行去重。统计以可信 operation_id 为主，观测事件数另列。
5. 路径保留 raw；派生相对路径使用 Linux 语义。不能在 Windows resolve Linux path，不能把词法消除 ../ 当作软链接/对象身份已验证。双路径操作保留两端，解析不明标 unresolved。
6. 每条派生记录保留源 run/event、文件 hash/行号、转换版本、规格引用和 normalization_status。未解析、冲突、失败、unknown 保留并说明学习准入状态，不补造事实。
7. 业务 phase 仅辅助覆盖与解释；缺依据为 null。合法数值异常不转为主机权限违规。成功但违反已知业务约束的记录应报警/隔离，不加入授权候选。

### 6.1 切分与防泄漏

同一个 run 不拆事件；同源 family、输入变体和无 Guard/执行配对 comparison 作为同一分组分配，禁止进入不同 split。按服务分别生成 profile，service_id 是分层维度；同服务内按 family/comparison 分组，不能把训练服务全部留在 train 而要求未训练服务通用预测。正常训练与独立 normal 测试均需有代表性生命周期覆盖。

train 只含通过质量检查的 normal。validation 用于正常覆盖和参数选择；开发中看过的异常反例标 development，不混进最终冻结 test。最终 violation/boundary/recovery 与 normal test 不用于选规则或阈值。

F 分别导出 learning-view.json 和 evaluation-view.json：前者只引用训练/正常验证的准入派生记录及粗粒度约束；后者引用完整评测清单和预期。学习入口拒绝把 evaluation-view 作为学习输入，按 split 只加载允许的行为载荷。完整包中的测试文件仅可作完整性 hash 检查，不参与候选生成。manifest 已含部分预期时，学习解析器也必须投影掉评测专用字段。

### 6.2 指标注意事项

有限清单固定 subject/resource/path/action 和职责预期，不从模型输出造标签。额外授权分离“违反已知硬约束”和“可选择范围的扩大”；有限清单之外未来对象范围单独描述。零分母为 N/A，unspecified、unsupported、未测与前置失败列数量及原因。

解释呈现开关不应改变权限判断；其价值用证据完整/解释正确率评估。没有人工审核实验不报告效率提升。离线覆盖、真实业务完成、实际阻断、内核耗时与 Python 函数耗时分别统计。

## 7 G1 准入与退回清单

| 检查 | 通过条件 | 不通过处理 |
|---|---|---|
| 结构与版本 | 必需文件、模型、枚举、ID/引用均符合 08 | 退回 B 或包生成者；记录版本差异 |
| 完整性 | 所有 specs/run/input 引用可解析，checksum 通过 | 不进入学习；重新传输或新包修订 |
| 主体与资源 | 有 target/cgroup 和资源映射证据，作用域明确 | unresolved，不能推导宽权限 |
| 操作语义 | open/allow/success 分开，双路径动作齐全 | 补采或排除该动作，保留原事实 |
| 授权真值 | 预期先定且有 BusinessSpec 依据，未知单列 | 不计应拒分母，交 B/C/组长确认 |
| 学习准入 | normal、可信成功/操作语义、无约束冲突，低频记录保留 | 报告原因；不把“未准入”当删除原始记录 |
| 切分 | family/comparison 无跨 split 泄漏，测试未参与开发调参 | 重新分组并另发 dataset 版本 |
| 真实性 | source_type/evidence_kind 明确，fixture 和 real 不混报 | 修正元数据并生成新版本 |
| 恢复 | 确认损坏、恢复报告、合法损失依据齐全 | not_run/failed/not_checked；不凑成功 |

## 8 每人交接必须写什么

在 docs/handoffs/D.md、E.md、F.md 写：文件列表、schema/spec/工具/代码版本、真实命令与退出码、run/family/comparison 清单、输入与载荷 hash、已检查/未检查项、失败与排除原因、下一角色需提供的输入。来源说明和许可一并交付。

D：交 C 输入/单位/质量样例，交 F 正常 run 与覆盖表。E：交 A/B 真实反例，交 C 损坏/恢复条件，交 F 独立预期与前置证据。F：交组长/B 可独立打开的完整包、两种输入视图、划分与质量报告，给 D/E 明确补采清单。

最小正式批次以“代表性与证据齐全”为准，不预设必须凑多少万条数据。工具未实现前可准备文档和 fixture；正式采集和性能数字必须等工具真实运行。
