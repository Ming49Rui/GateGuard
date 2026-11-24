"""从 data/raw 生成 processed dataset 与 train/validation/test 划分（任务 F）。

F 唯一维护 data/processed/ 与 data/splits/；raw 只读，不原地修改。

用法::

    python scripts/data/split.py --raw data/raw --out data/processed/power-v1 \
        --dataset-id power-v1 --test-family fam-b --validation-family fam-c

规则（08 §4）：
- 划分单位是 **family**：同一 family 的 run 必须整族落在同一个 split，防止事件级泄漏。
- train 只允许 normal；违规/边界/恢复 family 必须显式指定为 validation 或 test。
- 质检未通过的 run 自动排除，并写进 exclusions（带错误码），不静默丢弃。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    CHECKSUMS_FILE,
    EXIT_DATA_INVALID,
    EXIT_OK,
    EXIT_PRECONDITION_FAILED,
    LABELS,
    PAYLOAD_FILES,
    SCHEMA_VERSION,
    Finding,
    Report,
    enable_utf8_stdio,
    sha256_file,
    utc_now,
)
from validate import validate_run  # noqa: E402


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    path: Path
    label: str
    family: str
    service: str


# ---------------------------------------------------------------------------
# 扫描与划分
# ---------------------------------------------------------------------------


def scan_raw(raw: Path) -> tuple[list[RunInfo], list[Finding]]:
    findings: list[Finding] = []
    runs: list[RunInfo] = []
    if not raw.is_dir():
        findings.append(Finding("RAW_DIR_MISSING", "error", str(raw), "raw 目录不存在"))
        return runs, findings

    seen: dict[str, str] = {}
    for label_dir in sorted(p for p in raw.iterdir() if p.is_dir()):
        if label_dir.name not in LABELS:
            findings.append(
                Finding(
                    "RAW_LAYOUT_UNKNOWN",
                    "warning",
                    label_dir.name,
                    f"raw 下出现非契约标签目录 {label_dir.name!r}，已跳过（契约布局 data/raw/<label>/<run_id>/）",
                )
            )
            continue
        for run_dir in sorted(p for p in label_dir.iterdir() if p.is_dir()):
            manifest = _read_manifest(run_dir)
            if manifest is None:
                findings.append(
                    Finding("MANIFEST_INVALID", "error", f"{label_dir.name}/{run_dir.name}",
                            "manifest.json 缺失或不是合法 JSON，无法确定场景真值")
                )
                continue
            label = manifest.get("label")
            if label not in LABELS:
                findings.append(
                    Finding("LABEL_INVALID", "error", f"{label_dir.name}/{run_dir.name}",
                            f"manifest.label={label!r} 不在契约枚举内")
                )
                continue
            if label != label_dir.name:
                findings.append(
                    Finding("LABEL_DIR_MISMATCH", "error", f"{label_dir.name}/{run_dir.name}",
                            f"目录标签 {label_dir.name} 与 manifest.label {label} 不一致")
                )
            family = manifest.get("family_id")
            if not isinstance(family, str) or not family:
                findings.append(
                    Finding("FAMILY_MISSING", "error", f"{label_dir.name}/{run_dir.name}",
                            "manifest 缺少 family_id，无法做整族划分")
                )
                continue
            if run_dir.name in seen:
                findings.append(
                    Finding("RUN_ID_DUP", "error", run_dir.name,
                            f"run_id 重复，同时出现在 {seen[run_dir.name]} 与 {label_dir.name}")
                )
                continue
            seen[run_dir.name] = label_dir.name
            runs.append(
                RunInfo(
                    run_id=run_dir.name,
                    path=run_dir,
                    label=label,
                    family=family,
                    service=str(manifest.get("service_id") or ""),
                )
            )
    if not runs and not findings:
        findings.append(Finding("NO_RUNS", "error", str(raw), "raw 下没有可用 run"))
    return runs, findings


def assign_splits(
    runs: Iterable[RunInfo],
    test_families: Iterable[str] = (),
    validation_families: Iterable[str] = (),
) -> tuple[dict[str, str], list[Finding]]:
    """按 family 整族分配。返回 {run_id: split} 与发现列表。"""
    runs = list(runs)
    test_set = {f for f in test_families if f}
    val_set = {f for f in validation_families if f}
    findings: list[Finding] = []

    family_labels: dict[str, set[str]] = {}
    family_runs: dict[str, list[RunInfo]] = {}
    for run in runs:
        family_labels.setdefault(run.family, set()).add(run.label)
        family_runs.setdefault(run.family, []).append(run)

    known = set(family_labels)
    for extra in sorted((test_set | val_set) - known):
        findings.append(
            Finding("FAMILY_UNKNOWN", "warning", "splits", f"指定的 family {extra!r} 在 raw 中不存在")
        )

    split_of_family: dict[str, str] = {}
    for family, labels in sorted(family_labels.items()):
        if len(labels) > 1:
            findings.append(
                Finding("FAMILY_MIXED_LABEL", "warning", family,
                        f"同一 family 混有多个 label：{sorted(labels)}；请确认这是同一业务族")
            )
        if family in test_set and family in val_set:
            findings.append(
                Finding("FAMILY_CONFLICT", "error", family,
                        "同一 family 同时被指定为 test 与 validation")
            )
            continue
        if family in test_set:
            split_of_family[family] = "test"
        elif family in val_set:
            split_of_family[family] = "validation"
        else:
            split_of_family[family] = "train"
            bad = [r for r in family_runs[family] if r.label != "normal"]
            if bad:
                findings.append(
                    Finding(
                        "FAMILY_NOT_TRAINABLE",
                        "error",
                        family,
                        f"family {family} 含非 normal run {[r.run_id for r in bad]}，"
                        "必须用 --test-family/--validation-family 显式指定，不能落进 train",
                    )
                )

    assignment: dict[str, str] = {
        run.run_id: split_of_family[run.family]
        for run in runs
        if run.family in split_of_family
    }
    return assignment, findings


# ---------------------------------------------------------------------------
# 生成 dataset
# ---------------------------------------------------------------------------


def build_dataset(
    raw: Path,
    out: Path,
    *,
    dataset_id: str | None = None,
    seed: int = 7,
    test_families: Iterable[str] = (),
    validation_families: Iterable[str] = (),
    force: bool = False,
) -> Report:
    rep = Report(str(out), "dataset")
    dataset_id = dataset_id or out.name

    runs, scan_findings = scan_raw(raw)
    rep.findings.extend(scan_findings)
    if not runs:
        return rep

    assignment, split_findings = assign_splits(runs, test_families, validation_families)
    rep.findings.extend(split_findings)
    if rep.errors:
        return rep

    # 逐个 run 质检：不通过就排除，并写清原因
    accepted: list[RunInfo] = []
    exclusions: list[dict[str, Any]] = []
    per_run_quality: dict[str, Any] = {}
    for run in runs:
        sub = validate_run(run.path)
        codes = sorted({f.code for f in sub.errors})
        per_run_quality[run.run_id] = {
            "status": sub.status,
            "error": len(sub.errors),
            "warning": len(sub.warnings),
            "error_codes": codes,
            "report": sub.to_dict(),
        }
        for gap in sub.contract_gaps:
            if gap not in rep.contract_gaps:
                rep.contract_gaps.append(gap)
        for item in sub.unverified:
            if item not in rep.unverified:
                rep.unverified.append(item)
        if sub.errors:
            exclusions.append(
                {
                    "run_id": run.run_id,
                    "label": run.label,
                    "reason": "quality_failed",
                    "error_codes": codes,
                }
            )
            rep.warn("RUN_EXCLUDED", run.run_id, f"质检未通过，已排除：{codes}")
        else:
            accepted.append(run)

    split_counts = {"train": 0, "validation": 0, "test": 0}
    for run in accepted:
        split_counts[assignment[run.run_id]] += 1
    if split_counts["test"] == 0:
        rep.warn("TEST_EMPTY", "splits", "test 为空，无法冻结最终测试集")
    if split_counts["validation"] == 0:
        rep.warn("VALIDATION_EMPTY", "splits", "validation 为空，参数选择没有独立验证集")
    if not accepted:
        rep.error("NO_ACCEPTED_RUNS", "dataset", "没有任何 run 通过质检，dataset 未生成")
        return rep

    # 落盘（只清理 F 自己的输出目录）
    if out.exists():
        if not force:
            rep.error(
                "DATASET_EXISTS",
                str(out),
                "输出目录已存在；确认要重建请加 --force（只影响 F 的 processed 目录）",
            )
            return rep
        _safe_rmtree(out)
    (out / "runs").mkdir(parents=True, exist_ok=True)

    run_entries: list[dict[str, Any]] = []
    for run in sorted(accepted, key=lambda r: r.run_id):
        dest = out / "runs" / run.run_id
        shutil.copytree(run.path, dest)  # 字节副本；不修改 raw
        run_entries.append(
            {
                "run_id": run.run_id,
                "label": run.label,
                "family_id": run.family,
                "service_id": run.service,
                "split": assignment[run.run_id],
                "run_dir": f"runs/{run.run_id}",
                "payload_sha256": sha256_file(dest / CHECKSUMS_FILE),
            }
        )

    splits_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "seed": seed,
        "split_unit": "family",
        "frozen": False,
        "train": sorted(r["run_id"] for r in run_entries if r["split"] == "train"),
        "validation": sorted(r["run_id"] for r in run_entries if r["split"] == "validation"),
        "test": sorted(r["run_id"] for r in run_entries if r["split"] == "test"),
        "families": {
            split: sorted(
                {r["family_id"] for r in run_entries if r["split"] == split}
            )
            for split in ("train", "validation", "test")
        },
    }

    dataset_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "created_by": "F",
        "created_at": utc_now(),
        "seed": seed,
        "split_unit": "family",
        "runs": run_entries,
        "exclusions": exclusions,
        "contract_gaps": rep.contract_gaps,
    }

    quality_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "created_at": utc_now(),
        "summary": {
            "runs_total": len(runs),
            "runs_accepted": len(accepted),
            "runs_excluded": len(exclusions),
            "by_split": split_counts,
            "raw_only": True,
        },
        "schema_validation": {
            "status": "not_checked",
            "note": "B 的 Dataset.validate 尚未发布；当前只做 F 的业务质量检查",
        },
        "runs": {run_id: item["report"] for run_id, item in per_run_quality.items()},
        "exclusions": exclusions,
        "contract_gaps": rep.contract_gaps,
        "unverified": rep.unverified,
    }

    _write_json(out / "dataset.json", dataset_payload)
    _write_json(out / "splits.json", splits_payload)
    _write_json(out / "quality_report.json", quality_payload)

    lines = []
    for name in ("dataset.json", "splits.json", "quality_report.json"):
        lines.append(f"{sha256_file(out / name)}  {name}")
    for entry in run_entries:
        rel = f"{entry['run_dir']}/{CHECKSUMS_FILE}"
        lines.append(f"{sha256_file(out / rel)}  {rel}")
    (out / CHECKSUMS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

    rep.check("dataset_written", "passed", f"{len(accepted)} runs -> {out}")
    rep.info(
        "SPLIT_SUMMARY",
        "splits",
        f"train={split_counts['train']} validation={split_counts['validation']} test={split_counts['test']} "
        f"excluded={len(exclusions)}",
    )
    return rep


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _read_manifest(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_rmtree(path: Path) -> None:
    """只允许删除 F 自己的输出目录：拒绝盘符根、家目录、当前仓库根。"""
    resolved = path.resolve()
    if len(resolved.parts) < 3:
        raise SystemExit(f"拒绝删除过浅的路径：{resolved}")
    if resolved == resolved.anchor:
        raise SystemExit(f"拒绝删除根路径：{resolved}")
    shutil.rmtree(resolved)


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdio()
    parser = argparse.ArgumentParser(description="生成 processed dataset 与划分（任务 F）")
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-id", dest="dataset_id", default=None)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--test-family", action="append", default=[])
    parser.add_argument("--validation-family", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    rep = build_dataset(
        args.raw,
        args.out,
        dataset_id=args.dataset_id,
        seed=args.seed,
        test_families=args.test_family,
        validation_families=args.validation_family,
        force=args.force,
    )
    counts = rep.to_dict()["counts"]
    print(f"[{rep.status.upper()}] {rep.target}")
    print(
        f"  error={counts['error']} warning={counts['warning']} "
        f"not_checked={counts['not_checked']} contract_gap={counts['contract_gap']}"
    )
    for finding in rep.findings[:30]:
        print(f"  - {finding.severity:<7} {finding.code:<24} {finding.locator}: {finding.message}")
    if rep.errors:
        return EXIT_PRECONDITION_FAILED if any(f.code == "DATASET_EXISTS" for f in rep.errors) else EXIT_DATA_INVALID
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
