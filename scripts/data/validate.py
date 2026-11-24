"""GateGuard run/dataset 包质检（任务 F，契约 3.0）。

用法::

    python scripts/data/validate.py --run  data/raw/normal/<run_id>
    python scripts/data/validate.py --dataset data/processed/<dataset_id>
    python scripts/data/validate.py --run <dir> --out tmp/report.json --strict

退出码遵循 08 §7：0 通过；2 参数或数据错误。质检失败返回 2，不返回 0。

本工具只做 F 负责的"业务质量与真值一致性"检查：文件齐全、checksum、
ID 唯一、时钟、枚举、result/errno 关系、真值缺失、越界路径、恢复前是否
确有变化。schema 的结构校验归 B（Dataset.validate），B 交付后接入，
两侧结论并列写入 quality_report.json，互不替代。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    CHECKSUMS_FILE,
    DECISION_FIELDS,
    EVIDENCE_KINDS,
    EVENT_FIELDS,
    EVENT_REQUIRED_NON_NULL,
    EXIT_DATA_INVALID,
    EXIT_OK,
    LABELS,
    MANIFEST_FIELDS,
    OPERATIONS,
    PAYLOAD_FILES,
    RESULTS,
    SCHEMA_VERSION,
    VERDICTS,
    Report,
    entry_business_seq,
    entry_content_hash,
    enable_utf8_stdio,
    is_valid_ts,
    iter_jsonl,
    normalize_file_truth,
    partition_problem,
    read_json_file,
    verify_checksums,
)


def validate_run(run_dir: Path, report: Report | None = None) -> Report:
    """校验一个 run 包。返回的 Report.status 为 passed / failed / not_checked。"""
    rep = report or Report(str(run_dir), "run")
    if not run_dir.is_dir():
        rep.error("RUN_DIR_MISSING", str(run_dir), "run 目录不存在")
        return rep

    # --- 1. 载荷文件齐全 ------------------------------------------------
    present: list[str] = []
    for name in PAYLOAD_FILES:
        if (run_dir / name).is_file():
            present.append(name)
        else:
            rep.error("FILE_MISSING", name, f"缺少载荷文件 {name}")
    rep.check(
        "payload_files",
        "passed" if len(present) == len(PAYLOAD_FILES) else "failed",
        f"{len(present)}/{len(PAYLOAD_FILES)}",
    )

    # --- 2. checksums ---------------------------------------------------
    if (run_dir / CHECKSUMS_FILE).is_file():
        for finding in verify_checksums(run_dir, present):
            rep.findings.append(finding)
        rep.check("checksums", "passed" if not _has_code(rep, "CHECKSUM_") else "failed")
    else:
        rep.check("checksums", "failed", "缺少 checksums.sha256")

    # --- 3. events ------------------------------------------------------
    events: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    clock_ids: set[Any] = set()
    event_run_ids: set[Any] = set()
    event_service_ids: set[Any] = set()
    for lineno, ev in iter_jsonl(run_dir / "events.jsonl", rep, "events.jsonl"):
        loc = f"events.jsonl:{lineno}"
        events.append(ev)
        for field_name in EVENT_FIELDS:
            if field_name not in ev:
                rep.error("FIELD_MISSING", f"{loc}.{field_name}", f"Event 缺少字段 {field_name}")
        for field_name in EVENT_REQUIRED_NON_NULL:
            if ev.get(field_name) is None:
                rep.error(
                    "FIELD_NULL_REQUIRED",
                    f"{loc}.{field_name}",
                    f"Event.{field_name} 不允许为 null（缺证据不能默认通过）",
                )
        if ev.get("schema_version") not in (None, SCHEMA_VERSION):
            rep.error(
                "SCHEMA_VERSION_UNSUPPORTED",
                f"{loc}.schema_version",
                f"schema_version={ev.get('schema_version')!r}，本工具只处理 {SCHEMA_VERSION}",
            )
        eid = ev.get("event_id")
        if isinstance(eid, str):
            if eid in event_ids:
                rep.error("EVENT_ID_DUP", f"{loc}.event_id", f"event_id 重复：{eid}")
            event_ids.add(eid)
        if ev.get("ts") is not None and not is_valid_ts(ev.get("ts")):
            rep.error(
                "TS_INVALID",
                f"{loc}.ts",
                f"ts 必须是 UTC ISO 8601 且以 Z 结尾，实际 {ev.get('ts')!r}",
            )
        mns = ev.get("monotonic_ns")
        if mns is not None and (isinstance(mns, bool) or not isinstance(mns, int) or mns < 0):
            rep.error("MONOTONIC_INVALID", f"{loc}.monotonic_ns", f"monotonic_ns 非法：{mns!r}")
        if ev.get("clock_id") is not None:
            clock_ids.add(ev.get("clock_id"))
        if ev.get("operation") is not None and ev.get("operation") not in OPERATIONS:
            rep.error(
                "ENUM_INVALID",
                f"{loc}.operation",
                f"operation={ev.get('operation')!r} 不在契约枚举内",
            )
        if ev.get("result") is not None and ev.get("result") not in RESULTS:
            rep.error(
                "ENUM_INVALID", f"{loc}.result", f"result={ev.get('result')!r} 不在契约枚举内"
            )
        if ev.get("evidence_kind") is not None and ev.get("evidence_kind") not in EVIDENCE_KINDS:
            rep.error(
                "ENUM_INVALID",
                f"{loc}.evidence_kind",
                f"evidence_kind={ev.get('evidence_kind')!r} 不在契约枚举内",
            )
        _check_result_errno(rep, loc, ev)
        if ev.get("evidence_kind") and ev.get("evidence_kind") != "real":
            rep.warn(
                "EVIDENCE_NOT_REAL",
                f"{loc}.evidence_kind",
                "主机访问证据应为 real；fixture/simulated_input 不得用于学习或验收结论",
            )
        problem = partition_problem(ev.get("path"))
        if problem:
            rep.error("PATH_OUTSIDE_PARTITIONS", f"{loc}.path", problem)
        if ev.get("run_id") is not None:
            event_run_ids.add(ev.get("run_id"))
        if ev.get("service_id") is not None:
            event_service_ids.add(ev.get("service_id"))

    if len(event_run_ids) > 1:
        rep.error(
            "RUN_ID_MIXED", "events.jsonl", f"同一 run 内出现多个 run_id：{sorted(map(str, event_run_ids))}"
        )
    if event_run_ids and run_dir.name not in event_run_ids:
        rep.error(
            "RUN_ID_DIR_MISMATCH",
            "events.jsonl",
            f"事件 run_id={sorted(map(str, event_run_ids))} 与目录名 {run_dir.name} 不一致",
        )
    if len(clock_ids) > 1:
        rep.warn(
            "CLOCK_ID_MIXED",
            "events.jsonl",
            f"事件混用多个 clock_id：{sorted(map(str, clock_ids))}；monotonic_ns 不可跨 clock 比较",
        )
    rep.check(
        "events",
        "passed" if events and not _has_code(rep, ("FIELD_", "EVENT_ID_DUP", "TS_INVALID", "ENUM_INVALID")) else "failed",
        f"{len(events)} 条事件",
    )

    # --- 4. manifest（场景真值） ---------------------------------------
    manifest = read_json_file(run_dir / "manifest.json", rep, "manifest.json")
    label = None
    operations_ids: set[str] = set()
    if isinstance(manifest, dict):
        for field_name in MANIFEST_FIELDS:
            if field_name not in manifest:
                rep.error("FIELD_MISSING", f"manifest.json.{field_name}", f"Manifest 缺少字段 {field_name}")
        label = manifest.get("label")
        if label is not None and label not in LABELS:
            rep.error("ENUM_INVALID", "manifest.json.label", f"label={label!r} 不在契约枚举内")
        if manifest.get("schema_version") not in (None, SCHEMA_VERSION):
            rep.error(
                "SCHEMA_VERSION_UNSUPPORTED",
                "manifest.json.schema_version",
                f"schema_version={manifest.get('schema_version')!r}",
            )
        operations_ids = _check_manifest_operations(rep, manifest)
        _check_expected_outcomes(rep, manifest, operations_ids)
        declared_without_event = sorted(
            operations_ids - {ev.get("operation_id") for ev in events if ev.get("operation_id")}
        )
        if declared_without_event:
            rep.warn(
                "OPERATION_WITHOUT_EVENT",
                "manifest.json.operations",
                f"声明的操作没有任何事件能证明它被执行：{declared_without_event}",
            )
        if label == "recovery" and not manifest.get("recovery_trigger"):
            rep.error(
                "RECOVERY_TRIGGER_MISSING",
                "manifest.json.recovery_trigger",
                "recovery 场景必须声明 recovery_trigger（损坏如何被确认与触发）",
            )
        msid = manifest.get("service_id")
        if msid is not None and event_service_ids and msid not in event_service_ids:
            rep.error(
                "SERVICE_ID_MISMATCH",
                "manifest.json.service_id",
                f"manifest.service_id={msid!r} 与事件中的 {sorted(map(str, event_service_ids))} 不一致",
            )
    elif manifest is None:
        label = None

    # --- 5. metadata ----------------------------------------------------
    metadata = read_json_file(run_dir / "metadata.json", rep, "metadata.json")
    if isinstance(metadata, dict):
        recommended = [k for k in ("os", "kernel", "seed", "clock_id", "commit", "toolchain")]
        missing_meta = [k for k in recommended if k not in metadata]
        if missing_meta:
            rep.warn(
                "METADATA_RECOMMENDED_MISSING",
                "metadata.json",
                f"建议记录但缺失：{missing_meta}（08 §4 要求可追溯环境与提交）",
            )
        if metadata.get("schema_version") not in (None, SCHEMA_VERSION):
            rep.warn(
                "SCHEMA_VERSION_UNSUPPORTED",
                "metadata.json.schema_version",
                f"metadata.schema_version={metadata.get('schema_version')!r}",
            )

    # --- 6. outcomes（独立于 Guard 的实测结果） ------------------------
    outcomes: list[dict[str, Any]] = []
    seen_ops: set[str] = set()
    for lineno, item in iter_jsonl(run_dir / "outcomes.jsonl", rep, "outcomes.jsonl"):
        loc = f"outcomes.jsonl:{lineno}"
        outcomes.append(item)
        oid = item.get("operation_id")
        if not isinstance(oid, str) or not oid:
            rep.error("OUTCOME_FIELD_MISSING", f"{loc}.operation_id", "outcome 缺少 operation_id")
        elif oid in seen_ops:
            rep.error("OUTCOME_DUP", f"{loc}.operation_id", f"operation_id 重复统计：{oid}")
        else:
            seen_ops.add(oid)
        if item.get("result") not in RESULTS:
            rep.error(
                "ENUM_INVALID", f"{loc}.result", f"outcome.result={item.get('result')!r} 不在契约枚举内"
            )
        if label in ("violation", "boundary", "recovery") and not item.get("result"):
            rep.error("OUTCOME_FIELD_MISSING", f"{loc}.result", "违规/边界/恢复场景必须记录实测结果")
    if not outcomes:
        if label in ("violation", "boundary"):
            rep.error(
                "OUTCOME_EMPTY", "outcomes.jsonl", "违规/边界场景没有记录实测结果，无法证明前置条件成立"
            )
        elif label == "normal":
            rep.warn("OUTCOME_EMPTY", "outcomes.jsonl", "normal 场景没有记录业务结果")
    rep.check("outcomes", "passed" if outcomes else "not_checked", f"{len(outcomes)} 条")

    # --- 7. decisions（可能为空：未启用 Guard） ------------------------
    decisions = 0
    for lineno, item in iter_jsonl(run_dir / "decisions.jsonl", rep, "decisions.jsonl"):
        decisions += 1
        loc = f"decisions.jsonl:{lineno}"
        for field_name in DECISION_FIELDS:
            if field_name not in item:
                rep.error("FIELD_MISSING", f"{loc}.{field_name}", f"Decision 缺少字段 {field_name}")
        if item.get("verdict") not in VERDICTS:
            rep.error(
                "ENUM_INVALID", f"{loc}.verdict", f"verdict={item.get('verdict')!r} 不在契约枚举内"
            )
        if "enforced" in item and not isinstance(item.get("enforced"), bool):
            rep.error("TYPE_INVALID", f"{loc}.enforced", "enforced 必须是布尔值")
        if item.get("verdict") in ("allow", "deny") and item.get("policy_version") is None:
            rep.warn(
                "POLICY_VERSION_MISSING",
                f"{loc}.policy_version",
                "已生效裁决缺少 policy_version，无法追溯策略版本",
            )
    rep.check(
        "decisions",
        "passed" if decisions else "not_checked",
        f"{decisions} 条" if decisions else "未启用 Guard（空文件，契约允许）",
    )

    # --- 8. 文件真值 ----------------------------------------------------
    rep.gap(
        "FILE_TRUTH_SHAPE",
        "08 §4 只规定 initial/final 文件真值包含内容、声明元数据与业务序号，未冻结外层结构；"
        "F 初稿按 [entry, ...] 或 {files: [...]} 读取，条目要求 path + content_sha256 + 业务序号",
        needs="在 08 §4 冻结这两个文件的条目字段名与业务序号字段",
    )
    initial_raw = read_json_file(run_dir / "initial_files.json", rep, "initial_files.json")
    final_raw = read_json_file(run_dir / "final_files.json", rep, "final_files.json")
    initial, init_reason = normalize_file_truth(initial_raw)
    final, final_reason = normalize_file_truth(final_raw)
    if init_reason or final_reason:
        rep.error(
            "FILE_TRUTH_UNREADABLE",
            "initial_files.json/final_files.json",
            f"无法按契约用途读出文件真值：{init_reason or final_reason}",
        )
    for mapping, name in ((initial, "initial_files.json"), (final, "final_files.json")):
        for path in mapping:
            problem = partition_problem(path)
            if problem:
                rep.error("PATH_OUTSIDE_PARTITIONS", f"{name}:{path}", problem)

    changed = _changed_paths(initial, final)
    if label == "recovery":
        if not changed:
            rep.error(
                "RECOVERY_NO_CHANGE",
                "initial_files.json/final_files.json",
                "恢复场景必须先证明合成数据确实发生变化；前后真值完全一致不能作为恢复证据",
            )
        if not any(entry_content_hash(e) for e in final.values()):
            rep.unverified_item(
                "RECOVERY_HASH_MISSING",
                "final_files 没有 content_sha256，无法核对内容恢复；只能标 not_checked",
                owner="C/E",
            )
    rep.check(
        "file_truth",
        "passed" if (initial or final) and not _has_code(rep, "PATH_OUTSIDE_PARTITIONS") else "not_checked",
        f"initial {len(initial)} / final {len(final)} 条，变化 {len(changed)} 条",
    )

    # --- 9. 跨文件运行标识 ---------------------------------------------
    for name in ("decisions.jsonl",):
        for lineno, item in iter_jsonl(run_dir / name, rep, f"{name}#runid"):
            rid = item.get("run_id")
            if rid is not None and event_run_ids and rid not in event_run_ids:
                rep.warn(
                    "RUN_ID_MISMATCH",
                    f"{name}:{lineno}.run_id",
                    f"{name} 的 run_id={rid!r} 与事件不一致",
                )

    # --- 10. 未接入的正式 schema 校验 ----------------------------------
    rep.unverified_item(
        "SCHEMA_VALIDATOR_NOT_WIRED",
        "B 的 schema 3.0 实现（Dataset.validate）尚未发布；本报告只是 F 的业务质量检查，"
        "不等价于契约结构校验",
        owner="B",
    )
    return rep


def validate_dataset(dataset_dir: Path, report: Report | None = None, deep: bool = True) -> Report:
    """校验一个 processed dataset：引用完整、划分无泄漏、copied runs 可校验。"""
    rep = report or Report(str(dataset_dir), "dataset")
    if not dataset_dir.is_dir():
        rep.error("DATASET_DIR_MISSING", str(dataset_dir), "dataset 目录不存在")
        return rep

    for name in ("dataset.json", "splits.json", "quality_report.json"):
        if not (dataset_dir / name).is_file():
            rep.error("FILE_MISSING", name, f"缺少 {name}")
    if not (dataset_dir / "runs").is_dir():
        rep.error("FILE_MISSING", "runs/", "缺少 runs/ 目录（未交付原始 run 载荷）")

    if (dataset_dir / CHECKSUMS_FILE).is_file():
        for finding in verify_checksums(
            dataset_dir,
            [n for n in ("dataset.json", "splits.json", "quality_report.json") if (dataset_dir / n).is_file()],
        ):
            rep.findings.append(finding)
    rep.check("dataset_checksums", "passed" if not _has_code(rep, "CHECKSUM_") else "failed")

    dataset = read_json_file(dataset_dir / "dataset.json", rep, "dataset.json")
    splits = read_json_file(dataset_dir / "splits.json", rep, "splits.json")

    run_entries: dict[str, dict[str, Any]] = {}
    if isinstance(dataset, dict):
        rep.gap(
            "DATASET_JSON_SHAPE",
            "08 §4 只列出 dataset.json 的用途，未冻结字段；F 初稿按 {dataset_id, runs:[{run_id,...}], exclusions:[{run_id, reason}]} 读取",
            needs="在 08 §4 冻结 dataset.json 与 splits.json 的字段",
        )
        raw_runs = dataset.get("runs") or []
        if not isinstance(raw_runs, list):
            rep.error("TYPE_INVALID", "dataset.json.runs", "runs 必须是列表")
            raw_runs = []
        for entry in raw_runs:
            if isinstance(entry, str):
                run_entries[entry] = {"run_id": entry}
            elif isinstance(entry, dict) and isinstance(entry.get("run_id"), str):
                run_entries[entry["run_id"]] = entry
            else:
                rep.error("DATASET_RUN_ENTRY_INVALID", "dataset.json.runs", f"无法识别的 run 引用：{entry!r}")

    for run_id in sorted(run_entries):
        run_path = dataset_dir / "runs" / run_id
        if not run_path.is_dir():
            rep.error("RUN_PAYLOAD_MISSING", f"runs/{run_id}", "dataset 声明了该 run 但未交付载荷")
            continue
        if not (run_path / CHECKSUMS_FILE).is_file():
            rep.error("RUN_CHECKSUM_MISSING", f"runs/{run_id}/{CHECKSUMS_FILE}", "载荷缺少 checksums.sha256")
        if deep:
            sub = validate_run(run_path)
            if sub.errors:
                codes = sorted({f.code for f in sub.errors})
                rep.error(
                    "RUN_PACKAGE_INVALID",
                    f"runs/{run_id}",
                    f"载荷自身质检未通过：{codes}",
                )

    # --- 划分检查：不重叠、不未知、train 只 normal、family 不跨集 -------
    if isinstance(splits, dict):
        rep.gap(
            "SPLITS_SHAPE",
            "08 §4 只要求 splits.json 给出 train/validation/test 的 run_id 清单；F 初稿按同名三个键读取",
            needs="确认 splits.json 键名与是否记录 split_unit/seed/frozen",
        )
        occurrences: dict[str, list[str]] = {}
        for split_name in ("train", "validation", "test"):
            ids = splits.get(split_name) or []
            if not isinstance(ids, list):
                rep.error("TYPE_INVALID", f"splits.json.{split_name}", "必须是 run_id 列表")
                continue
            for run_id in ids:
                if not isinstance(run_id, str):
                    rep.error("TYPE_INVALID", f"splits.json.{split_name}", f"非法 run_id：{run_id!r}")
                    continue
                occurrences.setdefault(run_id, []).append(split_name)
                if run_id not in run_entries:
                    rep.error(
                        "SPLIT_UNKNOWN_RUN",
                        f"splits.json.{split_name}",
                        f"run {run_id} 未在 dataset.json 中登记",
                    )

        for run_id, names in sorted(occurrences.items()):
            if len(names) > 1:
                rep.error(
                    "SPLIT_OVERLAP",
                    f"splits.json:{run_id}",
                    f"run {run_id} 同时出现在 {names}（事件级泄漏）",
                )

        family_splits: dict[str, set[str]] = {}
        manifest_cache: dict[str, dict[str, Any]] = {}
        for run_id, names in sorted(occurrences.items()):
            if run_id not in manifest_cache:
                manifest_path = dataset_dir / "runs" / run_id / "manifest.json"
                manifest = read_json_file(manifest_path, rep, f"runs/{run_id}/manifest.json")
                manifest_cache[run_id] = manifest if isinstance(manifest, dict) else {}
            manifest = manifest_cache[run_id]
            label = manifest.get("label")
            family = manifest.get("family_id")
            for split_name in names:
                if split_name == "train" and label != "normal":
                    rep.error(
                        "SPLIT_TRAIN_NOT_NORMAL",
                        f"splits.json.train:{run_id}",
                        f"train 只允许 normal，该 run 的 label={label!r}",
                    )
                if isinstance(family, str) and family:
                    family_splits.setdefault(family, set()).add(split_name)

        for family, names in sorted(family_splits.items()):
            if len(names) > 1:
                rep.error(
                    "SPLIT_FAMILY_LEAK",
                    f"splits.json:{family}",
                    f"family {family} 同时出现在 {sorted(names)}；必须整族同集，否则同源事件泄漏到测试集",
                )

        excluded = {e.get("run_id") for e in (dataset.get("exclusions") or []) if isinstance(e, dict)}
        unassigned = sorted(set(run_entries) - set(occurrences) - excluded)
        if unassigned:
            rep.warn(
                "SPLIT_UNASSIGNED",
                "splits.json",
                f"{len(unassigned)} 个 run 既未划分也未登记排除原因：{unassigned[:5]}",
            )
        rep.check(
            "splits",
            "passed" if not _has_code(rep, ("SPLIT_", "SCHEMA_")) else "failed",
            f"train {len(splits.get('train') or [])} / validation {len(splits.get('validation') or [])} / test {len(splits.get('test') or [])}",
        )

    rep.unverified_item(
        "SCHEMA_VALIDATOR_NOT_WIRED",
        "B 的 Dataset.validate 尚未发布；dataset 结构校验待 B 在 G0 交付后并列写入",
        owner="B",
    )
    return rep


# ---------------------------------------------------------------------------
# 内部检查
# ---------------------------------------------------------------------------


def _has_code(rep: Report, prefixes: str | tuple[str, ...]) -> bool:
    if isinstance(prefixes, str):
        prefixes = (prefixes,)
    return any(f.code.startswith(prefixes) for f in rep.findings)


def _check_result_errno(rep: Report, loc: str, ev: dict[str, Any]) -> None:
    """success 不能带非零 errno；failed 应带 errno；unknown 不约束。"""
    result = ev.get("result")
    errno = ev.get("errno")
    if result == "success" and isinstance(errno, int) and not isinstance(errno, bool) and errno != 0:
        rep.error(
            "RESULT_ERRNO_CONFLICT",
            f"{loc}.errno",
            f"result=success 却带 errno={errno}；LSM allow 不等于 syscall 成功，两者不能混写",
        )
    if result == "failed" and (errno is None or errno == 0):
        rep.warn(
            "FAILED_WITHOUT_ERRNO",
            f"{loc}.errno",
            "result=failed 但没有非零 errno；失败尝试必须保留可核对的错误号",
        )


def _check_manifest_operations(rep: Report, manifest: dict[str, Any]) -> set[str]:
    operations = manifest.get("operations")
    ids: set[str] = set()
    if not isinstance(operations, list):
        rep.error("TYPE_INVALID", "manifest.json.operations", "operations 必须是列表")
        return ids
    for idx, item in enumerate(operations):
        loc = f"manifest.json.operations[{idx}]"
        if not isinstance(item, dict):
            rep.error("TYPE_INVALID", loc, "操作项必须是对象")
            continue
        oid = item.get("operation_id")
        if not isinstance(oid, str) or not oid:
            rep.error("FIELD_MISSING", f"{loc}.operation_id", "操作项缺少 operation_id")
            continue
        if oid in ids:
            rep.error("OPERATION_ID_DUP", f"{loc}.operation_id", f"operation_id 重复：{oid}")
        ids.add(oid)
        op = item.get("operation")
        if op is not None and op not in OPERATIONS:
            rep.error("ENUM_INVALID", f"{loc}.operation", f"operation={op!r} 不在契约枚举内")
    if not ids:
        rep.error("OPERATIONS_EMPTY", "manifest.json.operations", "场景未声明任何操作")
    return ids


def _check_expected_outcomes(rep: Report, manifest: dict[str, Any], ids: set[str]) -> None:
    rep.gap(
        "EXPECTED_OUTCOME_SHAPE",
        "08 §3 只约束 expected_outcomes[i].operation_id，未规定期望值字段名与取值；F 初稿按 'expected' 读取 allow/deny/unsupported",
        needs="在 08 §3 冻结 expected_outcomes 条目的期望值字段与取值集合",
    )
    expected = manifest.get("expected_outcomes")
    label = manifest.get("label")
    if not isinstance(expected, list):
        rep.error("TYPE_INVALID", "manifest.json.expected_outcomes", "expected_outcomes 必须是列表")
        return
    if not expected:
        if label in ("violation", "boundary", "recovery"):
            rep.error(
                "TRUTH_MISSING",
                "manifest.json.expected_outcomes",
                f"{label} 场景必须给出预设职责真值；不能用 Guard 的 verdict 回填真值",
            )
        else:
            rep.warn(
                "TRUTH_MISSING",
                "manifest.json.expected_outcomes",
                "normal 场景没有预设期望结果，正常误拒率将无法计算",
            )
        return
    seen: set[str] = set()
    for idx, item in enumerate(expected):
        loc = f"manifest.json.expected_outcomes[{idx}]"
        if not isinstance(item, dict):
            rep.error("TYPE_INVALID", loc, "期望结果项必须是对象")
            continue
        oid = item.get("operation_id")
        if oid not in ids:
            rep.warn("EXPECTED_UNKNOWN_OPERATION", loc, f"expected_outcomes 引用了未声明的操作 {oid!r}")
        if isinstance(oid, str):
            if oid in seen:
                rep.error("EXPECTED_DUP", f"{loc}.operation_id", f"同一操作出现多条期望：{oid}")
            seen.add(oid)
        if "expected" not in item:
            rep.warn(
                "EXPECTED_VALUE_MISSING",
                loc,
                "该操作没有期望值；真值缺失会使相应指标分母不完整",
            )


def _changed_paths(initial: dict[str, dict[str, Any]], final: dict[str, dict[str, Any]]) -> set[str]:
    changed: set[str] = set()
    for path, entry in final.items():
        before = initial.get(path)
        if before is None:
            changed.add(path)
            continue
        h_final = entry_content_hash(entry)
        h_init = entry_content_hash(before)
        if h_final and h_init and h_final != h_init:
            changed.add(path)
        elif entry_business_seq(entry) != entry_business_seq(before):
            changed.add(path)
    changed |= set(initial) - set(final)
    return changed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(rep: Report, out: Path | None) -> None:
    counts = rep.to_dict()["counts"]
    print(f"[{rep.status.upper()}] {rep.kind}: {rep.target}")
    print(
        f"  error={counts['error']} warning={counts['warning']} "
        f"not_checked={counts['not_checked']} contract_gap={counts['contract_gap']}"
    )
    for finding in rep.findings[:20]:
        print(f"  - {finding.severity:<7} {finding.code:<28} {finding.locator}: {finding.message}")
    if len(rep.findings) > 20:
        print(f"  ... 其余 {len(rep.findings) - 20} 条见报告")
    for gap in rep.contract_gaps:
        print(f"  ~ gap     {gap['code']}: {gap['message']}")
    if out:
        print(f"  report -> {out}")


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdio()
    parser = argparse.ArgumentParser(description="GateGuard run/dataset 包质检（任务 F）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", type=Path, help="单个 run 包目录")
    group.add_argument("--dataset", type=Path, help="processed dataset 目录")
    parser.add_argument("--out", type=Path, help="把 JSON 报告写到该路径")
    parser.add_argument("--strict", action="store_true", help="把 warning 也视为失败")
    parser.add_argument("--no-deep", action="store_true", help="dataset 模式不逐个校验载荷")
    args = parser.parse_args(argv)

    if args.run:
        rep = validate_run(args.run)
    else:
        rep = validate_dataset(args.dataset, deep=not args.no_deep)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(rep.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    _print_summary(rep, args.out)

    failed = bool(rep.errors) or (args.strict and bool(rep.warnings))
    return EXIT_DATA_INVALID if failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
