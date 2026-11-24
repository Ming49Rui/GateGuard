# 数据质检与划分（任务 F）

契约基线：`GateGuard_Agent提示词/08_接口与数据契约.md` 版本 3.0。
状态：**初版，只在自造 fixture 上验证过**；真实 run 包与 B 的 schema 实现尚未接入。

## 1 范围与所有权

| 项 | 内容 |
|---|---|
| F 写 | `scripts/data/*`、`data/processed/`、`data/splits/`、`docs/` 下四份文档 |
| F 不写 | `src/gateguard/**`、`bpf/`、`examples/**`、`data/raw/**`、其它角色的文档 |
| 输入 | `data/raw/<label>/<run_id>/` 只读；绝不原地修改、绝不覆盖 |
| 输出 | `data/processed/<dataset_id>/`、`data/splits/`（由本工具生成）、JSON 报告 |
| 不做 | 不选训练方法、不改算法、不替组长下结论；发现数据问题退回 D/E 补采 |

三个工具都只在 F 的路径内落盘；`split.py --force` 重建前会检查目标路径深度，拒绝删除盘符根等过浅路径。

## 2 三态结果

判定一律三态，不允许把"没查"说成"通过"：

- `passed`：检查执行且未发现 error；
- `failed`：发现 error，退出码 2；
- `not_checked`：当前无法判定（例如 B 的 schema 校验未接入、恢复报告未生成），在报告 `unverified` 里单列原因与负责角色。

`contract_gaps` 记录"08 未冻结、F 只能先假设"的结构，属于给 B 的提案，不算数据错误。

## 3 run 包检查（`validate.py --run`）

| 代码 | 级别 | 含义 |
|---|---|---|
| `FILE_MISSING` | error | 七个载荷文件或 `checksums.sha256` 缺失 |
| `CHECKSUM_MISMATCH` / `CHECKSUM_NOT_COVERED` / `CHECKSUM_LINE_INVALID` | error | 内容与校验和不符、载荷未覆盖、行格式非法 |
| `CHECKSUM_SELF_LISTED` | warning | 校验和包含自身（契约要求不包含） |
| `FIELD_MISSING` / `FIELD_NULL_REQUIRED` | error | Event 缺键；必填字段为 null |
| `SCHEMA_VERSION_UNSUPPORTED` | error | 非 3.0 |
| `EVENT_ID_DUP` | error | 同 run 内 event_id 重复 |
| `TS_INVALID` / `MONOTONIC_INVALID` | error | ts 非 UTC `…Z`；monotonic_ns 非法 |
| `CLOCK_ID_MIXED` | warning | 混用 clock_id，monotonic_ns 不可跨 clock 比较 |
| `ENUM_INVALID` | error | operation/result/verdict/label/evidence_kind 越出枚举 |
| `RESULT_ERRNO_CONFLICT` | error | `success` 带非零 errno（LSM allow ≠ syscall 成功） |
| `FAILED_WITHOUT_ERRNO` | warning | `failed` 没有可核对 errno |
| `EVIDENCE_NOT_REAL` | warning | 主机访问证据标成 fixture/simulated_input |
| `PATH_OUTSIDE_PARTITIONS` | error | 路径不在 `live/{config,telemetry,reports,logs}` 之内 |
| `RUN_ID_DIR_MISMATCH` / `RUN_ID_MIXED` | error | 事件 run_id 与目录名不一致 / 同 run 多个 run_id |
| `SERVICE_ID_MISMATCH` | error | manifest 与事件的 service_id 不一致 |
| `OPERATION_ID_DUP` / `OPERATIONS_EMPTY` | error | 场景操作 id 重复 / 未声明操作 |
| `TRUTH_MISSING` | error（violation/boundary/recovery） | 没有预设真值，不能拿 verdict 回填 |
| `EXPECTED_UNKNOWN_OPERATION` / `EXPECTED_DUP` | warning / error | 真值引用了不存在的操作 / 同一操作多条真值 |
| `OPERATION_WITHOUT_EVENT` | warning | 声明的操作没有任何事件证明被执行 |
| `RECOVERY_TRIGGER_MISSING` | error | recovery 场景没有声明触发方式 |
| `RECOVERY_NO_CHANGE` | error | 恢复前后文件真值完全一致——不能当恢复证据 |
| `RECOVERY_HASH_MISSING` | not_checked | 没有 content_sha256，内容恢复无法核对 |
| `OUTCOME_DUP` / `OUTCOME_EMPTY` | error | 结果重复统计 / 违规场景没有实测结果 |
| `POLICY_VERSION_MISSING` | warning | 已生效裁决缺策略版本，无法追溯 |

## 4 dataset 检查（`validate.py --dataset`）

