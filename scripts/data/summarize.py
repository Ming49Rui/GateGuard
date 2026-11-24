"""指标统计（任务 F，契约 3.0 口径；介绍书 §7.5）。

只读 processed dataset，输出 JSON 与 Markdown。所有口径固定，不替代组长做结论：
- 按 operation_id 去重：一次测试动作的多个 hook 只算一次，不放大阻断率。
- 分母为 0 → N/A；没有分母或没有数据 → not_checked。绝不用预期数字填充。
- permissive 的 would_deny 不计实际阻断，单列。
- 不同后端语义不同，不横向比较速度。

用法::

    python scripts/data/summarize.py --dataset data/processed/power-v1 \
        --out artifacts/metrics.json --markdown artifacts/metrics.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EXIT_DATA_INVALID,
    EXIT_OK,
    SCHEMA_VERSION,
    enable_utf8_stdio,
    iter_jsonl,
    logical_root_of,
    utc_now,
    Report,
)


@dataclass
class ActionRecord:
    run_id: str
    split: str
    label: str
    operation_id: str
    service: str
    operation: str | None = None
    resource: str | None = None
    truth: str | None = None
    denied: bool = False
    would_deny: bool = False
    backends: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------


def collect_actions(dataset_dir: Path) -> tuple[list[ActionRecord], list[str]]:
    notes: list[str] = []
    dataset_path = dataset_dir / "dataset.json"
    try:
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"无法读取 {dataset_path}: {exc}"]

    splits: dict[str, str] = {}
    splits_path = dataset_dir / "splits.json"
    if splits_path.is_file():
        try:
            splits_payload = json.loads(splits_path.read_text(encoding="utf-8"))
            for name in ("train", "validation", "test"):
                for run_id in splits_payload.get(name) or []:
                    splits[run_id] = name
        except json.JSONDecodeError:
            notes.append("splits.json 不是合法 JSON，split 字段留空")

    actions: list[ActionRecord] = []
    for entry in dataset.get("runs") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("run_id"), str):
            continue
        run_id = entry["run_id"]
        run_dir = dataset_dir / "runs" / run_id
        label = str(entry.get("label") or "")
        service = str(entry.get("service_id") or "")
        actions.extend(_actions_of_run(run_dir, run_id, splits.get(run_id, ""), label, service, notes))
    return actions, notes


def _actions_of_run(
    run_dir: Path,
    run_id: str,
    split: str,
    label: str,
    service: str,
    notes: list[str],
) -> list[ActionRecord]:
    scratch = Report(str(run_dir), "run")

    manifest: dict[str, Any] = {}
    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            notes.append(f"{run_id}: manifest.json 解析失败")
    truth: dict[str, str] = {}
    operations: dict[str, str] = {}
    resources: dict[str, str | None] = {}
    for item in manifest.get("expected_outcomes") or []:
        if isinstance(item, dict) and isinstance(item.get("operation_id"), str):
            expected = item.get("expected")
            truth[item["operation_id"]] = expected if isinstance(expected, str) else None
    for item in manifest.get("operations") or []:
        if not isinstance(item, dict):
            continue
        oid = item.get("operation_id")
        if not isinstance(oid, str):
            continue
        operations[oid] = str(item.get("operation") or "")
        path = item.get("path")
        resources[oid] = logical_root_of(path) if isinstance(path, str) else None

    # decisions 按 operation_id 去重
    verdicts: dict[str, list[dict[str, Any]]] = {}
    for _lineno, item in iter_jsonl(run_dir / "decisions.jsonl", scratch, "decisions.jsonl"):
        oid = item.get("operation_id")
        if isinstance(oid, str):
            verdicts.setdefault(oid, []).append(item)

    outcome_ops: set[str] = set()
    for _lineno, item in iter_jsonl(run_dir / "outcomes.jsonl", scratch, "outcomes.jsonl"):
        oid = item.get("operation_id")
        if isinstance(oid, str):
            outcome_ops.add(oid)

    op_ids = sorted(set(operations) | set(verdicts) | outcome_ops)
    records: list[ActionRecord] = []
    for oid in op_ids:
        entries = verdicts.get(oid, [])
        denied = any(e.get("verdict") == "deny" and e.get("enforced") is True for e in entries)
        would = any(e.get("verdict") == "would_deny" for e in entries)
        backends = {str(e.get("backend")) for e in entries if e.get("backend")}
        records.append(
            ActionRecord(
                run_id=run_id,
                split=split,
                label=label,
                operation_id=oid,
                service=service,
                operation=operations.get(oid),
                resource=resources.get(oid),
                truth=truth.get(oid),
                denied=denied,
                would_deny=would,
                backends=backends,
            )
        )
    if any(r.truth is None for r in records) and records:
        notes.append(f"{run_id}: 部分操作没有预设真值，相关指标分母不完整")
    return records


# ---------------------------------------------------------------------------
# 口径
# ---------------------------------------------------------------------------


def _metric(numerator: int, denominator: int | None, note: str = "") -> dict[str, Any]:
    if denominator is None:
        return {"status": "not_checked", "value": None, "numerator": None, "denominator": None,
                "note": note or "缺少可计算的数据"}
    if denominator == 0:
        return {"status": "na", "value": None, "numerator": 0, "denominator": 0,
                "note": note or "零分母，按契约记 N/A"}
    return {
        "status": "measured",
        "value": round(numerator / denominator, 4),
        "numerator": numerator,
        "denominator": denominator,
        "note": note,
    }


def compute_metrics(actions: Iterable[ActionRecord]) -> dict[str, Any]:
    actions = list(actions)
    denied_population = [a for a in actions if a.truth == "deny"]
    allowed_population = [a for a in actions if a.truth == "allow"]
    blocked = [a for a in denied_population if a.denied]
    missed = [a for a in denied_population if not a.denied]
    false_denied = [a for a in allowed_population if a.denied]
    unlabeled = [a for a in actions if a.truth is None]
    unsupported = [a for a in actions if a.truth == "unsupported"]

    metrics: dict[str, Any] = {
        "actions_total": {"status": "measured", "value": len(actions)},
        "actions_with_truth": {"status": "measured", "value": len(actions) - len(unlabeled)},
        "actions_unlabeled": {"status": "measured", "value": len(unlabeled)},
        "actions_denied": {"status": "measured", "value": len([a for a in actions if a.denied])},
        "actions_would_deny": {
            "status": "measured",
            "value": len([a for a in actions if a.would_deny]),
            "note": "permissive 的 would_deny 不计实际阻断",
        },
        "block_rate": _metric(len(blocked), len(denied_population),
                              "真值应拒绝且前置条件成立的操作中，被实际拒绝的比例"),
        "missed_denial": _metric(len(missed), len(denied_population), "真值应拒绝但未被实际拒绝"),
        "false_deny_rate": _metric(len(false_denied), len(allowed_population),
                                   "真值正常的操作中被拒绝的比例"),
        "unsupported_actions": {"status": "measured", "value": len(unsupported),
                                "note": "后端声明不支持的操作，单列，不计入阻断率分母"},
    }

    by_backend: dict[str, Any] = {}
    for backend in sorted({b for a in actions for b in a.backends}):
        subset = [a for a in actions if backend in a.backends]
        bd = [a for a in subset if a.truth == "deny"]
        bl = [a for a in subset if a.truth == "allow"]
        by_backend[backend] = {
            "actions": len(subset),
            "block_rate": _metric(len([a for a in bd if a.denied]), len(bd)),
            "false_deny_rate": _metric(len([a for a in bl if a.denied]), len(bl)),
        }
    metrics["by_backend"] = by_backend or {"status": "not_checked", "note": "没有含 backend 的决策记录"}
    return metrics


def extra_authorization(actions: Iterable[ActionRecord], resource_manifest: dict[str, Any] | None) -> dict[str, Any]:
    """额外授权率 = 有限清单中职责禁止但实际获允许的对数 / 该清单中可评估的对数。"""
    if not resource_manifest:
        return {
            "status": "na",
            "value": None,
            "numerator": None,
            "denominator": None,
            "note": "未提供冻结资源—动作清单（--resource-manifest），按契约记 N/A",
        }
    forbidden = resource_manifest.get("forbidden") or []
    actions = list(actions)
    evaluable = 0
    allowed = 0
    details: list[dict[str, Any]] = []
    for pair in forbidden:
        if not isinstance(pair, dict):
            continue
        service = pair.get("service_id")
        resource = pair.get("resource")
        operation = pair.get("operation")
        matched = [
            a for a in actions
            if (service is None or a.service == service)
            and (resource is None or a.resource == resource)
            and (operation is None or a.operation == operation)
        ]
        if not matched:
            continue  # 清单里存在但本数据集未覆盖：不可评估，不进分母
        evaluable += 1
        got = [a for a in matched if not a.denied]
        if got:
            allowed += 1
            details.append({"pair": pair, "runs": sorted({a.run_id for a in got})})
    return {
        "status": "measured" if evaluable else "na",
        "value": round(allowed / evaluable, 4) if evaluable else None,
        "numerator": allowed,
        "denominator": evaluable,
        "note": "可评估对数=数据集实际覆盖到的职责禁止对；未覆盖项不进分母",
        "details": details,
        "manifest_source": resource_manifest.get("source"),
    }


def recovery_metrics(dataset_dir: Path) -> dict[str, Any]:
    """从 recovery run 的 recovery_report.json 读取；没有报告就 not_checked。"""
    try:
        dataset = json.loads((dataset_dir / "dataset.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "not_checked", "note": "无法读取 dataset.json"}
    recovery_runs = [
        entry["run_id"]
        for entry in dataset.get("runs") or []
        if isinstance(entry, dict) and entry.get("label") == "recovery"
    ]
    if not recovery_runs:
        return {"status": "na", "note": "数据集不含 recovery run"}

    reports: list[dict[str, Any]] = []
    missing: list[str] = []
    for run_id in recovery_runs:
        path = dataset_dir / "runs" / run_id / "recovery_report.json"
        if not path.is_file():
            missing.append(run_id)
            continue
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            missing.append(run_id)
    if not reports:
        return {
            "status": "not_checked",
            "note": f"{len(missing)} 个 recovery run 没有 recovery_report.json（恢复未执行或未封包）",
            "missing_runs": missing,
        }
    rto = [r.get("rto_ms") for r in reports if isinstance(r.get("rto_ms"), (int, float))]
    rpo = [r.get("rpo_ms") for r in reports if isinstance(r.get("rpo_ms"), (int, float))]
    lost_records = [r.get("lost_legitimate_records") for r in reports
                    if isinstance(r.get("lost_legitimate_records"), int)]
    lost_bytes = [r.get("lost_legitimate_bytes") for r in reports
                  if isinstance(r.get("lost_legitimate_bytes"), int)]
    outcomes = [r.get("outcome") for r in reports]
    return {
        "status": "measured",
        "reports": len(reports),
        "missing_runs": missing,
        "rto_ms": {"value": max(rto) if rto else None, "samples": rto,
                   "note": "从接受恢复请求到业务健康通过"},
        "rpo_ms": {"value": max(rpo) if rpo else None, "samples": rpo},
        "lost_legitimate_records": sum(lost_records) if lost_records else None,
        "lost_legitimate_bytes": sum(lost_bytes) if lost_bytes else None,
        "outcomes": outcomes,
        "note": "RPO 是时间窗口，损失单列；不把它们统称零丢失",
    }


def integrity_metrics(dataset_dir: Path) -> dict[str, Any]:
    try:
        dataset = json.loads((dataset_dir / "dataset.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "not_checked", "note": "无法读取 dataset.json"}
    lost: list[int] = []
    for entry in dataset.get("runs") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("run_id"), str):
            continue
        meta_path = dataset_dir / "runs" / entry["run_id"] / "metadata.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        collection = meta.get("collection")
        if isinstance(collection, dict) and isinstance(collection.get("lost_events"), int):
            lost.append(collection["lost_events"])
    if not lost:
        return {"status": "not_checked", "note": "metadata 未提供采集丢失计数，无法计算审计完整性"}
    return {
        "status": "measured",
        "lost_events_total": sum(lost),
        "runs_with_counter": len(lost),
        "note": "丢失事件只影响审计完整性标注，不改变已生效的内核裁决",
    }


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def build_report(dataset_dir: Path, resource_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    actions, notes = collect_actions(dataset_dir)
    metrics = compute_metrics(actions)
    metrics["extra_authorization_rate"] = extra_authorization(actions, resource_manifest)
    metrics["recovery"] = recovery_metrics(dataset_dir)
    metrics["audit_integrity"] = integrity_metrics(dataset_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "generated_by": "F/scripts/data/summarize.py",
        "dataset_id": dataset_dir.name,
        "notes": notes,
        "metrics": metrics,
        "provenance": {
            "denominators": "只统计有预设真值的动作；无真值动作单列",
            "dedup_unit": "operation_id（一次动作的多个 hook 只算一次）",
        },
    }


_TABLE_ROWS = (
    ("actions_total", "动作总数"),
    ("block_rate", "违规阻断率"),
    ("missed_denial", "应拒绝未拒绝"),
    ("false_deny_rate", "正常误拒率"),
    ("extra_authorization_rate", "额外授权率"),
    ("actions_would_deny", "would_deny 数（不计阻断）"),
    ("unsupported_actions", "后端不支持动作数"),
)

#: 以百分比展示的比率指标
_RATE_KEYS = {"block_rate", "missed_denial", "false_deny_rate", "extra_authorization_rate"}


def to_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        f"# 指标汇总 · {report['dataset_id']}",
        "",
        f"生成时间：{report['generated_at']}　工具：{report['generated_by']}",
        "",
        "| 指标 | 状态 | 数值 | 分子/分母 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for key, label in _TABLE_ROWS:
        item = metrics.get(key) or {}
        value = item.get("value")
        num = item.get("numerator")
        den = item.get("denominator")
        ratio = f"{num}/{den}" if num is not None and den is not None else "—"
        shown = "—" if value is None else (f"{value:.2%}" if key in _RATE_KEYS else str(value))
        lines.append(
            f"| {label} | {item.get('status', 'not_checked')} | {shown} | {ratio} | {item.get('note', '')} |"
        )

    recovery = metrics.get("recovery") or {}
    lines += ["", f"## 恢复（{recovery.get('status')}）", ""]
    if recovery.get("status") == "measured":
        lines.append(f"- 报告数：{recovery.get('reports')}")
        lines.append(f"- RTO：{recovery.get('rto_ms', {}).get('value')} ms")
        lines.append(f"- RPO：{recovery.get('rpo_ms', {}).get('value')} ms")
        lines.append(f"- 丢失合法记录：{recovery.get('lost_legitimate_records')}")
        lines.append(f"- 丢失字节：{recovery.get('lost_legitimate_bytes')}")
        lines.append(f"- 结果：{recovery.get('outcomes')}")
    else:
        lines.append(f"- {recovery.get('note')}")

    integrity = metrics.get("audit_integrity") or {}
    lines += ["", f"## 审计完整性（{integrity.get('status')}）", "", f"- {integrity.get('note')}"]
    if report.get("notes"):
        lines += ["", "## 备注", ""] + [f"- {n}" for n in report["notes"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdio()
    parser = argparse.ArgumentParser(description="指标统计（任务 F）")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--resource-manifest", type=Path,
                        help="冻结的职责禁止清单 JSON：{source, forbidden:[{service_id,resource,operation}]}")
    args = parser.parse_args(argv)

    if not (args.dataset / "dataset.json").is_file():
        print(f"dataset.json 不存在：{args.dataset}", file=sys.stderr)
        return EXIT_DATA_INVALID

    resource_manifest = None
    if args.resource_manifest:
        try:
            resource_manifest = json.loads(args.resource_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"资源清单不可读：{exc}", file=sys.stderr)
            return EXIT_DATA_INVALID

    report = build_report(args.dataset, resource_manifest)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = to_markdown(report)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown, encoding="utf-8")
    print(markdown)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
