"""GateGuard 数据质检公共辅助（任务 F，契约 3.0）。

设计原则
--------
1. 只读：本模块只打开输入包，绝不写入 data/raw/ 或其他角色的目录。
2. 不定义 schema：schema 归 B（src/gateguard/contracts/）。这里只放 08 契约
   文档中已经冻结的枚举、载荷文件名，以及读取/校验原语。
3. 三态：能判定的记 passed/failed；无法判定的记 not_checked，绝不默认通过。
4. 零第三方依赖，可在 Windows 离线运行；不 resolve Linux 路径。

F 的检查对象是"业务质量与真值一致性"，不是 schema 结构本身。B 的
Dataset.validate 接入后，两者结果并列写进 quality_report.json。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

TOOL_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# 08 契约冻结的常量
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "3.0"

PAYLOAD_FILES: tuple[str, ...] = (
    "events.jsonl",
    "decisions.jsonl",
    "outcomes.jsonl",
    "manifest.json",
    "metadata.json",
    "initial_files.json",
    "final_files.json",
)
CHECKSUMS_FILE = "checksums.sha256"

MODES = {"learning", "permissive", "enforcing"}
LABELS = {"normal", "violation", "boundary", "recovery"}
OPERATIONS = {
    "open",
    "read",
    "write",
    "create",
    "remove",
    "rename",
    "truncate",
    "mmap_write",
    "exec",
    "connect",
}
RESULTS = {"success", "failed", "unknown"}
VERDICTS = {"allow", "deny", "would_deny", "unsupported"}
EVIDENCE_KINDS = {"real", "fixture", "simulated_input"}
CAPABILITY_STATUS = {"supported", "unsupported", "unverified"}
POLICY_STATUS = {"candidate", "validated", "approved", "installed"}
CHECK_STATUS = {"passed", "failed", "not_checked"}
INCIDENT_STATES = {
    "detected",
    "isolating",
    "isolated",
    "evidence_saved",
    "stopping",
    "stopped",
    "recovering",
    "verifying",
    "restored",
    "failed",
    "rescue_required",
}
SNAPSHOT_KINDS = {"baseline", "periodic", "incident"}
SNAPSHOT_TRUST_STATUS = {"unverified", "validated", "approved", "rejected"}

#: 08 §3 Event 的必需字段（键必须存在；部分允许 null）
EVENT_FIELDS: tuple[str, ...] = (
    "schema_version",
    "event_id",
    "run_id",
    "service_id",
    "instance_id",
    "operation_id",
    "ts",
    "monotonic_ns",
    "clock_id",
    "pid",
    "tgid",
    "starttime",
    "cgroup_id",
    "comm",
    "exe",
    "syscall",
    "path",
    "flags",
    "operation",
    "result",
    "errno",
    "source",
    "resource_id",
    "policy_version",
    "evidence_kind",
)

#: 这些字段有值时才能支撑审计与学习，null 视为缺证据
EVENT_REQUIRED_NON_NULL: tuple[str, ...] = (
    "schema_version",
    "event_id",
    "run_id",
    "service_id",
    "instance_id",
    "ts",
    "monotonic_ns",
    "clock_id",
    "operation",
    "result",
    "source",
    "evidence_kind",
)

#: 08 §3 ScenarioManifest
MANIFEST_FIELDS: tuple[str, ...] = (
    "schema_version",
    "scenario_id",
    "family_id",
    "service_id",
    "label",
    "seed",
    "sandbox_id",
    "operations",
    "preconditions",
    "expected_outcomes",
    "recovery_trigger",
)

#: 08 §3 Decision
DECISION_FIELDS: tuple[str, ...] = (
    "schema_version",
    "decision_id",
    "event_id",
    "operation_id",
    "run_id",
    "backend",
    "requested_action",
    "verdict",
    "enforced",
    "reason",
    "rule_id",
    "policy_version",
)

#: 业务逻辑资源分区（08 §1、介绍书 §3.1）
LOGICAL_ROOTS: tuple[str, ...] = ("config", "telemetry", "reports", "logs")

#: 08 §7 退出码
EXIT_OK = 0
EXIT_DATA_INVALID = 2
EXIT_PLATFORM_UNSUPPORTED = 3
EXIT_PRECONDITION_FAILED = 4
EXIT_RUNTIME_FAILED = 5

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_LIVE_MARKER = "/live/"


# ---------------------------------------------------------------------------
# 报告结构
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """一条质检发现。severity: error 必须修；warning 需人工确认；info 仅记录。"""

    code: str
    severity: str
    locator: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "locator": self.locator,
            "message": self.message,
        }


@dataclass
class Report:
    target: str
    kind: str  # run | dataset
    findings: list[Finding] = field(default_factory=list)
    contract_gaps: list[dict[str, str]] = field(default_factory=list)
    unverified: list[dict[str, str]] = field(default_factory=list)
    checks: list[dict[str, str]] = field(default_factory=list)

    # -- 记录 ------------------------------------------------------------
    def add(self, code: str, severity: str, locator: str, message: str) -> None:
        self.findings.append(Finding(code, severity, locator, message))

    def error(self, code: str, locator: str, message: str) -> None:
        self.add(code, "error", locator, message)

    def warn(self, code: str, locator: str, message: str) -> None:
        self.add(code, "warning", locator, message)

    def info(self, code: str, locator: str, message: str) -> None:
        self.add(code, "info", locator, message)

    def check(self, name: str, status: str, detail: str = "") -> None:
        assert status in CHECK_STATUS
        self.checks.append({"name": name, "status": status, "detail": detail})

    def gap(self, code: str, message: str, owner: str = "B", needs: str = "") -> None:
        """记录 08 契约未规定、F 只能先假设的结构。交给 B 汇总升级契约。"""
        self.contract_gaps.append(
            {"code": code, "message": message, "owner": owner, "needs": needs}
        )

    def unverified_item(self, code: str, message: str, owner: str = "") -> None:
        self.unverified.append({"code": code, "message": message, "owner": owner})

    # -- 汇总 ------------------------------------------------------------
    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def status(self) -> str:
        if self.errors:
            return "failed"
        if self.checks:
            return "passed"
        return "not_checked"

    def to_dict(self) -> dict[str, Any]:
        codes: dict[str, int] = {}
        for f in self.findings:
            codes[f.code] = codes.get(f.code, 0) + 1
        return {
            "report_version": TOOL_VERSION,
            "generated_at": utc_now(),
            "kind": self.kind,
            "target": self.target,
            "status": self.status,
            "counts": {
                "error": len(self.errors),
                "warning": len(self.warnings),
                "info": len(self.findings) - len(self.errors) - len(self.warnings),
                "not_checked": len(self.unverified),
                "contract_gap": len(self.contract_gaps),
            },
            "code_counts": dict(sorted(codes.items())),
            "checks": self.checks,
            "findings": [f.to_dict() for f in self.findings],
            "contract_gaps": self.contract_gaps,
            "unverified": self.unverified,
        }


# ---------------------------------------------------------------------------
# 时间与哈希
# ---------------------------------------------------------------------------


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enable_utf8_stdio() -> None:
    """Windows 控制台默认用本地代码页（936），中文会乱码；统一改 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_valid_ts(value: Any) -> bool:
    return isinstance(value, str) and bool(_TS_RE.match(value))