| 代码 | 级别 | 含义 |
|---|---|---|
| `RUN_PAYLOAD_MISSING` / `RUN_CHECKSUM_MISSING` | error | 声明了 run 但未交付载荷 / 载荷缺少 checksums |
| `RUN_PACKAGE_INVALID` | error | 载荷自身质检未通过 |
| `SPLIT_OVERLAP` | error | 同一 run 出现在多个 split（事件级泄漏） |
| `SPLIT_UNKNOWN_RUN` | error | split 引用了未登记 run |
| `SPLIT_TRAIN_NOT_NORMAL` | error | train 混入非 normal |
| `SPLIT_FAMILY_LEAK` | error | 同一 family 跨 train/validation/test——必须整族同集 |
| `SPLIT_UNASSIGNED` | warning | 既未划分也未登记排除原因 |

## 5 划分规则（`split.py`）

- 单位是 **family**：同一 family 的所有 run 必须落在同一 split。
- train 只收 normal；含违规/边界/恢复的 family 必须用 `--test-family` / `--validation-family` 显式指定，否则拒绝生成（`FAMILY_NOT_TRAINABLE`）。
- 同一个 family 不能同时指定为 test 与 validation（`FAMILY_CONFLICT`）。
- 质检未通过的 run 自动进 `exclusions` 并带错误码，不静默丢弃。
- 校验未通过时**不落盘**，避免产出一个半成品 dataset 让人误用。

## 6 指标口径（`summarize.py`）

- 按 `operation_id` 去重：一次动作的多个 hook 只算一次。
- 分母为 0 → `na`；无数据/无真值 → `not_checked`；绝不用预期数字填空。
- `would_deny` 单列，不计实际阻断。
- 额外授权率：只统计"数据集实际覆盖到的职责禁止对"，未覆盖的对不进分母；未提供清单直接 `na`。
- 恢复：RTO 从接受恢复到业务健康通过；RPO 是时间窗口；合法记录/字节损失单列，不合并成"零丢失"。
- 按 backend 分组给出阻断率与误拒率；不同语义后端不比较速度。

## 7 需要 B 补进契约的四处（`contract_gaps`）

1. **`expected_outcomes[i]` 的期望值字段**：08 只约束 `operation_id`，未规定字段名与取值。F 初稿按 `expected: allow|deny|unsupported`。
2. **`initial_files.json` / `final_files.json` 条目结构**：08 只说"内容、声明元数据、业务序号"。F 初稿按 `[{path, content_sha256, mode, uid, gid, biz_seq}]` 或 `{files: [...]}`。
3. **`dataset.json` 字段**：08 只给用途。F 初稿用 `{dataset_id, seed, split_unit, runs:[{run_id,label,family_id,service_id,split,run_dir,payload_sha256}], exclusions:[{run_id,reason,error_codes}], contract_gaps}`。
4. **`splits.json` 键名**：08 只要求三个清单。F 初稿用 `train/validation/test` + `families` + `split_unit` + `frozen`。

建议 B 在 G0 冻结这四处后，F 把读取逻辑收紧为强校验（当前是容错读取 + 上报缺口）。

## 8 待接入

| 项 | 负责 | 现状 |
|---|---|---|
| B 的 schema 3.0 实现与官方 fixture | B | 未发布；`quality_report.json.schema_validation.status = not_checked` |
| 真实 run 包 | D/E（经 C 的 ScenarioRunner + A 的 collector） | 未采集；当前只有 F 自造 fixture |
| `recovery_report.json` | C | 未生成；恢复指标 `not_checked` |

## 9 用法

```powershell
# 自造 fixture（不是 B 的正式 fixture，只验证管道）
python scripts/data/make_fixtures.py --out tmp/fixtures

# 单个 run 包质检
python scripts/data/validate.py --run data/raw/normal/<run_id> --out tmp/report.json

# 生成 processed dataset 与划分（按 family 整族分配）
python scripts/data/split.py --raw data/raw --out data/processed/power-v1 `
    --dataset-id power-v1 --test-family fam-b --validation-family fam-c

# dataset 复查
python scripts/data/validate.py --dataset data/processed/power-v1

# 指标
python scripts/data/summarize.py --dataset data/processed/power-v1 `
    --out artifacts/metrics.json --markdown artifacts/metrics.md
```

自测（stdlib unittest，无第三方依赖）：

```powershell
python scripts/data/tests/test_quality.py -v
```

退出码：0 通过；2 数据或参数错误（08 §7）。

## 10 已知限制

- 不在 Windows 上 resolve/realpath Linux 路径，只做字符串切分判断逻辑分区。
- 不校验 08 未冻结的结构；遇到不认识的结构上报 `contract_gap` 而不是猜。
- 不下结论说"这批数据能用于学习"——覆盖度与业务阶段判断由组长/B 确认，F 只给缺失项清单。
- fixture 通过不等于实测通过，报告里不会出现"实测"字样。
