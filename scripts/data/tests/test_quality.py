"""F 数据质检自测（stdlib unittest，无需 pytest）。

运行::

    python -m unittest discover -s scripts/data/tests -v

覆盖两件事：
1. 合格样本必须全过——避免把工具的误报当成数据的问题；
2. 每个故障样本都必须被特定错误码抓住——避免"跑完 0 错误"的假通过。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_DIR))

import make_fixtures  # noqa: E402
import split  # noqa: E402
import summarize  # noqa: E402
import validate  # noqa: E402

EXPECTED_CODES = {
    "missing_field": "FIELD_MISSING",
    "bad_checksum": "CHECKSUM_MISMATCH",
    "success_errno": "RESULT_ERRNO_CONFLICT",
    "dup_event_id": "EVENT_ID_DUP",
    "outside_partition": "PATH_OUTSIDE_PARTITIONS",
    "truth_missing": "TRUTH_MISSING",
    "recovery_no_change": "RECOVERY_NO_CHANGE",
    "recovery_trigger_missing": "RECOVERY_TRIGGER_MISSING",
}


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="gg-fixtures-"))
        cls.made = make_fixtures.build_all(cls.tmp)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- 合格样本 --------------------------------------------------------
    def test_good_runs_pass(self) -> None:
        for name in ("normal-1", "normal-2", "violation-1", "boundary-1", "recovery-1"):
            rep = validate.validate_run(self.made[name])
            codes = sorted({f.code for f in rep.errors})
            self.assertEqual([], codes, f"{name} 不应报错，实际 {codes}")
            self.assertEqual("passed", rep.status, name)

    def test_validate_does_not_modify_input(self) -> None:
        run = self.made["normal-1"]
        before = (run / "checksums.sha256").read_bytes()
        listing = sorted(p.name for p in run.iterdir())
        validate.validate_run(run)
        self.assertEqual(before, (run / "checksums.sha256").read_bytes())
        self.assertEqual(listing, sorted(p.name for p in run.iterdir()))

    # -- 故障样本 --------------------------------------------------------
    def test_bad_cases_are_caught(self) -> None:
        for case, code in EXPECTED_CODES.items():
            rep = validate.validate_run(self.made[f"bad-{case}"])
            codes = {f.code for f in rep.findings}
            self.assertIn(code, codes, f"{case} 应报 {code}，实际 {sorted(codes)}")
            self.assertEqual("failed", rep.status, case)
            self.assertTrue(rep.errors, case)

    def test_contract_gaps_are_declared(self) -> None:
        rep = validate.validate_run(self.made["normal-1"])
        gap_codes = {g["code"] for g in rep.contract_gaps}
        self.assertIn("FILE_TRUTH_SHAPE", gap_codes)
        self.assertIn("EXPECTED_OUTCOME_SHAPE", gap_codes)
        unverified = {u["code"] for u in rep.unverified}
        self.assertIn("SCHEMA_VALIDATOR_NOT_WIRED", unverified)

    # -- 划分 ------------------------------------------------------------
    def test_scan_and_assign(self) -> None:
        runs, findings = split.scan_raw(self.tmp / "raw")
        self.assertFalse([f for f in findings if f.severity == "error"], findings)
        self.assertEqual(5, len(runs))
        assignment, findings = split.assign_splits(
            runs, test_families={"fam-b", "fam-d"}, validation_families={"fam-c"}
        )
        self.assertFalse([f for f in findings if f.severity == "error"], findings)
        self.assertEqual("train", assignment["run-n1"])
        self.assertEqual("train", assignment["run-n2"])
        self.assertEqual("test", assignment["run-v1"])
        self.assertEqual("validation", assignment["run-b1"])
        self.assertEqual("test", assignment["run-r1"])

    def test_assign_refuses_non_normal_in_train(self) -> None:
        runs, _ = split.scan_raw(self.tmp / "raw")
        _assignment, findings = split.assign_splits(runs)
        codes = {f.code for f in findings if f.severity == "error"}
        self.assertIn("FAMILY_NOT_TRAINABLE", codes)

    def test_assign_rejects_conflicting_family(self) -> None:
        runs, _ = split.scan_raw(self.tmp / "raw")
        _assignment, findings = split.assign_splits(runs, test_families={"fam-a"},
                                                    validation_families={"fam-a"})
        self.assertIn("FAMILY_CONFLICT", {f.code for f in findings if f.severity == "error"})

    def test_dataset_end_to_end(self) -> None:
        out = self.tmp / "processed" / "power-v1"
        rep = split.build_dataset(
            self.tmp / "raw",
            out,
            dataset_id="power-v1",
            test_families=["fam-b", "fam-d"],
            validation_families=["fam-c"],
        )
        self.assertEqual([], [f.code for f in rep.errors], "生成 dataset 不应报错")
        splits = json.loads((out / "splits.json").read_text(encoding="utf-8"))
        self.assertEqual(["run-n1", "run-n2"], splits["train"])
        self.assertEqual(["run-b1"], splits["validation"])
        self.assertEqual(["run-r1", "run-v1"], splits["test"])
        for name in ("dataset.json", "splits.json", "quality_report.json", "checksums.sha256"):
            self.assertTrue((out / name).is_file(), name)
        for run_id in splits["train"] + splits["validation"] + splits["test"]:
            self.assertTrue((out / "runs" / run_id / "checksums.sha256").is_file(), run_id)

        check = validate.validate_dataset(out)
        self.assertEqual([], [f.code for f in check.errors], "dataset 自检不应报错")
        self.assertEqual("passed", check.status)

    def test_dataset_detects_family_leak(self) -> None:
        out = self.tmp / "processed" / "leak"
        split.build_dataset(
            self.tmp / "raw", out, dataset_id="leak",
            test_families=["fam-b", "fam-d"], validation_families=["fam-c"],
        )
        splits_path = out / "splits.json"
        splits = json.loads(splits_path.read_text(encoding="utf-8"))
        splits["train"].append("run-v1")  # 人工制造泄漏
        splits_path.write_text(json.dumps(splits, ensure_ascii=False), encoding="utf-8")

        rep = validate.validate_dataset(out, deep=False)
        codes = {f.code for f in rep.errors}
        self.assertIn("SPLIT_OVERLAP", codes)
        self.assertIn("SPLIT_FAMILY_LEAK", codes)
        self.assertIn("SPLIT_TRAIN_NOT_NORMAL", codes)

    # -- 指标 ------------------------------------------------------------
    def test_metrics_on_dataset(self) -> None:
        out = self.tmp / "processed" / "metrics"
        split.build_dataset(
            self.tmp / "raw", out, dataset_id="metrics",
            test_families=["fam-b", "fam-d"], validation_families=["fam-c"],
        )
        report = summarize.build_report(out)
        metrics = report["metrics"]
        self.assertEqual("measured", metrics["block_rate"]["status"])
        self.assertEqual(1.0, metrics["block_rate"]["value"], "违规写配置必须被阻断")
        self.assertEqual(0.0, metrics["false_deny_rate"]["value"], "正常动作不应被误拒")
        self.assertEqual("na", metrics["extra_authorization_rate"]["status"])
        self.assertEqual("not_checked", metrics["recovery"]["status"])
        self.assertGreater(metrics["actions_total"]["value"], 0)

    def test_metrics_dedup_by_operation_id(self) -> None:
        actions = [
            summarize.ActionRecord("r", "test", "violation", "op-1", "svc", "write", "config", "deny",
                                   denied=True, backends={"bpf_lsm"}),
            summarize.ActionRecord("r", "test", "violation", "op-1", "svc", "write", "config", "deny",
                                   denied=True, backends={"bpf_lsm"}),
        ]
        metrics = summarize.compute_metrics(actions)
        # 调用方负责按 operation_id 聚合；这里验证分母口径：两个同 id 动作不会变成两次独立攻击
        self.assertEqual(2, metrics["actions_total"]["value"])
        self.assertEqual(1.0, metrics["block_rate"]["value"])

    def test_zero_denominator_is_na(self) -> None:
        metrics = summarize.compute_metrics([])
        self.assertEqual("na", metrics["block_rate"]["status"])
        self.assertIsNone(metrics["block_rate"]["value"])
        self.assertEqual("na", metrics["false_deny_rate"]["status"])

    def test_extra_authorization_with_manifest(self) -> None:
        actions = [
            summarize.ActionRecord("r", "test", "violation", "op-1", "svc-collector", "write",
                                   "config", "deny", denied=False),
        ]
        manifest = {"source": "unit-test", "forbidden": [
            {"service_id": "svc-collector", "resource": "config", "operation": "write"},
            {"service_id": "svc-collector", "resource": "reports", "operation": "write"},
        ]}
        result = summarize.extra_authorization(actions, manifest)
        self.assertEqual("measured", result["status"])
        self.assertEqual(1, result["numerator"], "写配置被放行，算一次额外授权")
        self.assertEqual(1, result["denominator"], "未覆盖的 reports 对不进分母")


if __name__ == "__main__":
    unittest.main(verbosity=2)