# ---------------------------------------------------------------------------
# 读取（容错，不抛出、不修改输入）
# ---------------------------------------------------------------------------


def read_json_file(path: Path, report: Report, locator: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        report.error("FILE_MISSING", locator, f"缺少文件 {path.name}")
    except json.JSONDecodeError as exc:
        report.error(
            "JSON_INVALID", locator, f"{path.name} 不是合法 JSON：{exc.msg} (line {exc.lineno})"
        )
    except OSError as exc:  # 权限、编码等
        report.error("FILE_UNREADABLE", locator, f"无法读取 {path.name}：{exc}")
    return None


def iter_jsonl(path: Path, report: Report, locator: str) -> Iterator[tuple[int, dict[str, Any]]]:
    """逐行读取 JSONL。坏行记错误并跳过，保留行号便于定位。"""
    try:
        with path.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    report.error(
                        "JSONL_INVALID",
                        f"{locator}:{lineno}",
                        f"第 {lineno} 行不是合法 JSON：{exc.msg}",
                    )
                    continue
                if not isinstance(obj, dict):
                    report.error(
                        "JSONL_NOT_OBJECT", f"{locator}:{lineno}", f"第 {lineno} 行不是对象"
                    )
                    continue
                yield lineno, obj
    except FileNotFoundError:
        report.error("FILE_MISSING", locator, f"缺少文件 {path.name}")
    except OSError as exc:
        report.error("FILE_UNREADABLE", locator, f"无法读取 {path.name}：{exc}")


# ---------------------------------------------------------------------------
# checksums.sha256
# ---------------------------------------------------------------------------


def parse_checksums_file(path: Path) -> tuple[dict[str, str], list[tuple[int, str]]]:
    entries: dict[str, str] = {}
    problems: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return entries, [(0, "无法读取 checksums 文件")]
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            problems.append((lineno, line))
            continue
        digest, name = parts[0].lower(), parts[1].lstrip("*")
        if not _HEX64_RE.match(digest):
            problems.append((lineno, line))
            continue
        entries[name] = digest
    return entries, problems


def verify_checksums(root: Path, required: Iterable[str] = ()) -> list[Finding]:
    """校验 root/checksums.sha256；不把 checksums 自身计入载荷。"""
    findings: list[Finding] = []
    sums_path = root / CHECKSUMS_FILE
    if not sums_path.is_file():
        findings.append(
            Finding("CHECKSUM_FILE_MISSING", "error", CHECKSUMS_FILE, "缺少 checksums.sha256")
        )
        return findings

    entries, problems = parse_checksums_file(sums_path)
    for lineno, text in problems:
        findings.append(
            Finding(
                "CHECKSUM_LINE_INVALID",
                "error",
                f"{CHECKSUMS_FILE}:{lineno}",
                f"无法解析校验和行：{text}",
            )
        )

    if CHECKSUMS_FILE in entries:
        findings.append(
            Finding(
                "CHECKSUM_SELF_LISTED",
                "warning",
                CHECKSUMS_FILE,
                "checksums.sha256 不应包含自身（契约要求不包含自身）",
            )
        )

    for name in required:
        if name not in entries:
            findings.append(
                Finding("CHECKSUM_NOT_COVERED", "error", name, f"载荷文件 {name} 未被校验和覆盖")
            )

    for name, digest in sorted(entries.items()):
        target = root / name
        if not target.is_file():
            findings.append(
                Finding("CHECKSUM_ENTRY_MISSING_FILE", "error", name, f"校验和列出的 {name} 不存在")
            )
            continue
        actual = sha256_file(target)
        if actual != digest:
            findings.append(
                Finding(
                    "CHECKSUM_MISMATCH",
                    "error",
                    name,
                    f"{name} 内容与校验和不一致（记录 {digest[:12]}…，实际 {actual[:12]}…）",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 逻辑资源分区
# ---------------------------------------------------------------------------


def logical_root_of(path: Any) -> str | None:
    """从 Linux 绝对路径取 live/ 之后的第一段逻辑分区。

    - 不含 '/live/' 或 path 为 null：返回 None（无法判定，不下结论）
    - 指向 live 根目录本身：返回空串
    - 其余返回第一段目录名，由调用方比对 LOGICAL_ROOTS

    注意：Windows 离线程序不得对 Linux path 调用 realpath/resolve，
    这里只做字符串切分（08 §2）。
    """
    if not isinstance(path, str) or not path:
        return None
    norm = path.replace("\\", "/")
    idx = norm.find(_LIVE_MARKER)
    if idx < 0:
        return None
    rest = norm[idx + len(_LIVE_MARKER) :].lstrip("/")
    if not rest:
        return ""
    return rest.split("/", 1)[0]


def partition_problem(path: Any) -> str | None:
    """返回越界说明；None 表示合法或无法判定。"""
    root = logical_root_of(path)
    if root is None:
        return None
    if root == "":
        return "路径指向 live 根目录，不属于任何业务分区"
    if root not in LOGICAL_ROOTS:
        return f"路径位于业务分区之外：live/{root}/"
    return None


def rel_to_live(path: Any) -> str | None:
    if not isinstance(path, str) or not path:
        return None
    norm = path.replace("\\", "/")
    idx = norm.find(_LIVE_MARKER)
    if idx < 0:
        return None
    return norm[idx + len(_LIVE_MARKER) :].lstrip("/")


# ---------------------------------------------------------------------------
# 文件真值（initial_files / final_files）
# ---------------------------------------------------------------------------


def normalize_file_truth(payload: Any) -> tuple[dict[str, dict[str, Any]], str | None]:
    """把 initial/final 文件真值统一成 {path: entry}。

    08 只规定"内容、声明元数据与业务序号"，没有冻结外层结构，因此这里
    同时接受 [entry, ...] 与 {"files": [entry, ...]}；两种都不匹配时返回
    (空字典, 原因)，由调用方记为 contract gap，而不是编造结构。
    """
    entries: Any
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict) and isinstance(payload.get("files"), list):
        entries = payload["files"]
    elif isinstance(payload, dict) and all(
        isinstance(v, dict) for v in payload.values()
    ) and payload:
        # {"telemetry/x.json": {...}} 形式
        entries = [dict({"path": k}, **v) for k, v in payload.items()]
    else:
        return {}, "既不是条目列表，也不是 {files: [...]} 或 {path: entry}"

    out: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        out[path] = item
    if not out:
        return {}, "条目中没有可用的 path 字段"
    return out, None


def entry_content_hash(entry: dict[str, Any]) -> str | None:
    for key in ("content_sha256", "sha256", "content_hash"):
        value = entry.get(key)
        if isinstance(value, str) and _HEX64_RE.match(value.lower()):
            return value.lower()
    return None


def entry_business_seq(entry: dict[str, Any]) -> Any:
    for key in ("biz_seq", "business_seq", "sequence", "record_seq"):
        if key in entry:
            return entry[key]
    return None
