"""F 自造的 fixture 生成器（**不是** B 的正式 fixture）。

B 在 G0 交付 schema 3.0 的官方 fixture；本文件只用于 F 自己验证质检管道，
以及给 split / summarize 提供可复现输入。生成物放在 tmp/ 下（已 gitignore）。

用法::

    python scripts/data/make_fixtures.py --out tmp/fixtures
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import CHECKSUMS_FILE, PAYLOAD_FILES, enable_utf8_stdio  # noqa: E402

SANDBOX = "/home/gg/data/sandbox/sbx-001"
LIVE = f"{SANDBOX}/live"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _event(
    seq: int,
    run_id: str,
    *,
    service: str,
    operation_id: str,
    operation: str,
    path: str,
    result: str = "success",
    errno: int = 0,
    flags: str = "O_RDONLY",
    **over: Any,
) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "schema_version": "3.0",
        "event_id": f"{run_id}:ebpf:{seq:03d}",
        "run_id": run_id,
        "service_id": service,
        "instance_id": "inst-001",
        "operation_id": operation_id,
        "ts": f"2026-11-24T05:00:{seq:02d}Z",
        "monotonic_ns": 1_000_000 * seq,
        "clock_id": 1,
        "pid": 4200 + seq,
        "tgid": 4200,
        "starttime": 987654,
        "cgroup_id": 1234,
        "comm": "power-gateway",
        "exe": "/opt/gg/bin/power-gateway",
        "syscall": "openat",
        "path": path,
        "flags": flags,
        "operation": operation,
        "result": result,
        "errno": errno,
        "source": "ebpf",
        "resource_id": f"res-{seq:03d}",
        "policy_version": "pv-001",
        "evidence_kind": "real",
    }
    ev.update(over)
    return ev


def _scenario(label: str, service: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (operations, expected_outcomes)。真值由场景预设，不由 verdict 回填。"""
    if label == "recovery":
        return (
            [
                {"operation_id": "op-1", "operation": "write", "path": f"{LIVE}/telemetry/rec-0001.json"},
                {"operation_id": "op-2", "operation": "read", "path": f"{LIVE}/telemetry/rec-0001.json"},
            ],
            [
                {"operation_id": "op-1", "expected": "allow"},
                {"operation_id": "op-2", "expected": "allow"},
            ],
        )
    if label == "violation":
        return (
            [
                {"operation_id": "op-1", "operation": "read", "path": f"{LIVE}/telemetry/rec-0001.json"},
                {"operation_id": "op-2", "operation": "write", "path": f"{LIVE}/config/device.json"},
            ],
            [
                {"operation_id": "op-1", "expected": "allow"},
                {"operation_id": "op-2", "expected": "deny"},
            ],
        )
    if label == "boundary":
        return (
            [
                {"operation_id": "op-1", "operation": "write", "path": f"{LIVE}/telemetry/rec-0002.json"},
                {"operation_id": "op-2", "operation": "open", "path": f"{LIVE}/config/device.json"},
            ],
            [
                {"operation_id": "op-1", "expected": "allow"},
                {"operation_id": "op-2", "expected": "deny"},
            ],
        )
    return (
        [
            {"operation_id": "op-1", "operation": "read", "path": f"{LIVE}/config/device.json"},
            {"operation_id": "op-2", "operation": "write", "path": f"{LIVE}/telemetry/rec-0001.json"},
            {"operation_id": "op-3", "operation": "write", "path": f"{LIVE}/logs/gateway.log"},
        ],
        [
            {"operation_id": "op-1", "expected": "allow"},
            {"operation_id": "op-2", "expected": "allow"},
            {"operation_id": "op-3", "expected": "allow"},
        ],
    )


def build_run(
    run_dir: Path,
    *,
    run_id: str,
    label: str,
    family: str,
    service: str = "svc-collector",
    seed: int = 7,
    guard: str = "enforced",
    mutate: str | None = None,
) -> Path:
    """生成一个结构完整的 run 包，可按 mutate 注入单点故障。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    operations, expected = _scenario(label, service)

    if label == "recovery":
        events = [
            _event(1, run_id, service=service, operation_id="op-1", operation="write",
                   path=f"{LIVE}/telemetry/rec-0001.json", flags="O_WRONLY|O_CREAT"),
            _event(2, run_id, service=service, operation_id="op-2", operation="read",
                   path=f"{LIVE}/telemetry/rec-0001.json"),
        ]
    elif label == "violation":
        events = [
            _event(1, run_id, service=service, operation_id="op-1", operation="read",
                   path=f"{LIVE}/telemetry/rec-0001.json"),
            _event(2, run_id, service=service, operation_id="op-2", operation="write",
                   path=f"{LIVE}/config/device.json", flags="O_WRONLY|O_CREAT",
                   result="failed", errno=13),
        ]
    elif label == "boundary":
        events = [
            _event(1, run_id, service=service, operation_id="op-1", operation="write",
                   path=f"{LIVE}/telemetry/rec-0002.json", flags="O_WRONLY|O_CREAT"),
            _event(2, run_id, service=service, operation_id="op-2", operation="open",
                   path=f"{LIVE}/config/device.json", flags="O_RDWR",
                   result="failed", errno=13),
        ]
    else:
        events = [
            _event(1, run_id, service=service, operation_id="op-1", operation="read",
                   path=f"{LIVE}/config/device.json"),
            _event(2, run_id, service=service, operation_id="op-2", operation="write",
                   path=f"{LIVE}/telemetry/rec-0001.json", flags="O_WRONLY|O_CREAT"),
            _event(3, run_id, service=service, operation_id="op-3", operation="write",
                   path=f"{LIVE}/logs/gateway.log", flags="O_WRONLY|O_APPEND"),
        ]

    decisions: list[dict[str, Any]] = []
    if guard == "enforced":
        truth = {item["operation_id"]: item["expected"] for item in expected}
        for seq, ev in enumerate(events, 1):
            oid = ev["operation_id"]
            deny = truth.get(oid) == "deny"
            decisions.append(
                {
                    "schema_version": "3.0",
                    "decision_id": f"{run_id}:dec:{seq:03d}",
                    "event_id": ev["event_id"],
                    "operation_id": oid,
                    "run_id": run_id,
                    "backend": "bpf_lsm",
                    "requested_action": ev["operation"],
                    "verdict": "deny" if deny else "allow",
                    "enforced": True,
                    "reason": "超出职责分区" if deny else "命中 allow 规则",
                    "rule_id": f"rule-{oid}",
                    "policy_version": "pv-001",
                }
            )

    op_index = {item["operation_id"]: item for item in operations}
    outcomes = [
        {
            "schema_version": "3.0",
            "run_id": run_id,
            "operation_id": item["operation_id"],
            "operation": op_index[item["operation_id"]]["operation"],
            "result": "failed" if item["expected"] == "deny" else "success",
            "errno": 13 if item["expected"] == "deny" else 0,
            "observed_path": op_index[item["operation_id"]]["path"],
        }
        for item in expected
    ]

    initial = [
        {
            "path": f"{LIVE}/config/device.json",
            "content_sha256": content_hash('{"ct_ratio":120,"baud":9600}'),
            "mode": "0644",
            "uid": 1000,
            "gid": 1000,
            "biz_seq": 1,
        }
    ]
    final = list(initial)
    if label == "recovery":
        initial.append(
            {"path": f"{LIVE}/telemetry/rec-0001.json", "content_sha256": content_hash("V=220.1,I=5.02"),
             "mode": "0644", "uid": 1000, "gid": 1000, "biz_seq": 10}
        )
        final.append(
            {"path": f"{LIVE}/telemetry/rec-0001.json", "content_sha256": content_hash("V=0.0,I=0.0"),
             "mode": "0644", "uid": 1000, "gid": 1000, "biz_seq": 10}
        )
    else:
        final += [
            {"path": f"{LIVE}/telemetry/rec-0001.json", "content_sha256": content_hash("V=220.1,I=5.02"),
             "mode": "0644", "uid": 1000, "gid": 1000, "biz_seq": 10},
            {"path": f"{LIVE}/logs/gateway.log", "content_sha256": content_hash("sample ok"),
             "mode": "0640", "uid": 1000, "gid": 1000, "biz_seq": 11},
        ]

    manifest = {
        "schema_version": "3.0",
        "scenario_id": f"scn-{label}",
        "family_id": family,
        "service_id": service,
        "label": label,
        "seed": seed,
        "sandbox_id": "sbx-001",
        "operations": operations,
        "preconditions": [{"check": "dac_allows_without_guard", "result": "passed"}],
        "expected_outcomes": expected,
        "recovery_trigger": "manual_test" if label == "recovery" else None,
    }

    metadata = {
        "schema_version": "3.0",
        "os": "Ubuntu 24.04 LTS",
        "kernel": "6.8.0-generic",
        "commit": "fixture",
        "seed": seed,
        "clock_id": 1,
        "mode": "enforcing" if guard == "enforced" else "learning",
        "backend": "bpf_lsm",
        "toolchain": {"clang": "18.1.3", "libbpf": "1.4.0", "bpftool": "7.4.0"},
        "collection": {"lost_events": 0},
    }

    # --- 故障注入（在写载荷之前） --------------------------------------
    if mutate == "missing_field":
        events[0].pop("path", None)
    elif mutate == "success_errno":
        events[1]["errno"] = 13
    elif mutate == "dup_event_id":
        events[1]["event_id"] = events[0]["event_id"]
    elif mutate == "outside_partition":
        events[1]["path"] = f"{LIVE}/../policy/allow.list"
    elif mutate == "truth_missing":
        manifest["expected_outcomes"] = []
    elif mutate == "recovery_no_change":
        final = [dict(e) for e in initial]
    elif mutate == "recovery_trigger_missing":
        manifest["recovery_trigger"] = None

    _write_jsonl(run_dir / "events.jsonl", events)
    _write_jsonl(run_dir / "decisions.jsonl", decisions)
    _write_jsonl(run_dir / "outcomes.jsonl", outcomes)
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "metadata.json", metadata)
    _write_json(run_dir / "initial_files.json", initial)
    _write_json(run_dir / "final_files.json", final)
    _write_checksums(run_dir)

    if mutate == "bad_checksum":
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(events[0], ensure_ascii=False) + "\n")

    return run_dir


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def _write_checksums(run_dir: Path) -> None:
    lines = []
    for name in PAYLOAD_FILES:
        digest = hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (run_dir / CHECKSUMS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


BAD_CASES: dict[str, tuple[str, str]] = {
    "missing_field": ("missing_field", "normal"),
    "bad_checksum": ("bad_checksum", "normal"),
    "success_errno": ("success_errno", "normal"),
    "dup_event_id": ("dup_event_id", "normal"),
    "outside_partition": ("outside_partition", "normal"),
    "truth_missing": ("truth_missing", "violation"),
    "recovery_no_change": ("recovery_no_change", "recovery"),
    "recovery_trigger_missing": ("recovery_trigger_missing", "recovery"),
}


def build_all(out: Path, *, force: bool = True) -> dict[str, Path]:
    if out.exists() and force:
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    made: dict[str, Path] = {}

    raw = out / "raw"
    made["normal-1"] = build_run(
        raw / "normal" / "run-n1", run_id="run-n1", label="normal", family="fam-a", seed=7
    )
    made["normal-2"] = build_run(
        raw / "normal" / "run-n2", run_id="run-n2", label="normal", family="fam-a", seed=11
    )
    made["violation-1"] = build_run(
        raw / "violation" / "run-v1", run_id="run-v1", label="violation", family="fam-b", seed=7
    )
    made["boundary-1"] = build_run(
        raw / "boundary" / "run-b1", run_id="run-b1", label="boundary", family="fam-c", seed=7
    )
    made["recovery-1"] = build_run(
        raw / "recovery" / "run-r1", run_id="run-r1", label="recovery", family="fam-d", seed=7
    )

    for case, (mutate, label) in BAD_CASES.items():
        made[f"bad-{case}"] = build_run(
            out / "bad" / case / f"run-{case}",
            run_id=f"run-{case}",
            label=label,
            family=f"fam-{case}",
            mutate=mutate,
        )
    return made


def main(argv: list[str] | None = None) -> int:
    enable_utf8_stdio()
    parser = argparse.ArgumentParser(description="生成 F 自造 fixture（非 B 正式 fixture）")
    parser.add_argument("--out", type=Path, default=Path("tmp/fixtures"))
    args = parser.parse_args(argv)
    made = build_all(args.out)
    print(f"生成 {len(made)} 个 run 包 -> {args.out}")
    for name, path in sorted(made.items()):
        print(f"  {name:<24} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
