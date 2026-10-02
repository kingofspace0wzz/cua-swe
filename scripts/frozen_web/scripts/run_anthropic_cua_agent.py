#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fnmatch
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import resource
import shlex
import stat
import subprocess
import tempfile
import time
from typing import Any
import unicodedata
import uuid
import sys

import requests

from provider_client import ProviderError, ProviderTransport


TOOLS = [
    {
        "name": "shell",
        "description": (
            "Run a shell command in the task workspace. Use the CUA-SWE adapter "
            "CLI described in the prompt for every browser observation/action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_sec": {"type": "integer", "minimum": 1, "maximum": 180},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "view_image",
        "description": (
            "Visually inspect a screenshot produced by the CUA-SWE adapter. "
            "Pass the exact screenshot path returned by observe or act."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "finish",
        "description": "Finish after implementing and validating the task.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
]

STRUCTURED_SUBMISSION_ERROR = (
    "Protocol submission rejected. Continue inspecting with shell or call "
    "submit_design exactly once with a schema-valid object."
)
_SUPPORTED_SCHEMA_KEYS = {
    "$schema",
    "$id",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "const",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "items",
}
_READ_ONLY_COMMANDS = {
    "cat",
    "echo",
    "find",
    "grep",
    "head",
    "ls",
    "pwd",
    "sed",
    "tail",
}
_SHELL_SEPARATORS = {"|", ";", "&&", "||"}

TYPED_PROTOCOL_PROPOSAL_SHA256 = {
    "03": "7125de5f04295b2e6e31ebf1c3159fa482e7b2d082e5e0768e08f0a55420d5b6",
    "04": "7d18c94758150af07ddc97d4f9415e006fa6819724b6c2d4b620cb1b8d757f48",
    "05": "ec41c930f50420406cc4aa4e3f37c5f13ddd30cf67c5c63d075ec6817001028c",
}
TYPED_PROTOCOL_MAX_TURNS = 40
TYPED_PROTOCOL_MAX_RESULT_BYTES = 65_536
TYPED_PROTOCOL_MAX_SUBMISSION_BYTES = 24_576
TYPED_PROTOCOL_RESULT_BUDGET = 2_424_832
TYPED_MAX_MANIFEST_FILES = 50_000
TYPED_MAX_LIVE_ENTRIES = 100_000
TYPED_RAW_DIRENT_SENTINEL = 100_001
TYPED_TRANSPORT_STAGES = frozenset(
    {
        "credential_resolution",
        "request_headers",
        "dispatch",
        "response_status",
        "response_decode",
    }
)
TYPED_TRANSPORT_FAILURE_KINDS = frozenset(
    {
        "no_credentials",
        "credential_resolution_error",
        "header_error",
        "connect_timeout",
        "read_timeout",
        "proxy_error",
        "tls_error",
        "connection_error",
        "http_status",
        "response_decode_error",
        "unknown_transport",
    }
)
TYPED_MAX_LIVE_FILE_BYTES = 67_108_864
TYPED_MAX_LIVE_HASH_BYTES = 1_073_741_824
TYPED_PROTOCOL_REMINDERS = {
    33: "8 turns remain; submit_design becomes the only available tool for the final 3 turns.",
    36: "5 turns remain; complete inspection and prepare the full schema-valid submission.",
    38: "3 reserved submission turns remain; source inspection is now unavailable.",
}
TYPED_TRUNCATION_REASON_ORDER = (
    "field_utf8_limit",
    "operation_record_limit",
    "per_file_size_limit",
    "per_call_entries_limit",
    "per_call_files_limit",
    "per_call_bytes_limit",
    "trajectory_entries_limit",
    "trajectory_files_limit",
    "trajectory_bytes_limit",
    "binary_or_non_utf8_skipped",
    "result_bytes_limit",
)
TYPED_INSPECTION_ERROR_CONTENT = {
    category: f"source_inspect_error:{category}"
    for category in (
        "schema_or_type_error",
        "scalar_range_error",
        "canonical_in_root_path_not_found",
        "target_kind_mismatch",
        "content_unsupported",
        "content_too_large",
        "glob_syntax_unsupported",
        "inspection_budget_exhausted",
    )
}
TYPED_PROTOCOL_ERROR_CONTENT = {
    "protocol_shape_error": "protocol_error:protocol_shape_error",
    "wrong_tool": "protocol_error:wrong_tool",
    "multiple_tool_calls_rejected": "protocol_error:multiple_tool_calls_rejected",
    "provider_truncated_submission": "protocol_error:provider_truncated_submission",
    "submission_schema_invalid": "submission_error:submission_schema_invalid",
    "submission_constant_or_local_bound_invalid": (
        "submission_error:submission_constant_or_local_bound_invalid"
    ),
    "submission_too_large": "submission_error:submission_too_large",
    "submission_semantic_invalid": "submission_error:submission_semantic_invalid",
}
TYPED_SUBMISSION_VALIDATION_ERROR_CODES = frozenset(
    {
        "additional_property",
        "const_mismatch",
        "local_identifier_bound",
        "local_max_items",
        "local_string_bound",
        "max_items",
        "max_length",
        "min_items",
        "min_length",
        "missing_required",
        "type_mismatch",
    }
)
TYPED_SUBMISSION_VALIDATION_FEEDBACK_MAX_BYTES = 512
TYPED_SUBMISSION_VALIDATION_PATH_MAX_BYTES = 384
TYPED_SEMANTIC_VALIDATION_TIMEOUT_SECONDS = 2
TYPED_SEMANTIC_VALIDATION_MAX_OUTPUT_BYTES = 512
TYPED_SEMANTIC_VALIDATOR_MAX_BYTES = 262_144
TYPED_SEMANTIC_VALIDATOR_ALLOWED_IMPORTS = frozenset({"hashlib", "json", "re", "sys"})
TYPED_SEMANTIC_VALIDATOR_FORBIDDEN_NAMES = frozenset(
    {
        "breakpoint",
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "globals",
        "help",
        "locals",
        "open",
        "setattr",
        "vars",
        "__import__",
    }
)
TYPED_SEMANTIC_VALIDATOR_ALLOWED_ATTRIBUTES = frozenset(
    {
        "add",
        "buffer",
        "dumps",
        "encode",
        "flush",
        "fullmatch",
        "hexdigest",
        "index",
        "loads",
        "read",
        "result",
        "sha256",
        "stdin",
        "stdout",
        "update",
        "values",
        "write",
    }
)
TYPED_SEMANTIC_VALIDATION_REFERENCE_KEYS = frozenset(
    {"case_id", "fact_id", "family_id", "state_id"}
)
TYPED_SEMANTIC_VALIDATION_ERROR_CODES = frozenset(
    {
        "adversary_fact_set_mismatch",
        "adversary_post_live_mismatch",
        "adversary_pre_live_mismatch",
        "adversary_selection_unchanged",
        "adversary_wrong_family_mismatch",
        "affected_state_set_invalid",
        "declared_transition_mismatch",
        "design_self_assessment_false",
        "diagnostic_fact_instruction_leak",
        "difference_before_earliest",
        "duplicate_affected_state",
        "duplicate_fact_id",
        "duplicate_family_fact_prediction",
        "duplicate_family_id",
        "duplicate_family_symptom_ref",
        "duplicate_independent_fact_ref",
        "duplicate_negative_case_id",
        "duplicate_negative_state_prediction",
        "duplicate_rank_after",
        "duplicate_rank_before",
        "duplicate_state_id",
        "duplicate_state_negative_ref",
        "duplicate_state_symptom_ref",
        "duplicate_symptom_id",
        "duplicate_withheld_fact_id",
        "earliest_stage_not_different",
        "earliest_stage_unknown",
        "end_to_end_proof_empty",
        "fact_independence_set_mismatch",
        "fact_partition_invalid",
        "fact_transition_unsupported",
        "family_fact_cardinality",
        "family_prediction_fact_set_mismatch",
        "family_prediction_vector_collision",
        "family_symptom_coverage_mismatch",
        "fallback_bypass_empty",
        "final_stage_not_different",
        "final_stage_not_unique_exact",
        "instruction_separation_false",
        "negative_bounds_flag_false",
        "negative_case_cardinality",
        "negative_state_set_mismatch",
        "non_noop_flags_false",
        "rank_chain_mismatch",
        "ranked_family_cardinality",
        "ranked_family_coverage",
        "ruled_out_prediction_match",
        "semantic_input_shape_invalid",
        "stage_ordinal_sequence",
        "stage_witness_cardinality",
        "state_bounds_empty",
        "state_consistency_false",
        "state_negative_set_mismatch",
        "supported_prediction_mismatch",
        "ui_state_cardinality",
        "uncovered_symptom",
        "unknown_state_symptom",
        "withheld_fact_set_mismatch",
        "witness_ordinal_sequence",
    }
)
TYPED_IDENTIFIER_PATH_SCHEMA_PATHS = frozenset(
    {
        ("candidate_id",),
        ("template_revision",),
        ("mutation_seed",),
        ("selected_family",),
        ("coherent_fault_model", "mutation_operations", "*", "path"),
        ("coherent_fault_model", "mutation_operations", "*", "symbol_or_region"),
        ("plausible_repair_families_before_reproduction", "*", "family"),
        (
            "plausible_repair_families_before_reproduction",
            "*",
            "source_areas",
            "*",
        ),
        ("discriminating_runtime_observations", "*", "supports", "*"),
        ("discriminating_runtime_observations", "*", "rules_out", "*"),
        ("ui_state_matrix", "*", "state_id"),
        ("source_only_shortcut_audit", "answer_bearing_locations", "*"),
        ("source_only_shortcut_audit", "shortcuts_to_remove_during_packaging", "*"),
        ("packaging_scope", "retain_paths", "*"),
        ("packaging_scope", "omit_paths", "*"),
        ("packaging_scope", "required_license_files", "*"),
        ("packaging_scope", "diagnostic_indirection_to_preserve", "*"),
    }
)

SOURCE_INSPECT_TOOL = {
    "name": "source_inspect",
    "description": (
        "Inspect the bound read-only source index. Choose exactly one typed operation; "
        "read_file requires start_line and end_line, search_text requires query and may "
        "include file_glob, and find_files requires name_glob. No shell, network, write, "
        "build, test, or browser capability is available."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list_dir", "read_file", "search_text", "find_files"],
            },
            "path": {"type": "string", "minLength": 1, "maxLength": 512},
            "start_line": {"type": "integer", "minimum": 1, "maximum": 1_000_000},
            "end_line": {"type": "integer", "minimum": 1, "maximum": 1_000_000},
            "query": {"type": "string", "minLength": 1, "maxLength": 256},
            "file_glob": {"type": "string", "minLength": 1, "maxLength": 128},
            "name_glob": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        "required": ["operation", "path"],
        "additionalProperties": False,
    },
}


class TypedCustodyFailure(RuntimeError):
    """A fail-closed source, protocol, or publication custody failure."""


class TypedRecoverableInspection(ValueError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


class TypedSubmissionValidationError(ValueError):
    def __init__(
        self,
        code: str,
        schema_path: tuple[str, ...],
        *,
        category: str = "submission_schema_invalid",
        message: str | None = None,
    ) -> None:
        if code not in TYPED_SUBMISSION_VALIDATION_ERROR_CODES:
            raise ValueError("unsupported typed submission validation error code")
        super().__init__(message or code)
        self.code = code
        self.schema_path = schema_path
        self.category = category


class TypedTerminalProvider(RuntimeError):
    def __init__(
        self,
        category: str,
        *,
        transport_stage: str | None = None,
        dispatch_attempted: bool = False,
        failure_kind: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(category)
        self.category = category
        if transport_stage is None:
            if dispatch_attempted or failure_kind is not None or http_status is not None:
                raise ValueError("transport telemetry requires a stage")
            self.transport_telemetry: dict[str, object] | None = None
            return
        if transport_stage not in TYPED_TRANSPORT_STAGES:
            raise ValueError("invalid transport stage")
        if type(dispatch_attempted) is not bool:
            raise ValueError("dispatch_attempted must be a boolean")
        if failure_kind not in TYPED_TRANSPORT_FAILURE_KINDS:
            raise ValueError("invalid transport failure kind")
        if http_status is not None and (
            type(http_status) is not int or not 100 <= http_status <= 599
        ):
            raise ValueError("invalid HTTP status")
        if failure_kind != "http_status" and http_status is not None:
            raise ValueError("HTTP status is only valid for http_status failures")
        self.transport_telemetry = {
            "dispatch_attempted": dispatch_attempted,
            "failure_kind": failure_kind,
            "http_status": http_status,
            "transport_stage": transport_stage,
        }


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    sha256: str


@dataclass
class InspectionCounters:
    calls: int = 0
    entries_visited: int = 0
    files_opened: int = 0
    file_bytes_read: int = 0
    serialized_result_bytes: int = 0


@dataclass(frozen=True)
class TypedSourceIndex:
    files: tuple[ManifestEntry, ...]
    file_digests: dict[str, str]
    directories: tuple[str, ...]
    directory_set: frozenset[str]


@dataclass
class TypedSourceProtocolConfig:
    schema: dict[str, Any]
    schema_sha256: str
    candidate_output: Path
    source_manifest: bytes
    source_manifest_sha256: str
    source_index: TypedSourceIndex
    run_id: str
    workspace: Path
    semantic_validator_bytes: bytes | None = None
    semantic_validator_sha256: str | None = None
    startup_outcome: str | None = None
    startup_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuredSubmissionConfig:
    schema: dict[str, Any]
    schema_sha256: str
    candidate_output: Path
    source_manifest: bytes
    source_manifest_sha256: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _expected_digest(value: str, label: str) -> str:
    digest = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _validate_supported_schema(schema: Any, path: str = "$") -> None:
    if not isinstance(schema, dict):
        raise ValueError(f"schema at {path} must be an object")
    unsupported = set(schema) - _SUPPORTED_SCHEMA_KEYS
    if unsupported:
        raise ValueError(f"unsupported schema keywords at {path}: {sorted(unsupported)}")
    schema_type = schema.get("type")
    if schema_type is not None and schema_type not in {
        "object",
        "array",
        "string",
        "integer",
        "boolean",
    }:
        raise ValueError(f"unsupported schema type at {path}: {schema_type}")
    if schema_type == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ValueError(f"object schema at {path} requires properties and required")
        if schema.get("additionalProperties") is not False:
            raise ValueError(f"object schema at {path} must reject additional properties")
        if not all(isinstance(name, str) for name in required) or len(set(required)) != len(required):
            raise ValueError(f"object schema at {path} has invalid required keys")
        if not set(required).issubset(properties):
            raise ValueError(f"object schema at {path} requires undeclared properties")
        for name, child in properties.items():
            if not isinstance(name, str):
                raise ValueError(f"object schema at {path} has a non-string property")
            _validate_supported_schema(child, f"{path}.{name}")
    if schema_type == "array":
        if not isinstance(schema.get("items"), dict):
            raise ValueError(f"array schema at {path} requires one item schema")
        for key in ("minItems", "maxItems"):
            if key in schema and (not isinstance(schema[key], int) or schema[key] < 0):
                raise ValueError(f"{key} at {path} must be a nonnegative integer")
        if schema.get("maxItems", float("inf")) < schema.get("minItems", 0):
            raise ValueError(f"array bounds at {path} are inconsistent")
        _validate_supported_schema(schema["items"], f"{path}[]")
    if schema_type == "string":
        for key in ("minLength", "maxLength"):
            if key in schema and (not isinstance(schema[key], int) or schema[key] < 0):
                raise ValueError(f"{key} at {path} must be a nonnegative integer")
        if schema.get("maxLength", float("inf")) < schema.get("minLength", 0):
            raise ValueError(f"string bounds at {path} are inconsistent")


def _validate_instance(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"value at {path} does not match its constant")
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            raise ValueError(f"value at {path} must be an object")
        properties = schema["properties"]
        missing = set(schema["required"]) - set(value)
        if missing:
            raise ValueError(f"value at {path} is missing required properties")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"value at {path} contains additional properties")
        for name, child in properties.items():
            if name in value:
                _validate_instance(value[name], child, f"{path}.{name}")
        return
    if schema_type == "array":
        if not isinstance(value, list):
            raise ValueError(f"value at {path} must be an array")
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"array at {path} is too short")
        if len(value) > schema.get("maxItems", float("inf")):
            raise ValueError(f"array at {path} is too long")
        for index, item in enumerate(value):
            _validate_instance(item, schema["items"], f"{path}[{index}]")
        return
    if schema_type == "string":
        if not isinstance(value, str):
            raise ValueError(f"value at {path} must be a string")
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"string at {path} is too short")
        if len(value) > schema.get("maxLength", float("inf")):
            raise ValueError(f"string at {path} is too long")
        return
    if schema_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError(f"value at {path} must be an integer")
    if schema_type == "boolean" and not isinstance(value, bool):
        raise ValueError(f"value at {path} must be a boolean")


def _schema_name_sort_key(name: str) -> bytes:
    return name.encode("utf-8", errors="surrogatepass")


def _typed_schema_path_segment(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", name):
        return f".{name}"
    encoded = name.encode("utf-8", errors="surrogatepass")
    digest = hashlib.sha256(encoded).hexdigest()
    if len(encoded) <= 32:
        representation = encoded.hex()
    else:
        representation = f"{encoded[:32].hex()}~sha256:{digest}"
    return f'["hex:{representation}"]'


def _format_typed_schema_path(schema_path: tuple[str, ...]) -> str:
    pieces = ["$"]
    for name in schema_path:
        pieces.append("[*]" if name == "*" else _typed_schema_path_segment(name))
    path = "".join(pieces)
    encoded = path.encode("ascii")
    if len(encoded) <= TYPED_SUBMISSION_VALIDATION_PATH_MAX_BYTES:
        return path
    suffix = f"~sha256:{hashlib.sha256(encoded).hexdigest()}"
    prefix_bytes = TYPED_SUBMISSION_VALIDATION_PATH_MAX_BYTES - len(suffix)
    return encoded[:prefix_bytes].decode("ascii") + suffix


def _format_typed_submission_validation_error(
    error: TypedSubmissionValidationError,
) -> str:
    if error.code not in TYPED_SUBMISSION_VALIDATION_ERROR_CODES:
        raise ValueError("unsupported typed submission validation error code")
    content = "submission_error:" + json.dumps(
        {
            "code": error.code,
            "path": _format_typed_schema_path(error.schema_path),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    if len(content.encode("utf-8")) > TYPED_SUBMISSION_VALIDATION_FEEDBACK_MAX_BYTES:
        raise ValueError("typed submission validation feedback exceeds bound")
    return content


def _validate_typed_semantic_validator_source(payload: bytes) -> None:
    try:
        source = payload.decode("utf-8", errors="strict")
        tree = ast.parse(source, filename="typed-semantic-validator.py", mode="exec")
    except (UnicodeError, SyntaxError) as exc:
        raise TypedCustodyFailure("semantic_validator_source_invalid") from exc
    protocol_marker = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.asname is not None
                or alias.name not in TYPED_SEMANTIC_VALIDATOR_ALLOWED_IMPORTS
                for alias in node.names
            ):
                raise TypedCustodyFailure("semantic_validator_source_unsafe")
        elif isinstance(node, ast.ImportFrom):
            raise TypedCustodyFailure("semantic_validator_source_unsafe")
        elif isinstance(node, ast.Name):
            if (
                node.id in TYPED_SEMANTIC_VALIDATOR_FORBIDDEN_NAMES
                or node.id.startswith("__")
            ):
                raise TypedCustodyFailure("semantic_validator_source_unsafe")
        elif isinstance(node, ast.Attribute) and (
            node.attr.startswith("__")
            or node.attr not in TYPED_SEMANTIC_VALIDATOR_ALLOWED_ATTRIBUTES
        ):
            raise TypedCustodyFailure("semantic_validator_source_unsafe")
        elif isinstance(node, ast.Assign):
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "TYPED_SEMANTIC_VALIDATOR_PROTOCOL"
                and isinstance(node.value, ast.Constant)
                and node.value.value == 1
            ):
                protocol_marker = True
    if not protocol_marker:
        raise TypedCustodyFailure("semantic_validator_protocol_mismatch")


def _typed_semantic_resource_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024, 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_AS, (268_435_456, 268_435_456))


def _parse_typed_semantic_validation_result(payload: bytes) -> dict[str, str] | None:
    if not payload or len(payload) > TYPED_SEMANTIC_VALIDATION_MAX_OUTPUT_BYTES:
        raise TypedCustodyFailure("semantic_validator_output_invalid")
    try:
        value = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TypedCustodyFailure("semantic_validator_output_invalid") from exc
    if value == {"status": "pass"}:
        expected = b'{"status":"pass"}\n'
        if payload != expected:
            raise TypedCustodyFailure("semantic_validator_output_noncanonical")
        return None
    if not isinstance(value, dict) or value.get("status") != "reject":
        raise TypedCustodyFailure("semantic_validator_output_invalid")
    required = {"status", "code", "path"}
    if not required.issubset(value) or set(value) - required - set(
        TYPED_SEMANTIC_VALIDATION_REFERENCE_KEYS
    ):
        raise TypedCustodyFailure("semantic_validator_output_invalid")
    if value["code"] not in TYPED_SEMANTIC_VALIDATION_ERROR_CODES:
        raise TypedCustodyFailure("semantic_validator_output_invalid")
    path = value["path"]
    if (
        not isinstance(path, str)
        or len(path.encode("ascii", errors="ignore")) != len(path)
        or len(path) > 384
        or re.fullmatch(
            r"\$(?:\.[A-Za-z_][A-Za-z0-9_-]{0,63}|\[\*\]){1,8}", path
        )
        is None
    ):
        raise TypedCustodyFailure("semantic_validator_output_invalid")
    for key in TYPED_SEMANTIC_VALIDATION_REFERENCE_KEYS:
        if key not in value:
            continue
        reference = value[key]
        if not isinstance(reference, str) or re.fullmatch(
            r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,63}|sha256:[0-9a-f]{64})",
            reference,
        ) is None:
            raise TypedCustodyFailure("semantic_validator_output_invalid")
    canonical = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    if payload != canonical:
        raise TypedCustodyFailure("semantic_validator_output_noncanonical")
    return {str(key): str(item) for key, item in value.items()}


def _run_typed_semantic_validator(
    validator_bytes: bytes,
    canonical_candidate: bytes,
) -> dict[str, str] | None:
    _validate_typed_semantic_validator_source(validator_bytes)
    try:
        with tempfile.TemporaryDirectory(prefix="cua-swe-semantic-validator-") as raw:
            directory = Path(raw)
            directory.chmod(0o700)
            validator = directory / "typed-semantic-validator.py"
            descriptor = os.open(
                validator,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o400,
            )
            try:
                offset = 0
                while offset < len(validator_bytes):
                    count = os.write(descriptor, validator_bytes[offset:])
                    if count <= 0:
                        raise OSError("semantic validator short write")
                    offset += count
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            with tempfile.TemporaryFile(dir=directory) as output:
                process = subprocess.Popen(
                    [sys.executable, "-I", "-S", str(validator)],
                    cwd=directory,
                    env={
                        "LANG": "C",
                        "LC_ALL": "C",
                        "PYTHONHASHSEED": "0",
                        "PYTHONIOENCODING": "utf-8",
                    },
                    stdin=subprocess.PIPE,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    preexec_fn=_typed_semantic_resource_limits,
                )
                try:
                    process.communicate(
                        input=canonical_candidate,
                        timeout=TYPED_SEMANTIC_VALIDATION_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise TypedCustodyFailure("semantic_validator_timeout") from None
                if process.returncode != 0:
                    raise TypedCustodyFailure("semantic_validator_failure")
                size = os.fstat(output.fileno()).st_size
                if size > TYPED_SEMANTIC_VALIDATION_MAX_OUTPUT_BYTES:
                    raise TypedCustodyFailure("semantic_validator_output_invalid")
                output.seek(0)
                result = _parse_typed_semantic_validation_result(output.read())
                if result is not None:
                    _format_typed_semantic_validation_error(result)
                return result
    except TypedCustodyFailure:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise TypedCustodyFailure("semantic_validator_failure") from exc


def _format_typed_semantic_validation_error(error: dict[str, str]) -> str:
    payload = {key: value for key, value in error.items() if key != "status"}
    content = "submission_error:" + json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    if len(content.encode("ascii")) > TYPED_SUBMISSION_VALIDATION_FEEDBACK_MAX_BYTES:
        raise TypedCustodyFailure("semantic_validator_feedback_too_large")
    return content


def _validate_typed_submission_instance(
    value: Any,
    schema: dict[str, Any],
    schema_path: tuple[str, ...] = (),
) -> None:
    if "const" in schema and value != schema["const"]:
        raise TypedSubmissionValidationError(
            "const_mismatch",
            schema_path,
            category="submission_constant_or_local_bound_invalid",
        )
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            raise TypedSubmissionValidationError("type_mismatch", schema_path)
        properties = schema["properties"]
        missing = sorted(
            (name for name in schema["required"] if name not in value),
            key=_schema_name_sort_key,
        )
        if missing:
            raise TypedSubmissionValidationError(
                "missing_required", schema_path + (missing[0],)
            )
        if schema.get("additionalProperties") is False and any(
            name not in properties for name in value
        ):
            raise TypedSubmissionValidationError("additional_property", schema_path)
        for name in sorted(properties, key=_schema_name_sort_key):
            if name in value:
                _validate_typed_submission_instance(
                    value[name], properties[name], schema_path + (name,)
                )
        return
    if schema_type == "array":
        if not isinstance(value, list):
            raise TypedSubmissionValidationError("type_mismatch", schema_path)
        if len(value) < schema.get("minItems", 0):
            raise TypedSubmissionValidationError("min_items", schema_path)
        if len(value) > schema.get("maxItems", float("inf")):
            raise TypedSubmissionValidationError("max_items", schema_path)
        for item in value:
            _validate_typed_submission_instance(
                item, schema["items"], schema_path + ("*",)
            )
        return
    if schema_type == "string":
        if not isinstance(value, str):
            raise TypedSubmissionValidationError("type_mismatch", schema_path)
        if len(value) < schema.get("minLength", 0):
            raise TypedSubmissionValidationError("min_length", schema_path)
        if len(value) > schema.get("maxLength", float("inf")):
            raise TypedSubmissionValidationError("max_length", schema_path)
        return
    if schema_type == "integer" and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        raise TypedSubmissionValidationError("type_mismatch", schema_path)
    if schema_type == "boolean" and not isinstance(value, bool):
        raise TypedSubmissionValidationError("type_mismatch", schema_path)


def _source_manifest(workspace: Path) -> bytes:
    records: list[str] = []
    for path in sorted(workspace.rglob("*"), key=lambda candidate: candidate.as_posix()):
        if path.is_symlink():
            raise ValueError(f"source workspace contains a symbolic link: {path}")
        if not path.is_file():
            continue
        relative = "./" + path.relative_to(workspace).as_posix()
        records.append(f"{_sha256_bytes(path.read_bytes())}  {relative}\n")
    return "".join(records).encode("utf-8")


def _audit_read_only_command(command: str) -> None:
    if not command or "\n" in command or "\r" in command:
        raise ValueError("structured design shell commands must be nonempty and single-line")
    if any(marker in command for marker in ("$", "`", "~", "<(", ">(")):
        raise ValueError("structured design shell command contains expansion or substitution")
    if any(marker in command for marker in ("(", ")", "{", "}")):
        raise ValueError("structured design shell command contains a disallowed operator")
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&<>")
    lexer.whitespace_split = True
    raw_tokens = list(lexer)
    tokens: list[str] = []
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        if token in {">", "&>"} and index + 1 < len(raw_tokens):
            if raw_tokens[index + 1] == "/dev/null":
                if token == ">" and tokens and tokens[-1] in {"1", "2"}:
                    tokens.pop()
                index += 2
                continue
        tokens.append(token)
        index += 1
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SHELL_SEPARATORS:
            if not segments[-1]:
                raise ValueError("structured design shell command has an empty segment")
            segments.append([])
        elif token == "&":
            raise ValueError("structured design shell command cannot run in the background")
        elif ">" in token or "<" in token:
            raise ValueError("structured design shell command contains a disallowed redirection")
        else:
            segments[-1].append(token)
    if not segments[-1]:
        raise ValueError("structured design shell command has an empty final segment")
    for segment in segments:
        executable = segment[0]
        if executable not in _READ_ONLY_COMMANDS:
            raise ValueError("structured design shell command is not in the read-only allowlist")
        for argument in segment[1:]:
            path_candidates = [argument]
            if "=" in argument:
                path_candidates.append(argument.split("=", 1)[1])
            for candidate in path_candidates:
                if candidate.startswith("/") or candidate == ".." or candidate.startswith("../"):
                    raise ValueError("structured design shell command addresses outside the workspace")
                if "/../" in candidate or candidate.endswith("/.."):
                    raise ValueError("structured design shell command contains parent traversal")
        if executable == "sed":
            if (
                len(segment) < 4
                or segment[1] != "-n"
                or not re.fullmatch(r"[0-9]+(?:,[0-9]+)?p", segment[2])
                or any(argument.startswith("-") for argument in segment[3:])
            ):
                raise ValueError("structured design sed command is not a read-only print range")
        elif executable == "find":
            _audit_find_arguments(segment[1:])
        elif executable == "grep":
            _audit_grep_arguments(segment[1:])
        elif executable in {"head", "tail"}:
            _audit_head_tail_arguments(segment[1:])
        elif executable == "cat" and any(
            argument.startswith("-") and argument != "--" for argument in segment[1:]
        ):
            raise ValueError("structured design cat command has unsupported options")
        elif executable == "ls":
            _audit_ls_arguments(segment[1:])
        elif executable == "pwd" and any(argument not in {"-L", "-P"} for argument in segment[1:]):
            raise ValueError("structured design pwd command has unsupported arguments")


def _audit_find_arguments(arguments: list[str]) -> None:
    index = 0
    while index < len(arguments) and not arguments[index].startswith("-") and arguments[index] != "!":
        if any(marker in arguments[index] for marker in ("*", "?", "[")):
            raise ValueError("structured design find paths cannot use shell globs")
        index += 1
    if index == 0:
        raise ValueError("structured design find command requires an explicit workspace path")
    value_actions = {
        "-maxdepth": r"[0-9]+",
        "-mindepth": r"[0-9]+",
        "-type": r"[fd]",
        "-name": r".+",
        "-iname": r".+",
        "-path": r".+",
        "-ipath": r".+",
        "-size": r"[+-]?[0-9]+[bcwkMG]?",
        "-mtime": r"[+-]?[0-9]+",
        "-mmin": r"[+-]?[0-9]+",
        "-newer": r".+",
    }
    no_value_actions = {
        "!",
        "-not",
        "-a",
        "-and",
        "-o",
        "-or",
        "-print",
        "-print0",
        "-empty",
        "-readable",
        "-true",
        "-false",
    }
    while index < len(arguments):
        action = arguments[index]
        if action in no_value_actions:
            index += 1
            continue
        pattern = value_actions.get(action)
        if pattern is None or index + 1 >= len(arguments):
            raise ValueError("structured design find command contains an unsupported action")
        value = arguments[index + 1]
        if not re.fullmatch(pattern, value):
            raise ValueError("structured design find command has an invalid action value")
        index += 2


def _audit_grep_arguments(arguments: list[str]) -> None:
    index = 0
    short_flags = set("EFGPHhIabnorsRsvwxlLcZzqi")
    long_flags = {
        "--extended-regexp",
        "--fixed-strings",
        "--basic-regexp",
        "--perl-regexp",
        "--ignore-case",
        "--word-regexp",
        "--line-regexp",
        "--null-data",
        "--no-messages",
        "--invert-match",
        "--byte-offset",
        "--line-number",
        "--with-filename",
        "--no-filename",
        "--only-matching",
        "--quiet",
        "--silent",
        "--text",
        "--recursive",
        "--dereference-recursive",
    }
    long_value_patterns = {
        "--regexp": r".+",
        "--max-count": r"[0-9]+",
        "--after-context": r"[0-9]+",
        "--before-context": r"[0-9]+",
        "--context": r"[0-9]+",
    }
    safe_long_assignments = {
        "--include": r".+",
        "--exclude": r".+",
        "--exclude-dir": r".+",
        "--binary-files": r"(?:binary|text|without-match)",
        "--color": r"(?:never|always|auto)",
    }
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            index += 1
            continue
        if not argument.startswith("-") or argument == "-":
            index += 1
            continue
        if argument.startswith("--"):
            if argument in long_flags:
                index += 1
                continue
            if argument in long_value_patterns:
                if index + 1 >= len(arguments) or not re.fullmatch(
                    long_value_patterns[argument], arguments[index + 1]
                ):
                    raise ValueError("structured design grep option has an invalid value")
                index += 2
                continue
            name, separator, value = argument.partition("=")
            if separator and name in {**long_value_patterns, **safe_long_assignments}:
                pattern = {**long_value_patterns, **safe_long_assignments}[name]
                if not re.fullmatch(pattern, value):
                    raise ValueError("structured design grep option has an invalid value")
                index += 1
                continue
            raise ValueError("structured design grep command has an unsupported option")
        if len(argument) > 1 and set(argument[1:]).issubset(short_flags):
            index += 1
            continue
        if re.fullmatch(r"-[ABCm][0-9]+", argument):
            index += 1
            continue
        if argument in {"-A", "-B", "-C", "-m"}:
            if index + 1 >= len(arguments) or not re.fullmatch(r"[0-9]+", arguments[index + 1]):
                raise ValueError("structured design grep option has an invalid numeric value")
            index += 2
            continue
        if argument == "-e":
            if index + 1 >= len(arguments) or not arguments[index + 1]:
                raise ValueError("structured design grep -e requires a pattern")
            index += 2
            continue
        if argument.startswith("-e") and len(argument) > 2:
            index += 1
            continue
        raise ValueError("structured design grep command has an unsupported option")


def _audit_head_tail_arguments(arguments: list[str]) -> None:
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--" or not argument.startswith("-") or argument == "-":
            index += 1
            continue
        if re.fullmatch(r"-[0-9]+", argument) or re.fullmatch(r"-[qvz]+", argument):
            index += 1
            continue
        if argument in {"-n", "-c"}:
            if index + 1 >= len(arguments) or not re.fullmatch(
                r"[+-]?[0-9]+[bBkKmM]?", arguments[index + 1]
            ):
                raise ValueError("structured design head/tail option has an invalid value")
            index += 2
            continue
        if re.fullmatch(r"--(?:lines|bytes)=[+-]?[0-9]+[bBkKmM]?", argument):
            index += 1
            continue
        if argument in {"--quiet", "--silent", "--verbose", "--zero-terminated"}:
            index += 1
            continue
        raise ValueError("structured design head/tail command has an unsupported option")


def _audit_ls_arguments(arguments: list[str]) -> None:
    safe_short_flags = set("1aAbBcCdDfFgGhHiIklLmNnOoPqQrRsStTuvwxXZ")
    for argument in arguments:
        if argument == "--" or not argument.startswith("-") or argument == "-":
            continue
        if len(argument) > 1 and set(argument[1:]).issubset(safe_short_flags):
            continue
        raise ValueError("structured design ls command has an unsupported option")


def _publish_no_replace(output: Path, payload: bytes) -> None:
    temp_path: Path | None = None
    published = False
    try:
        descriptor, raw_temp_path = tempfile.mkstemp(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
        )
        temp_path = Path(raw_temp_path)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp_path, output)
        published = True
        temp_path.unlink()
        temp_path = None
        directory = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        if published:
            output.unlink(missing_ok=True)
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _prepare_structured_submission(args: argparse.Namespace) -> StructuredSubmissionConfig | None:
    option_names = (
        "submission_schema",
        "expected_submission_schema_sha256",
        "candidate_output",
        "source_manifest_before",
        "expected_source_manifest_sha256",
    )
    supplied = [getattr(args, name) is not None for name in option_names]
    if not any(supplied):
        return None
    if not all(supplied):
        raise ValueError("all structured-submission options must be supplied together")
    if not args.code_only:
        raise ValueError("structured submission requires --code-only")

    workspace = args.workspace.resolve()
    schema_path = args.submission_schema.resolve()
    manifest_path = args.source_manifest_before.resolve()
    candidate_output = args.candidate_output.resolve()
    for label, path in (("submission schema", schema_path), ("source manifest", manifest_path)):
        if path.is_relative_to(workspace):
            raise ValueError(f"{label} must be outside the source workspace")
        if not path.is_file():
            raise ValueError(f"{label} does not exist: {path}")
    if candidate_output.is_relative_to(workspace):
        raise ValueError("candidate output must be outside the source workspace")
    if not candidate_output.parent.is_dir():
        raise ValueError("candidate output parent must already exist")
    if candidate_output.exists() or candidate_output.is_symlink():
        raise FileExistsError(f"candidate output already exists: {candidate_output}")

    schema_bytes = schema_path.read_bytes()
    schema_digest = _sha256_bytes(schema_bytes)
    if schema_digest != _expected_digest(
        args.expected_submission_schema_sha256,
        "expected submission schema digest",
    ):
        raise ValueError("submission schema digest mismatch")
    try:
        schema = json.loads(schema_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("submission schema is not valid JSON") from exc
    _validate_supported_schema(schema)

    manifest_bytes = manifest_path.read_bytes()
    manifest_digest = _sha256_bytes(manifest_bytes)
    if manifest_digest != _expected_digest(
        args.expected_source_manifest_sha256,
        "expected source manifest digest",
    ):
        raise ValueError("source manifest digest mismatch")
    if _source_manifest(workspace) != manifest_bytes:
        raise ValueError("source workspace does not match the bound manifest")

    return StructuredSubmissionConfig(
        schema=schema,
        schema_sha256=schema_digest,
        candidate_output=candidate_output,
        source_manifest=manifest_bytes,
        source_manifest_sha256=manifest_digest,
    )


def _identity_tuple(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _open_flags(*, directory: bool) -> int:
    required = ("O_CLOEXEC", "O_NOFOLLOW")
    if directory:
        required += ("O_DIRECTORY",)
    if any(not hasattr(os, name) for name in required):
        raise TypedCustodyFailure("unsupported_no_follow_primitive")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    if directory:
        flags |= os.O_DIRECTORY
    return flags


def _open_external_regular(path: Path) -> int:
    try:
        descriptor = os.open(path, _open_flags(directory=False))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise TypedCustodyFailure("external_artifact_not_regular")
        return descriptor
    except TypedCustodyFailure:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as exc:
        raise TypedCustodyFailure("external_artifact_access_ambiguous") from exc


def _exact_read_descriptor(
    descriptor: int,
    *,
    expected_size: int,
    expected_sha256: str,
    maximum_size: int,
    over_limit_category: str,
) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size < 0:
        raise TypedCustodyFailure("source_identity_ambiguous")
    if before.st_size != expected_size:
        raise TypedCustodyFailure("source_size_precheck_mismatch")
    if expected_size > maximum_size:
        raise TypedRecoverableInspection(over_limit_category)
    remaining = expected_size
    chunks: list[bytes] = []
    digest = hashlib.sha256()
    bytes_read = 0
    while remaining:
        requested = min(1_048_576, remaining)
        try:
            chunk = os.read(descriptor, requested)
        except OSError as exc:
            raise TypedCustodyFailure("source_read_ambiguous") from exc
        if not chunk:
            raise TypedCustodyFailure("short_read")
        if len(chunk) > requested:
            raise TypedCustodyFailure("read_overshoot")
        chunks.append(chunk)
        digest.update(chunk)
        bytes_read += len(chunk)
        remaining -= len(chunk)
    after = os.fstat(descriptor)
    if _identity_tuple(before) != _identity_tuple(after):
        raise TypedCustodyFailure("source_changed_during_read")
    if bytes_read != expected_size or digest.hexdigest() != expected_sha256:
        raise TypedCustodyFailure("source_changed_during_read")
    return b"".join(chunks)


def _canonical_path(value: Any, *, allow_root: bool = True) -> str:
    if not isinstance(value, str):
        raise TypedRecoverableInspection("schema_or_type_error")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise TypedCustodyFailure("lexical_path_escape_or_ambiguity") from exc
    if not encoded or len(encoded) > 512:
        raise TypedRecoverableInspection("scalar_range_error")
    if value == ".":
        if allow_root:
            return value
        raise TypedCustodyFailure("lexical_path_escape_or_ambiguity")
    if (
        value.startswith("/")
        or value.endswith("/")
        or "//" in value
        or "\\" in value
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise TypedCustodyFailure("lexical_path_escape_or_ambiguity")
    components = value.split("/")
    if any(
        component in {"", ".", ".."}
        or len(component.encode("utf-8")) > 255
        for component in components
    ):
        raise TypedCustodyFailure("lexical_path_escape_or_ambiguity")
    return value


def _filename_glob(value: Any) -> str:
    if not isinstance(value, str):
        raise TypedRecoverableInspection("schema_or_type_error")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise TypedCustodyFailure("glob_escape_or_ambiguity") from exc
    if not encoded or len(value) > 128 or len(encoded) > 512:
        raise TypedRecoverableInspection("scalar_range_error")
    if (
        value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or re.match(r"^[A-Za-z]:", value) is not None
    ):
        raise TypedCustodyFailure("glob_escape_or_ambiguity")
    components = value.split("/")
    if any(component == ".." for component in components):
        raise TypedCustodyFailure("glob_escape_or_ambiguity")
    if any(component in {"", "."} for component in components):
        raise TypedRecoverableInspection("glob_syntax_unsupported")
    if any("{" in component or "}" in component for component in components):
        raise TypedRecoverableInspection("glob_syntax_unsupported")
    return value


def _relative_glob_matches(relative_path: str, pattern: str) -> bool:
    """Match a validated glob against a manifest-relative descendant path.

    A pattern without a slash retains the published filename-filter behavior and
    is matched against the basename at any depth. Slash-bearing patterns are
    relative to the requested source_inspect path. A component that is exactly
    ``**`` consumes zero or more complete path components; other components use
    Python's deterministic case-sensitive fnmatch grammar.
    """
    if "/" not in pattern:
        return fnmatch.fnmatchcase(relative_path.rsplit("/", 1)[-1], pattern)

    path_components = tuple(relative_path.split("/"))
    pattern_components = tuple(pattern.split("/"))
    memo: dict[tuple[int, int], bool] = {}

    def matches(pattern_index: int, path_index: int) -> bool:
        key = (pattern_index, path_index)
        if key in memo:
            return memo[key]
        if pattern_index == len(pattern_components):
            result = path_index == len(path_components)
        elif pattern_components[pattern_index] == "**":
            result = matches(pattern_index + 1, path_index) or (
                path_index < len(path_components)
                and matches(pattern_index, path_index + 1)
            )
        else:
            result = (
                path_index < len(path_components)
                and fnmatch.fnmatchcase(
                    path_components[path_index], pattern_components[pattern_index]
                )
                and matches(pattern_index + 1, path_index + 1)
            )
        memo[key] = result
        return result

    return matches(0, 0)


def _parse_typed_manifest(manifest: bytes) -> TypedSourceIndex:
    if not manifest or not manifest.endswith(b"\n") or manifest.endswith(b"\n\n"):
        raise TypedCustodyFailure("manifest_format_invalid")
    files: list[ManifestEntry] = []
    file_digests: dict[str, str] = {}
    directories: set[str] = {"."}
    directory_count = 0
    total_path_bytes = 0
    previous_path_bytes: bytes | None = None
    for raw_line in manifest.splitlines(keepends=True):
        if len(raw_line) > 1024 or not raw_line.endswith(b"\n"):
            raise TypedCustodyFailure("manifest_format_invalid")
        try:
            line = raw_line[:-1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TypedCustodyFailure("manifest_format_invalid") from exc
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise TypedCustodyFailure("manifest_format_invalid")
        digest, raw_path = match.groups()
        try:
            path = _canonical_path(raw_path, allow_root=False)
        except TypedRecoverableInspection as exc:
            raise TypedCustodyFailure("manifest_format_invalid") from exc
        encoded_path = path.encode("utf-8")
        if previous_path_bytes is not None and encoded_path <= previous_path_bytes:
            raise TypedCustodyFailure("manifest_format_invalid")
        previous_path_bytes = encoded_path
        if len(files) >= TYPED_MAX_MANIFEST_FILES:
            raise TypedCustodyFailure("bootstrap_limit_exceeded")
        if total_path_bytes + len(encoded_path) > 16_777_216:
            raise TypedCustodyFailure("bootstrap_limit_exceeded")
        total_path_bytes += len(encoded_path)
        components = path.split("/")[:-1]
        parent = ""
        for component in components:
            parent = component if not parent else f"{parent}/{component}"
            if parent in directories:
                continue
            if directory_count >= 50_000:
                raise TypedCustodyFailure("bootstrap_limit_exceeded")
            parent_bytes = parent.encode("utf-8")
            if total_path_bytes + len(parent_bytes) > 16_777_216:
                raise TypedCustodyFailure("bootstrap_limit_exceeded")
            directories.add(parent)
            directory_count += 1
            total_path_bytes += len(parent_bytes)
        files.append(ManifestEntry(path=path, sha256=digest))
        file_digests[path] = digest
    if not files:
        raise TypedCustodyFailure("manifest_format_invalid")
    ordered_directories = tuple(sorted(directories, key=lambda item: item.encode("utf-8")))
    return TypedSourceIndex(
        files=tuple(files),
        file_digests=file_digests,
        directories=ordered_directories,
        directory_set=frozenset(directories),
    )


def _open_workspace_root(workspace: Path) -> int:
    try:
        descriptor = os.open(workspace, _open_flags(directory=True))
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise TypedCustodyFailure("workspace_root_not_directory")
        return descriptor
    except TypedCustodyFailure:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as exc:
        raise TypedCustodyFailure("workspace_root_access_ambiguous") from exc


def _open_relative_descriptor(root_fd: int, path: str, *, directory: bool) -> int:
    canonical = _canonical_path(path)
    current = os.dup(root_fd)
    try:
        if canonical == ".":
            if not directory:
                raise TypedRecoverableInspection("target_kind_mismatch")
            return current
        components = canonical.split("/")
        for index, component in enumerate(components):
            final = index == len(components) - 1
            next_directory = directory if final else True
            try:
                following = os.open(
                    component,
                    _open_flags(directory=next_directory),
                    dir_fd=current,
                )
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    raise TypedRecoverableInspection(
                        "canonical_in_root_path_not_found"
                    ) from exc
                if exc.errno in {errno.ENOTDIR, errno.EISDIR}:
                    raise TypedRecoverableInspection("target_kind_mismatch") from exc
                raise TypedCustodyFailure("descriptor_anchored_open_ambiguous") from exc
            os.close(current)
            current = following
        metadata = os.fstat(current)
        expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
        if not expected:
            raise TypedRecoverableInspection("target_kind_mismatch")
        return current
    except Exception:
        os.close(current)
        raise


def _read_bound_source_file(
    workspace: Path,
    index: TypedSourceIndex,
    path: str,
    *,
    maximum_size: int,
    remaining_budget: int,
) -> tuple[bytes, int]:
    expected_digest = index.file_digests.get(path)
    if expected_digest is None:
        if path in index.directory_set:
            raise TypedRecoverableInspection("target_kind_mismatch")
        raise TypedRecoverableInspection("canonical_in_root_path_not_found")
    root_fd = _open_workspace_root(workspace)
    try:
        descriptor = _open_relative_descriptor(root_fd, path, directory=False)
        try:
            size = os.fstat(descriptor).st_size
            if size > maximum_size:
                raise TypedRecoverableInspection("content_too_large")
            if size > remaining_budget:
                raise TypedRecoverableInspection("inspection_budget_exhausted")
            payload = _exact_read_descriptor(
                descriptor,
                expected_size=size,
                expected_sha256=expected_digest,
                maximum_size=maximum_size,
                over_limit_category="content_too_large",
            )
            return payload, size
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)


def _verify_live_source(workspace: Path, index: TypedSourceIndex) -> None:
    root_fd = _open_workspace_root(workspace)
    root_identity = _identity_tuple(os.fstat(root_fd))
    raw_dirents_observed = 0
    live_entries_verified = 0
    live_bytes_hashed = 0
    seen_files: set[str] = set()
    seen_directories: set[str] = {"."}

    def validate_name(name: str) -> None:
        try:
            encoded_name = name.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise TypedCustodyFailure("live_path_invalid") from exc
        if (
            name in {"", ".", ".."}
            or len(encoded_name) > 255
            or unicodedata.normalize("NFC", name) != name
            or "/" in name
            or "\\" in name
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
        ):
            raise TypedCustodyFailure("live_path_invalid")

    def stat_child(directory_fd: int, name: str) -> tuple[int, int, int, int, int, int]:
        try:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise TypedCustodyFailure("source_changed_during_read") from exc
        return _identity_tuple(metadata)

    def snapshot(
        directory_fd: int,
        prefix: str,
    ) -> list[tuple[str, tuple[int, int, int, int, int, int]]]:
        nonlocal raw_dirents_observed
        before = _identity_tuple(os.fstat(directory_fd))
        children: list[tuple[str, tuple[int, int, int, int, int, int]]] = []
        try:
            with os.scandir(directory_fd) as iterator:
                for entry in iterator:
                    raw_dirents_observed += 1
                    if raw_dirents_observed == TYPED_RAW_DIRENT_SENTINEL:
                        raise TypedCustodyFailure("bootstrap_limit_exceeded")
                    validate_name(entry.name)
                    children.append((entry.name, stat_child(directory_fd, entry.name)))
        except TypedCustodyFailure:
            raise
        except OSError as exc:
            raise TypedCustodyFailure("live_enumeration_ambiguous") from exc
        after = _identity_tuple(os.fstat(directory_fd))
        if before != after:
            raise TypedCustodyFailure("source_changed_during_read")
        children.sort(
            key=lambda item: (
                (item[0] if prefix == "." else f"{prefix}/{item[0]}").encode("utf-8")
            )
        )
        return children

    def open_observed_child(
        directory_fd: int,
        name: str,
        observed_identity: tuple[int, int, int, int, int, int],
        *,
        directory: bool,
    ) -> int:
        if stat_child(directory_fd, name) != observed_identity:
            raise TypedCustodyFailure("source_changed_during_read")
        try:
            descriptor = os.open(name, _open_flags(directory=directory), dir_fd=directory_fd)
        except OSError as exc:
            raise TypedCustodyFailure("descriptor_anchored_open_ambiguous") from exc
        if _identity_tuple(os.fstat(descriptor)) != observed_identity:
            os.close(descriptor)
            raise TypedCustodyFailure("source_changed_during_read")
        return descriptor

    def walk(directory_fd: int, prefix: str) -> None:
        nonlocal raw_dirents_observed, live_entries_verified, live_bytes_hashed
        directory_identity = _identity_tuple(os.fstat(directory_fd))
        children = snapshot(directory_fd, prefix)
        for name, observed_identity in children:
            if _identity_tuple(os.fstat(directory_fd)) != directory_identity:
                raise TypedCustodyFailure("source_changed_during_read")
            path = name if prefix == "." else f"{prefix}/{name}"
            if live_entries_verified >= TYPED_MAX_LIVE_ENTRIES:
                raise TypedCustodyFailure("bootstrap_limit_exceeded")
            live_entries_verified += 1
            if path in index.directory_set:
                if not stat.S_ISDIR(observed_identity[2]):
                    raise TypedCustodyFailure("source_kind_mismatch")
                child_fd = open_observed_child(
                    directory_fd, name, observed_identity, directory=True
                )
                try:
                    seen_directories.add(path)
                    walk(child_fd, path)
                    if _identity_tuple(os.fstat(child_fd)) != observed_identity:
                        raise TypedCustodyFailure("source_changed_during_read")
                finally:
                    os.close(child_fd)
                if stat_child(directory_fd, name) != observed_identity:
                    raise TypedCustodyFailure("source_changed_during_read")
                if _identity_tuple(os.fstat(directory_fd)) != directory_identity:
                    raise TypedCustodyFailure("source_changed_during_read")
                continue
            expected_digest = index.file_digests.get(path)
            if expected_digest is None:
                raise TypedCustodyFailure("unexpected_live_entry")
            if not stat.S_ISREG(observed_identity[2]):
                raise TypedCustodyFailure("source_kind_mismatch")
            file_fd = open_observed_child(
                directory_fd, name, observed_identity, directory=False
            )
            try:
                size = os.fstat(file_fd).st_size
                if (
                    size > TYPED_MAX_LIVE_FILE_BYTES
                    or live_bytes_hashed + size > TYPED_MAX_LIVE_HASH_BYTES
                ):
                    raise TypedCustodyFailure("bootstrap_limit_exceeded")
                _exact_read_descriptor(
                    file_fd,
                    expected_size=size,
                    expected_sha256=expected_digest,
                    maximum_size=TYPED_MAX_LIVE_FILE_BYTES,
                    over_limit_category="bootstrap_limit_exceeded",
                )
                live_bytes_hashed += size
                seen_files.add(path)
            finally:
                os.close(file_fd)
            if stat_child(directory_fd, name) != observed_identity:
                raise TypedCustodyFailure("source_changed_during_read")
            if _identity_tuple(os.fstat(directory_fd)) != directory_identity:
                raise TypedCustodyFailure("source_changed_during_read")
        if _identity_tuple(os.fstat(directory_fd)) != directory_identity:
            raise TypedCustodyFailure("source_changed_during_read")

    try:
        walk(root_fd, ".")
        replacement_root = _open_workspace_root(workspace)
        try:
            if _identity_tuple(os.fstat(replacement_root)) != root_identity:
                raise TypedCustodyFailure("source_changed_during_read")
        finally:
            os.close(replacement_root)
    finally:
        os.close(root_fd)
    if seen_files != set(index.file_digests) or seen_directories != set(index.directory_set):
        raise TypedCustodyFailure("source_manifest_live_mismatch")


def _logical_lines(payload: bytes) -> list[str]:
    if b"\0" in payload:
        raise TypedRecoverableInspection("content_unsupported")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TypedRecoverableInspection("content_unsupported") from exc
    if not payload:
        return []
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def _utf8_prefix_clip(value: str, maximum_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return value, False
    budget = maximum_bytes - len("…".encode("utf-8"))
    kept: list[str] = []
    used = 0
    for character in value:
        width = len(character.encode("utf-8"))
        if used + width > budget:
            break
        kept.append(character)
        used += width
    return "".join(kept) + "…", True


def _search_excerpt(line: str, query: str) -> tuple[str, bool]:
    if len(line.encode("utf-8")) <= 1024:
        return line, False
    match_start = line.find(query)
    if match_start < 0:
        raise TypedCustodyFailure("search_excerpt_without_match")
    before = line[:match_start]
    match = line[match_start : match_start + len(query)]
    after = line[match_start + len(query) :]
    leading = "…" if before else ""
    trailing = "…" if after else ""
    remaining = 1024 - len(match.encode("utf-8")) - len(leading.encode("utf-8")) - len(
        trailing.encode("utf-8")
    )
    if remaining < 0:
        raise TypedCustodyFailure("search_excerpt_budget_invariant")
    left_budget = remaining // 2
    right_budget = remaining - left_budget
    left_chars: list[str] = []
    used = 0
    for character in reversed(before):
        width = len(character.encode("utf-8"))
        if used + width > left_budget:
            break
        left_chars.append(character)
        used += width
    left = "".join(reversed(left_chars))
    right_chars: list[str] = []
    used = 0
    for character in after:
        width = len(character.encode("utf-8"))
        if used + width > right_budget:
            break
        right_chars.append(character)
        used += width
    return leading + left + match + "".join(right_chars) + trailing, True


class TypedSourceInspector:
    def __init__(self, config: TypedSourceProtocolConfig) -> None:
        self.config = config
        self.counters = InspectionCounters()

    def inspect(self, arguments: Any) -> str:
        if self.counters.calls >= 37:
            raise TypedRecoverableInspection("inspection_budget_exhausted")
        if not isinstance(arguments, dict):
            raise TypedRecoverableInspection("schema_or_type_error")
        self.counters.calls += 1
        if self.counters.entries_visited >= 20_000:
            raise TypedRecoverableInspection("inspection_budget_exhausted")
        operation = arguments.get("operation")
        if operation == "list_dir":
            records, considered, reasons = self._list_dir(arguments)
        elif operation == "read_file":
            records, considered, reasons = self._read_file(arguments)
        elif operation == "search_text":
            records, considered, reasons = self._search_text(arguments)
        elif operation == "find_files":
            records, considered, reasons = self._find_files(arguments)
        else:
            raise TypedRecoverableInspection("schema_or_type_error")
        return self._canonical_result(operation, records, considered, reasons)

    def _validate_shape(
        self, arguments: dict[str, Any], required: set[str], optional: set[str] = set()
    ) -> str:
        if set(arguments) != required | (set(arguments) & optional):
            raise TypedRecoverableInspection("schema_or_type_error")
        return _canonical_path(arguments["path"])

    def _target_directory(self, path: str) -> None:
        if path in self.config.source_index.file_digests:
            raise TypedRecoverableInspection("target_kind_mismatch")
        if path not in self.config.source_index.directory_set:
            raise TypedRecoverableInspection("canonical_in_root_path_not_found")

    def _visit(self, local: dict[str, int], reasons: set[str], maximum: int) -> bool:
        if local["entries"] >= maximum:
            reasons.add("per_call_entries_limit")
            return False
        if self.counters.entries_visited >= 20_000:
            reasons.add("trajectory_entries_limit")
            return False
        local["entries"] += 1
        self.counters.entries_visited += 1
        return True

    def _can_open(self, local: dict[str, int], reasons: set[str], maximum: int) -> bool:
        if local["files"] >= maximum:
            reasons.add("per_call_files_limit")
            return False
        if self.counters.files_opened >= 1_000:
            reasons.add("trajectory_files_limit")
            return False
        return True

    def _children(self, path: str) -> list[tuple[str, str]]:
        prefix = "" if path == "." else path + "/"
        records: list[tuple[str, str]] = []
        for directory in self.config.source_index.directories:
            if directory == "." or not directory.startswith(prefix):
                continue
            remainder = directory[len(prefix) :]
            if "/" not in remainder:
                records.append((directory, "directory"))
        for entry in self.config.source_index.files:
            if not entry.path.startswith(prefix):
                continue
            remainder = entry.path[len(prefix) :]
            if "/" not in remainder:
                records.append((entry.path, "file"))
        return sorted(records, key=lambda record: record[0].encode("utf-8"))

    def _descendants(self, path: str) -> list[tuple[str, str]]:
        prefix = "" if path == "." else path + "/"
        records = [
            (directory, "directory")
            for directory in self.config.source_index.directories
            if directory != "." and directory.startswith(prefix)
        ]
        records.extend(
            (entry.path, "file")
            for entry in self.config.source_index.files
            if entry.path.startswith(prefix)
        )
        return sorted(records, key=lambda record: record[0].encode("utf-8"))

    def _list_dir(self, arguments: dict[str, Any]) -> tuple[list[dict], int, set[str]]:
        path = self._validate_shape(arguments, {"operation", "path"})
        self._target_directory(path)
        records: list[dict] = []
        reasons: set[str] = set()
        local = {"entries": 0, "files": 0, "bytes": 0}
        for candidate, kind in self._children(path):
            if len(records) >= 200:
                reasons.add("operation_record_limit")
                break
            if not self._visit(local, reasons, 1000):
                break
            records.append({"relative_path": candidate, "kind": kind})
            if len(records) == 200:
                reasons.add("operation_record_limit")
                break
        return records, len(records), reasons

    def _read_file(self, arguments: dict[str, Any]) -> tuple[list[dict], int, set[str]]:
        path = self._validate_shape(
            arguments, {"operation", "path", "start_line", "end_line"}
        )
        start = arguments.get("start_line")
        end = arguments.get("end_line")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 1
            or end < start
            or end > 1_000_000
            or end - start + 1 > 240
        ):
            raise TypedRecoverableInspection("scalar_range_error")
        if path not in self.config.source_index.file_digests:
            if path in self.config.source_index.directory_set:
                raise TypedRecoverableInspection("target_kind_mismatch")
            raise TypedRecoverableInspection("canonical_in_root_path_not_found")
        if self.counters.entries_visited >= 20_000 or self.counters.files_opened >= 1_000:
            raise TypedRecoverableInspection("inspection_budget_exhausted")
        if self.counters.file_bytes_read >= 134_217_728:
            raise TypedRecoverableInspection("inspection_budget_exhausted")
        self.counters.entries_visited += 1
        remaining = 134_217_728 - self.counters.file_bytes_read
        root_fd = _open_workspace_root(self.config.workspace)
        try:
            descriptor = _open_relative_descriptor(root_fd, path, directory=False)
            self.counters.files_opened += 1
            try:
                charged = os.fstat(descriptor).st_size
                if charged > 1_048_576:
                    raise TypedRecoverableInspection("content_too_large")
                if charged > remaining:
                    raise TypedRecoverableInspection("inspection_budget_exhausted")
                payload = _exact_read_descriptor(
                    descriptor,
                    expected_size=charged,
                    expected_sha256=self.config.source_index.file_digests[path],
                    maximum_size=1_048_576,
                    over_limit_category="content_too_large",
                )
            finally:
                os.close(descriptor)
        finally:
            os.close(root_fd)
        self.counters.file_bytes_read += charged
        lines = _logical_lines(payload)
        records: list[dict] = []
        reasons: set[str] = set()
        for line_number in range(start, min(end, len(lines)) + 1):
            clipped, was_clipped = _utf8_prefix_clip(lines[line_number - 1], 2048)
            if was_clipped:
                reasons.add("field_utf8_limit")
            records.append(
                {"line_number": line_number, "text": clipped, "text_clipped": was_clipped}
            )
        return records, len(records), reasons

    def _search_text(self, arguments: dict[str, Any]) -> tuple[list[dict], int, set[str]]:
        path = self._validate_shape(
            arguments, {"operation", "path", "query"}, {"file_glob"}
        )
        if path not in self.config.source_index.directory_set and path not in self.config.source_index.file_digests:
            raise TypedRecoverableInspection("canonical_in_root_path_not_found")
        if (
            self.counters.files_opened >= 1_000
            or self.counters.file_bytes_read >= 134_217_728
        ):
            raise TypedRecoverableInspection("inspection_budget_exhausted")
        query = arguments.get("query")
        if not isinstance(query, str):
            raise TypedRecoverableInspection("schema_or_type_error")
        try:
            query_bytes = query.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise TypedRecoverableInspection("scalar_range_error") from exc
        if not query_bytes or len(query_bytes) > 256 or any(ch in query for ch in "\0\n\r"):
            raise TypedRecoverableInspection("scalar_range_error")
        file_glob = arguments.get("file_glob")
        if "file_glob" in arguments:
            file_glob = _filename_glob(file_glob)
        if path in self.config.source_index.file_digests:
            candidates = [path]
            candidate_match_paths = {path: path.rsplit("/", 1)[-1]}
        else:
            prefix = "" if path == "." else path + "/"
            candidates = [
                entry.path
                for entry in self.config.source_index.files
                if entry.path.startswith(prefix)
            ]
            candidate_match_paths = {
                candidate: candidate[len(prefix) :] for candidate in candidates
            }
        records: list[dict] = []
        reasons: set[str] = set()
        local = {"entries": 0, "files": 0, "bytes": 0}
        stop = False
        for candidate in candidates:
            if len(records) >= 80:
                reasons.add("operation_record_limit")
                break
            if not self._visit(local, reasons, 1000):
                break
            if file_glob is not None and not _relative_glob_matches(
                candidate_match_paths[candidate], file_glob
            ):
                continue
            if not self._can_open(local, reasons, 200):
                break
            root_fd = _open_workspace_root(self.config.workspace)
            try:
                descriptor = _open_relative_descriptor(root_fd, candidate, directory=False)
                local["files"] += 1
                self.counters.files_opened += 1
                try:
                    size = os.fstat(descriptor).st_size
                    if size > 1_048_576:
                        reasons.add("per_file_size_limit")
                        continue
                    if local["bytes"] + size > 16_777_216:
                        reasons.add("per_call_bytes_limit")
                        break
                    if self.counters.file_bytes_read + size > 134_217_728:
                        reasons.add("trajectory_bytes_limit")
                        break
                    payload = _exact_read_descriptor(
                        descriptor,
                        expected_size=size,
                        expected_sha256=self.config.source_index.file_digests[candidate],
                        maximum_size=1_048_576,
                        over_limit_category="content_too_large",
                    )
                    local["bytes"] += size
                    self.counters.file_bytes_read += size
                finally:
                    os.close(descriptor)
            finally:
                os.close(root_fd)
            try:
                lines = _logical_lines(payload)
            except TypedRecoverableInspection as exc:
                if exc.category != "content_unsupported":
                    raise
                reasons.add("binary_or_non_utf8_skipped")
                continue
            for line_number, line in enumerate(lines, start=1):
                if query not in line:
                    continue
                if len(records) >= 80:
                    reasons.add("operation_record_limit")
                    stop = True
                    break
                excerpt, clipped = _search_excerpt(line, query)
                if clipped:
                    reasons.add("field_utf8_limit")
                records.append(
                    {
                        "relative_path": candidate,
                        "line_number": line_number,
                        "excerpt": excerpt,
                        "excerpt_clipped": clipped,
                    }
                )
                if len(records) == 80:
                    reasons.add("operation_record_limit")
                    stop = True
                    break
            if stop:
                break
        return records, len(records), reasons

    def _find_files(self, arguments: dict[str, Any]) -> tuple[list[dict], int, set[str]]:
        path = self._validate_shape(arguments, {"operation", "path", "name_glob"})
        self._target_directory(path)
        name_glob = _filename_glob(arguments.get("name_glob"))
        records: list[dict] = []
        reasons: set[str] = set()
        local = {"entries": 0, "files": 0, "bytes": 0}
        for candidate, kind in self._descendants(path):
            if len(records) >= 200:
                reasons.add("operation_record_limit")
                break
            if not self._visit(local, reasons, 10_000):
                break
            prefix = "" if path == "." else path + "/"
            if _relative_glob_matches(candidate[len(prefix) :], name_glob):
                records.append({"relative_path": candidate, "kind": kind})
                if len(records) == 200:
                    reasons.add("operation_record_limit")
                    break
        return records, len(records), reasons

    def _canonical_result(
        self,
        operation: str,
        records: list[dict],
        considered: int,
        reasons: set[str],
    ) -> str:
        ordered_reasons = [reason for reason in TYPED_TRUNCATION_REASON_ORDER if reason in reasons]

        def encode() -> bytes:
            envelope = {
                "operation": operation,
                "records": records,
                "records_considered": considered,
                "records_returned": len(records),
                "schema_version": 1,
                "truncated": bool(ordered_reasons),
                "truncation_reasons": ordered_reasons,
            }
            return (
                json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                + "\n"
            ).encode("utf-8")

        payload = encode()
        while len(payload) > TYPED_PROTOCOL_MAX_RESULT_BYTES:
            if "result_bytes_limit" not in ordered_reasons:
                ordered_reasons.append("result_bytes_limit")
                ordered_reasons.sort(key=TYPED_TRUNCATION_REASON_ORDER.index)
            if not records:
                raise TypedCustodyFailure("result_envelope_invariant")
            records.pop()
            payload = encode()
        if not records and len(payload) >= 4096:
            raise TypedCustodyFailure("result_envelope_invariant")
        if self.counters.serialized_result_bytes + len(payload) > TYPED_PROTOCOL_RESULT_BUDGET:
            raise TypedCustodyFailure("trajectory_result_counter_invariant")
        self.counters.serialized_result_bytes += len(payload)
        return payload.decode("utf-8")


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, _open_flags(directory=True))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except TypedCustodyFailure:
        raise
    except OSError as exc:
        raise TypedCustodyFailure("directory_fsync_failure") from exc


def _path_exists_no_follow(path: Path) -> bool:
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise TypedCustodyFailure("publication_inventory_ambiguous") from exc


def _write_exclusive_verified(path: Path, payload: bytes) -> tuple[int, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise TypedCustodyFailure("publication_exclusive_create_failure") from exc
    try:
        view = memoryview(payload)
        written = 0
        while written < len(payload):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise TypedCustodyFailure("publication_short_write")
            written += count
        os.fsync(descriptor)
        before = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    verify_fd = _open_external_regular(path)
    try:
        verified = _exact_read_descriptor(
            verify_fd,
            expected_size=len(payload),
            expected_sha256=_sha256_bytes(payload),
            maximum_size=max(len(payload), 1),
            over_limit_category="publication_size_invariant",
        )
        after = os.fstat(verify_fd)
    finally:
        os.close(verify_fd)
    if verified != payload or before.st_dev != after.st_dev or before.st_ino != after.st_ino:
        raise TypedCustodyFailure("publication_verification_failure")
    return before.st_dev, before.st_ino


def _read_canonical_metadata(path: Path, maximum_bytes: int = 16_384) -> dict[str, Any]:
    descriptor = _open_external_regular(path)
    try:
        before = os.fstat(descriptor)
        if before.st_size > maximum_bytes:
            raise TypedCustodyFailure("publication_metadata_too_large")
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                raise TypedCustodyFailure("publication_metadata_short_read")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if _identity_tuple(before) != _identity_tuple(after):
            raise TypedCustodyFailure("publication_metadata_changed_during_read")
        payload = b"".join(chunks)
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TypedCustodyFailure("publication_metadata_invalid") from exc
    if not isinstance(value, dict) or _canonical_json_bytes(value) != payload:
        raise TypedCustodyFailure("publication_metadata_invalid")
    return value


def _publication_names(config: TypedSourceProtocolConfig) -> dict[str, str]:
    return {
        "candidate": config.candidate_output.name,
        "prepared": f"{config.run_id}.prepared.json",
        "receipt": f"{config.run_id}.commit.json",
        "candidate_prefix": f".{config.candidate_output.name}.{config.run_id}.candidate.",
        "receipt_prefix": f".{config.run_id}.receipt.",
        "intent_temp_prefix": f".{config.run_id}.prepared.",
    }


def _validate_publication_basename(name: Any, prefix: str | None = None) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
        or (prefix is not None and not name.startswith(prefix))
    ):
        raise TypedCustodyFailure("publication_metadata_invalid")
    return name


def _verify_candidate_against_metadata(path: Path, metadata: dict[str, Any]) -> os.stat_result:
    descriptor = _open_external_regular(path)
    try:
        before = os.fstat(descriptor)
        size = metadata.get("candidate_bytes")
        digest = metadata.get("candidate_sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise TypedCustodyFailure("publication_metadata_invalid")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise TypedCustodyFailure("publication_metadata_invalid")
        _exact_read_descriptor(
            descriptor,
            expected_size=size,
            expected_sha256=digest,
            maximum_size=TYPED_PROTOCOL_MAX_SUBMISSION_BYTES,
            over_limit_category="publication_size_invariant",
        )
        return before
    finally:
        os.close(descriptor)


def _validate_prepared_metadata(
    config: TypedSourceProtocolConfig, value: dict[str, Any], *, state: str
) -> dict[str, Any]:
    names = _publication_names(config)
    required = {
        "schema_version",
        "run_id",
        "candidate_basename",
        "candidate_temporary_basename",
        "receipt_temporary_basename",
        "committed_receipt_basename",
        "candidate_sha256",
        "candidate_bytes",
        "state",
    }
    if set(value) != required or value.get("schema_version") != 1:
        raise TypedCustodyFailure("publication_metadata_invalid")
    if value.get("run_id") != config.run_id or value.get("state") != state:
        raise TypedCustodyFailure("publication_metadata_invalid")
    if value.get("candidate_basename") != names["candidate"]:
        raise TypedCustodyFailure("publication_metadata_invalid")
    if value.get("committed_receipt_basename") != names["receipt"]:
        raise TypedCustodyFailure("publication_metadata_invalid")
    _validate_publication_basename(
        value.get("candidate_temporary_basename"), names["candidate_prefix"]
    )
    _validate_publication_basename(
        value.get("receipt_temporary_basename"), names["receipt_prefix"]
    )
    if not isinstance(value.get("candidate_bytes"), int) or isinstance(
        value.get("candidate_bytes"), bool
    ):
        raise TypedCustodyFailure("publication_metadata_invalid")
    if not isinstance(value.get("candidate_sha256"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["candidate_sha256"]
    ):
        raise TypedCustodyFailure("publication_metadata_invalid")
    return value


def _read_verified_regular_recovery_payload(
    path: Path,
    *,
    maximum_bytes: int,
) -> tuple[bytes | None, tuple[int, int, int, int, int, int]]:
    try:
        named_before = os.lstat(path)
    except OSError as exc:
        raise TypedCustodyFailure("publication_receipt_temporary_access_ambiguous") from exc
    named_identity = _identity_tuple(named_before)
    if not stat.S_ISREG(named_before.st_mode):
        raise TypedCustodyFailure("publication_receipt_temporary_kind_ambiguous")
    descriptor = _open_external_regular(path)
    try:
        opened_before = os.fstat(descriptor)
        if _identity_tuple(opened_before) != named_identity:
            raise TypedCustodyFailure("publication_receipt_temporary_identity_ambiguous")
        if opened_before.st_size > maximum_bytes:
            payload: bytes | None = None
        else:
            remaining = opened_before.st_size
            chunks: list[bytes] = []
            while remaining:
                try:
                    chunk = os.read(descriptor, min(1_048_576, remaining))
                except OSError as exc:
                    raise TypedCustodyFailure(
                        "publication_receipt_temporary_access_ambiguous"
                    ) from exc
                if not chunk:
                    raise TypedCustodyFailure(
                        "publication_receipt_temporary_identity_ambiguous"
                    )
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
        if _identity_tuple(os.fstat(descriptor)) != named_identity:
            raise TypedCustodyFailure("publication_receipt_temporary_identity_ambiguous")
    finally:
        os.close(descriptor)
    try:
        if _identity_tuple(os.lstat(path)) != named_identity:
            raise TypedCustodyFailure("publication_receipt_temporary_identity_ambiguous")
    except TypedCustodyFailure:
        raise
    except OSError as exc:
        raise TypedCustodyFailure("publication_receipt_temporary_access_ambiguous") from exc
    return payload, named_identity


def _remove_verified_invalid_receipt_temporary(
    path: Path,
    expected_identity: tuple[int, int, int, int, int, int],
) -> None:
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise TypedCustodyFailure("publication_receipt_temporary_access_ambiguous") from exc
    if not stat.S_ISREG(current.st_mode) or _identity_tuple(current) != expected_identity:
        raise TypedCustodyFailure("publication_receipt_temporary_identity_ambiguous")
    _unlink_and_fsync(path)


def _relevant_publication_inventory(config: TypedSourceProtocolConfig) -> set[str]:
    names = _publication_names(config)
    relevant: set[str] = set()
    try:
        with os.scandir(config.candidate_output.parent) as entries:
            for entry in entries:
                name = entry.name
                if name in {names["candidate"], names["prepared"], names["receipt"]} or any(
                    name.startswith(names[prefix])
                    for prefix in ("candidate_prefix", "receipt_prefix", "intent_temp_prefix")
                ):
                    relevant.add(name)
    except OSError as exc:
        raise TypedCustodyFailure("publication_inventory_ambiguous") from exc
    return relevant


def _link_no_replace(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination, follow_symlinks=False)
    except OSError as exc:
        raise TypedCustodyFailure("publication_no_replace_link_failure") from exc


def _unlink_and_fsync(path: Path) -> None:
    try:
        path.unlink()
        _fsync_directory(path.parent)
    except OSError as exc:
        raise TypedCustodyFailure("publication_cleanup_ambiguous") from exc


def _publish_receipt_from_prepared(
    config: TypedSourceProtocolConfig,
    prepared: dict[str, Any],
) -> tuple[str, ...]:
    directory = config.candidate_output.parent
    names = _publication_names(config)
    receipt_path = directory / names["receipt"]
    receipt_temp = directory / prepared["receipt_temporary_basename"]
    committed = dict(prepared)
    committed["state"] = "committed"
    payload = _canonical_json_bytes(committed)
    if _path_exists_no_follow(receipt_temp):
        existing_payload, existing_identity = _read_verified_regular_recovery_payload(
            receipt_temp,
            maximum_bytes=16_384,
        )
        if existing_payload != payload:
            _remove_verified_invalid_receipt_temporary(
                receipt_temp,
                existing_identity,
            )
    if not _path_exists_no_follow(receipt_temp):
        _write_exclusive_verified(receipt_temp, payload)
    _link_no_replace(receipt_temp, receipt_path)
    _fsync_directory(directory)
    return ()


def _recover_typed_publication(config: TypedSourceProtocolConfig) -> tuple[str | None, tuple[str, ...]]:
    directory = config.candidate_output.parent
    names = _publication_names(config)
    inventory = _relevant_publication_inventory(config)
    if not inventory:
        return None, ()
    candidate_path = directory / names["candidate"]
    prepared_path = directory / names["prepared"]
    receipt_path = directory / names["receipt"]
    candidate_exists = names["candidate"] in inventory
    prepared_exists = names["prepared"] in inventory
    receipt_exists = names["receipt"] in inventory
    prepared: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    if prepared_exists:
        prepared = _validate_prepared_metadata(
            config, _read_canonical_metadata(prepared_path), state="prepared"
        )
    if receipt_exists:
        receipt = _validate_prepared_metadata(
            config, _read_canonical_metadata(receipt_path), state="committed"
        )
    expected_inventory = {names["candidate"], names["prepared"], names["receipt"]}
    if prepared is not None:
        expected_inventory.update(
            {
                prepared["candidate_temporary_basename"],
                prepared["receipt_temporary_basename"],
            }
        )
    if receipt is not None:
        expected_inventory.update(
            {
                receipt["candidate_temporary_basename"],
                receipt["receipt_temporary_basename"],
            }
        )
    if inventory - expected_inventory:
        raise TypedCustodyFailure("publication_quarantined")

    if receipt_exists:
        assert receipt is not None
        if not candidate_exists:
            raise TypedCustodyFailure("publication_quarantined")
        if prepared is not None:
            expected_receipt = dict(prepared)
            expected_receipt["state"] = "committed"
            if receipt != expected_receipt:
                raise TypedCustodyFailure("publication_quarantined")
        candidate_stat = _verify_candidate_against_metadata(candidate_path, receipt)
        receipt_temp = directory / receipt["receipt_temporary_basename"]
        candidate_temp = directory / receipt["candidate_temporary_basename"]
        if _path_exists_no_follow(receipt_temp):
            if _read_canonical_metadata(receipt_temp) != receipt:
                raise TypedCustodyFailure("publication_quarantined")
        if _path_exists_no_follow(candidate_temp):
            temp_stat = _verify_candidate_against_metadata(candidate_temp, receipt)
            if (candidate_stat.st_dev, candidate_stat.st_ino) != (
                temp_stat.st_dev,
                temp_stat.st_ino,
            ):
                raise TypedCustodyFailure("publication_quarantined")
        _fsync_directory(directory)
        warnings: set[str] = set()
        for basename in (
            receipt["receipt_temporary_basename"],
            receipt["candidate_temporary_basename"],
            names["prepared"],
        ):
            path = directory / basename
            if _path_exists_no_follow(path):
                try:
                    path.unlink()
                except OSError:
                    warnings.add("accepted_with_temporary_cleanup_warning")
                    continue
                try:
                    _fsync_directory(directory)
                except TypedCustodyFailure:
                    warnings.add("accepted_with_directory_durability_warning")
        return "candidate_already_committed", tuple(sorted(warnings))

    if prepared is None:
        raise TypedCustodyFailure("publication_quarantined")
    candidate_temp = directory / prepared["candidate_temporary_basename"]
    receipt_temp = directory / prepared["receipt_temporary_basename"]
    candidate_temp_exists = prepared["candidate_temporary_basename"] in inventory
    if candidate_exists and candidate_temp_exists:
        candidate_stat = _verify_candidate_against_metadata(candidate_path, prepared)
        temp_stat = _verify_candidate_against_metadata(candidate_temp, prepared)
        if (candidate_stat.st_dev, candidate_stat.st_ino) != (temp_stat.st_dev, temp_stat.st_ino):
            raise TypedCustodyFailure("publication_quarantined")
        _fsync_directory(directory)
        try:
            _publish_receipt_from_prepared(config, prepared)
            for path in (receipt_temp, candidate_temp, prepared_path):
                if _path_exists_no_follow(path):
                    _unlink_and_fsync(path)
            return "candidate_already_committed", ()
        except TypedCustodyFailure as exc:
            raise TypedCustodyFailure("publication_quarantined") from exc

    if not candidate_exists and candidate_temp_exists:
        _verify_candidate_against_metadata(candidate_temp, prepared)
        for path in (receipt_temp, candidate_temp, prepared_path):
            if _path_exists_no_follow(path):
                _unlink_and_fsync(path)
        return "aborted_pre_commit", ()
    raise TypedCustodyFailure("publication_quarantined")


def _publish_typed_candidate(
    config: TypedSourceProtocolConfig,
    payload: bytes,
    *,
    audit_log: callable,
) -> tuple[str, ...]:
    if len(payload) > TYPED_PROTOCOL_MAX_SUBMISSION_BYTES:
        raise TypedCustodyFailure("candidate_size_invariant")
    _verify_live_source(config.workspace, config.source_index)
    outcome, _ = _recover_typed_publication(config)
    if outcome is not None:
        raise TypedCustodyFailure("publication_quarantined")
    directory = config.candidate_output.parent
    names = _publication_names(config)
    candidate_temp = directory / (
        names["candidate_prefix"] + uuid.uuid4().hex + ".tmp"
    )
    receipt_temp_name = names["receipt_prefix"] + uuid.uuid4().hex + ".tmp"
    prepared_path = directory / names["prepared"]
    prepared_temp = directory / (
        names["intent_temp_prefix"] + uuid.uuid4().hex + ".tmp"
    )
    receipt_path = directory / names["receipt"]
    committed = False
    prepared_published = False
    try:
        audit_log(
            "typed_precommit_audit",
            candidate_sha256=_sha256_bytes(payload),
            candidate_bytes=len(payload),
            source_manifest_sha256=config.source_manifest_sha256,
            schema_sha256=config.schema_sha256,
        )
        _write_exclusive_verified(candidate_temp, payload)
        prepared = {
            "schema_version": 1,
            "run_id": config.run_id,
            "candidate_basename": names["candidate"],
            "candidate_temporary_basename": candidate_temp.name,
            "receipt_temporary_basename": receipt_temp_name,
            "committed_receipt_basename": names["receipt"],
            "candidate_sha256": _sha256_bytes(payload),
            "candidate_bytes": len(payload),
            "state": "prepared",
        }
        prepared_payload = _canonical_json_bytes(prepared)
        _write_exclusive_verified(prepared_temp, prepared_payload)
        _link_no_replace(prepared_temp, prepared_path)
        _fsync_directory(directory)
        prepared_published = True
        _unlink_and_fsync(prepared_temp)
        _link_no_replace(candidate_temp, config.candidate_output)
        _fsync_directory(directory)
        committed = True
        warnings: set[str] = set()
        try:
            _publish_receipt_from_prepared(config, prepared)
            for path in (directory / receipt_temp_name, candidate_temp, prepared_path):
                if _path_exists_no_follow(path):
                    try:
                        path.unlink()
                    except OSError:
                        warnings.add("accepted_with_temporary_cleanup_warning")
                        continue
                    try:
                        _fsync_directory(directory)
                    except TypedCustodyFailure:
                        warnings.add("accepted_with_directory_durability_warning")
        except TypedCustodyFailure:
            warnings.add("accepted_with_audit_log_warning")
        try:
            audit_log(
                "typed_commit",
                candidate_sha256=prepared["candidate_sha256"],
                receipt=str(receipt_path),
                warnings=sorted(warnings),
            )
        except Exception:
            warnings.add("accepted_with_audit_log_warning")
        return tuple(sorted(warnings))
    except Exception:
        if committed:
            return ("accepted_with_audit_log_warning",)
        if not prepared_published:
            for path in (prepared_temp, candidate_temp):
                if _path_exists_no_follow(path):
                    try:
                        _unlink_and_fsync(path)
                    except TypedCustodyFailure:
                        pass
        raise


def _read_bound_external(
    path: Path,
    expected_digest: str,
    *,
    maximum_size: int,
    over_limit_category: str = "bootstrap_limit_exceeded",
) -> bytes:
    descriptor = _open_external_regular(path)
    try:
        size = os.fstat(descriptor).st_size
        if size == 0:
            raise TypedCustodyFailure("manifest_format_invalid")
        if size > maximum_size:
            raise TypedCustodyFailure(over_limit_category)
        return _exact_read_descriptor(
            descriptor,
            expected_size=size,
            expected_sha256=expected_digest,
            maximum_size=maximum_size,
            over_limit_category=over_limit_category,
        )
    finally:
        os.close(descriptor)


def _prepare_typed_source_protocol(args: argparse.Namespace) -> TypedSourceProtocolConfig:
    if not args.code_only:
        raise ValueError("typed source inspection requires --code-only")
    if args.max_turns != TYPED_PROTOCOL_MAX_TURNS:
        raise ValueError("typed source inspection requires exactly 40 turns")
    if not isinstance(args.run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", args.run_id):
        raise ValueError("typed source inspection requires a safe --run-id")
    workspace = args.workspace.resolve()
    rollout = args.rollout_dir.resolve()
    candidate_output = args.candidate_output.resolve()
    paths = {
        "schema": args.submission_schema.resolve(),
        "manifest": args.source_manifest_before.resolve(),
        "archive": args.source_archive.resolve(),
        "proposal03": args.protocol_proposal_03.resolve(),
        "proposal04": args.protocol_proposal_04.resolve(),
        "proposal05": args.protocol_proposal_05.resolve(),
        "review": args.implementation_review.resolve(),
    }
    semantic_validator_bytes: bytes | None = None
    semantic_validator_sha256: str | None = None
    semantic_validator_supplied = args.typed_semantic_validator is not None
    semantic_digest_supplied = args.expected_typed_semantic_validator_sha256 is not None
    if semantic_validator_supplied != semantic_digest_supplied:
        raise ValueError(
            "typed semantic validator path and expected digest must be supplied together"
        )
    if semantic_validator_supplied:
        semantic_path = args.typed_semantic_validator.resolve()
        if semantic_path.is_relative_to(workspace):
            raise ValueError("semantic validator must be outside the source workspace")
        semantic_validator_sha256 = _expected_digest(
            args.expected_typed_semantic_validator_sha256,
            "expected typed semantic validator digest",
        )
        semantic_validator_bytes = _read_bound_external(
            semantic_path,
            semantic_validator_sha256,
            maximum_size=TYPED_SEMANTIC_VALIDATOR_MAX_BYTES,
            over_limit_category="semantic_validator_limit_exceeded",
        )
        _validate_typed_semantic_validator_source(semantic_validator_bytes)
    for label, path in paths.items():
        if path.is_relative_to(workspace):
            raise ValueError(f"{label} must be outside the source workspace")
    if rollout.is_relative_to(workspace) or candidate_output.is_relative_to(workspace):
        raise ValueError("rollout and candidate output must be outside the source workspace")
    if not candidate_output.parent.is_dir() or not rollout.parent.is_dir():
        raise ValueError("typed output parents must already exist")
    if _sha256_bytes(args.prompt.encode("utf-8")) != _expected_digest(
        args.expected_prompt_sha256, "expected prompt digest"
    ):
        raise ValueError("prompt digest mismatch")
    runner_digest = _sha256_bytes(Path(__file__).read_bytes())
    if runner_digest != _expected_digest(args.expected_runner_sha256, "expected runner digest"):
        raise ValueError("runner digest mismatch")
    proposal_bindings = (
        ("03", paths["proposal03"], args.expected_protocol_proposal_03_sha256),
        ("04", paths["proposal04"], args.expected_protocol_proposal_04_sha256),
        ("05", paths["proposal05"], args.expected_protocol_proposal_05_sha256),
    )
    for number, path, supplied_digest in proposal_bindings:
        expected = _expected_digest(supplied_digest, f"expected proposal {number} digest")
        if expected != TYPED_PROTOCOL_PROPOSAL_SHA256[number]:
            raise ValueError(f"proposal {number} digest is not the reviewed digest")
        _read_bound_external(path, expected, maximum_size=1_048_576)
    review_digest = _expected_digest(
        args.expected_implementation_review_sha256, "expected implementation review digest"
    )
    _read_bound_external(paths["review"], review_digest, maximum_size=1_048_576)
    archive_digest = _expected_digest(
        args.expected_source_archive_sha256, "expected source archive digest"
    )
    _read_bound_external(paths["archive"], archive_digest, maximum_size=1_073_741_824)
    schema_digest = _expected_digest(
        args.expected_submission_schema_sha256, "expected submission schema digest"
    )
    schema_bytes = _read_bound_external(paths["schema"], schema_digest, maximum_size=1_048_576)
    try:
        schema = json.loads(schema_bytes)
    except json.JSONDecodeError as exc:
        raise TypedCustodyFailure("submission_schema_invalid") from exc
    _validate_supported_schema(schema)
    manifest_digest = _expected_digest(
        args.expected_source_manifest_sha256, "expected source manifest digest"
    )
    manifest_bytes = _read_bound_external(
        paths["manifest"], manifest_digest, maximum_size=16_777_216
    )
    source_index = _parse_typed_manifest(manifest_bytes)
    _verify_live_source(workspace, source_index)
    config = TypedSourceProtocolConfig(
        schema=schema,
        schema_sha256=schema_digest,
        candidate_output=candidate_output,
        source_manifest=manifest_bytes,
        source_manifest_sha256=manifest_digest,
        source_index=source_index,
        run_id=args.run_id,
        workspace=workspace,
        semantic_validator_bytes=semantic_validator_bytes,
        semantic_validator_sha256=semantic_validator_sha256,
    )
    outcome, warnings = _recover_typed_publication(config)
    config.startup_outcome = outcome
    config.startup_warnings = warnings
    return config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(value: str, limit: int = 24_000) -> str:
    if len(value) <= limit:
        return value
    half = limit // 2
    return value[:half] + "\n...[output truncated]...\n" + value[-half:]


class MessagesClient:
    def __init__(
        self,
        model: str,
        code_only: bool = False,
        allow_finish: bool = True,
        submission_schema: dict[str, Any] | None = None,
        typed_submission_schema: dict[str, Any] | None = None,
        request_timeout_seconds: int = 300,
        request_attempts: int = 10,
    ) -> None:
        if request_timeout_seconds < 1:
            raise ValueError("request_timeout_seconds must be positive")
        if request_attempts < 1:
            raise ValueError("request_attempts must be positive")
        self.model = model
        self.code_only = code_only
        self.request_timeout_seconds = request_timeout_seconds
        self.request_attempts = request_attempts
        if submission_schema is not None and typed_submission_schema is not None:
            raise ValueError("structured submission modes are mutually exclusive")
        self.structured_submission = submission_schema is not None
        self.typed_source_inspection = typed_submission_schema is not None
        if typed_submission_schema is not None:
            self.submit_design_tool = {
                "name": "submit_design",
                "description": "Submit one complete schema-valid synthetic mutation design.",
                "input_schema": typed_submission_schema,
            }
            self.tools = [SOURCE_INSPECT_TOOL, self.submit_design_tool]
            self.tool_choice = {"type": "any", "disable_parallel_tool_use": True}
        elif submission_schema is None:
            self.tools = [
                tool
                for tool in TOOLS
                if (not code_only or tool["name"] != "view_image")
                and (allow_finish or tool["name"] != "finish")
            ]
            self.tool_choice: dict[str, str] | None = None
        else:
            self.tools = [
                TOOLS[0],
                {
                    "name": "submit_design",
                    "description": (
                        "Submit the complete mutation-design object exactly once "
                        "when source inspection is complete."
                    ),
                    "input_schema": submission_schema,
                },
            ]
            self.tool_choice = {"type": "any"}
        # Typed source inspection records a missing or invalid provider route as a
        # typed terminal transport failure on the first request instead of at startup.
        self.transport: ProviderTransport | None = None
        self.transport_failure_kind: str | None = None
        try:
            self.transport = ProviderTransport.for_agent("anthropic", model)
        except ProviderError:
            if not self.typed_source_inspection:
                raise
            self.transport_failure_kind = "no_credentials"
        except ValueError:
            if not self.typed_source_inspection:
                raise
            self.transport_failure_kind = "credential_resolution_error"
        self.endpoint = self.transport.endpoint if self.transport is not None else ""

    def _request_payload(
        self,
        messages: list[dict[str, Any]],
        request_number: int | None = None,
    ) -> dict[str, Any]:
        tools = self.tools
        tool_choice = self.tool_choice
        maximum_tokens = 16_384
        if self.typed_source_inspection:
            if request_number is None or not 1 <= request_number <= 40:
                raise ValueError("typed requests require a request number from 1 through 40")
            maximum_tokens = 32_768
            if request_number >= 38:
                tools = [self.submit_design_tool]
                tool_choice = {
                    "type": "tool",
                    "name": "submit_design",
                    "disable_parallel_tool_use": True,
                }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "max_tokens": maximum_tokens,
        }
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return payload

    def create(
        self,
        messages: list[dict[str, Any]],
        request_number: int | None = None,
    ) -> dict[str, Any]:
        payload = self._request_payload(messages, request_number=request_number)
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if self.typed_source_inspection:
            if self.transport is None:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="credential_resolution",
                    dispatch_attempted=False,
                    failure_kind=self.transport_failure_kind or "no_credentials",
                )
            try:
                request_headers = self.transport.headers()
            except Exception:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="request_headers",
                    dispatch_attempted=False,
                    failure_kind="header_error",
                ) from None
            try:
                response = requests.post(
                    self.endpoint,
                    data=body,
                    headers=request_headers,
                    timeout=self.request_timeout_seconds,
                )
            except requests.exceptions.ConnectTimeout:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="dispatch",
                    dispatch_attempted=True,
                    failure_kind="connect_timeout",
                ) from None
            except requests.exceptions.ReadTimeout:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="dispatch",
                    dispatch_attempted=True,
                    failure_kind="read_timeout",
                ) from None
            except requests.exceptions.ProxyError:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="dispatch",
                    dispatch_attempted=True,
                    failure_kind="proxy_error",
                ) from None
            except requests.exceptions.SSLError:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="dispatch",
                    dispatch_attempted=True,
                    failure_kind="tls_error",
                ) from None
            except requests.exceptions.ConnectionError:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="dispatch",
                    dispatch_attempted=True,
                    failure_kind="connection_error",
                ) from None
            except Exception:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="dispatch",
                    dispatch_attempted=True,
                    failure_kind="unknown_transport",
                ) from None
            try:
                status = getattr(response, "status_code", None)
            except Exception:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="response_status",
                    dispatch_attempted=True,
                    failure_kind="unknown_transport",
                ) from None
            if type(status) is not int or not 100 <= status <= 599:
                status = None
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="response_status",
                    dispatch_attempted=True,
                    failure_kind="http_status",
                    http_status=status,
                ) from None
            except Exception:
                raise TypedTerminalProvider(
                    "transport_failure",
                    transport_stage="response_status",
                    dispatch_attempted=True,
                    failure_kind="unknown_transport",
                ) from None
            try:
                decoded = response.json()
            except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
                raise TypedTerminalProvider(
                    "response_decode_failure",
                    transport_stage="response_decode",
                    dispatch_attempted=True,
                    failure_kind="response_decode_error",
                ) from None
            except Exception:
                raise TypedTerminalProvider(
                    "response_decode_failure",
                    transport_stage="response_decode",
                    dispatch_attempted=True,
                    failure_kind="response_decode_error",
                ) from None
            if not isinstance(decoded, dict):
                raise TypedTerminalProvider(
                    "response_decode_failure",
                    transport_stage="response_decode",
                    dispatch_attempted=True,
                    failure_kind="response_decode_error",
                )
            return decoded
        last_error: Exception | None = None
        for attempt in range(self.request_attempts):
            try:
                response = requests.post(
                    self.endpoint,
                    data=body,
                    headers=self.transport.headers(),
                    timeout=self.request_timeout_seconds,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise RuntimeError(f"retryable provider HTTP {response.status_code}: {_trim(response.text, 2000)}")
                response.raise_for_status()
                return response.json()
            except (requests.exceptions.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt == self.request_attempts - 1:
                    break
                time.sleep(min(2**attempt, 30))
        raise RuntimeError(f"provider request failed after retries: {last_error}")


class AnthropicAgent:
    def __init__(
        self,
        client: MessagesClient,
        workspace: Path,
        rollout_dir: Path,
        prompt: str,
        max_turns: int,
        structured_submission: StructuredSubmissionConfig | None = None,
        typed_source_protocol: TypedSourceProtocolConfig | None = None,
    ) -> None:
        self.client = client
        self.workspace = workspace.resolve()
        self.rollout_dir = rollout_dir.resolve()
        self.max_turns = max_turns
        self.structured_submission = structured_submission
        self.typed_source_protocol = typed_source_protocol
        if structured_submission is not None and typed_source_protocol is not None:
            raise ValueError("structured protocol modes are mutually exclusive")
        self.typed_inspector = (
            TypedSourceInspector(typed_source_protocol)
            if typed_source_protocol is not None
            else None
        )
        self.typed_tool_use_ids: set[str] = set()
        self.shell_commands: list[str] = []
        self.structured_protocol_failed = False
        self.messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        self.trajectory_path = self.rollout_dir / "anthropic-agent-trajectory.jsonl"
        self.final_path = self.rollout_dir / "anthropic_last_message.txt"
        self.rollout_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **data: Any) -> None:
        with self.trajectory_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"timestamp": _now(), "event": event, **data}, sort_keys=True) + "\n")
            if self.typed_source_protocol is not None:
                handle.flush()
                os.fsync(handle.fileno())

    def run(self) -> int:
        if self.typed_source_protocol is not None:
            return self._run_typed_source_protocol()
        self.log("start", requested_model=self.client.model, workspace=str(self.workspace))
        for turn in range(1, self.max_turns + 1):
            response = self.client.create(self._messages_for_request())
            returned_model = str(response.get("model") or "")
            content = response.get("content") or []
            self.messages.append({"role": "assistant", "content": content})
            self.log(
                "assistant",
                turn=turn,
                requested_model=self.client.model,
                returned_model=returned_model,
                stop_reason=response.get("stop_reason"),
                usage=response.get("usage"),
                content=[
                    block if block.get("type") != "thinking" else {"type": "thinking", "omitted": True}
                    for block in content
                ],
            )
            tool_uses = [block for block in content if block.get("type") == "tool_use"]
            text = "\n".join(
                str(block.get("text") or "") for block in content if block.get("type") == "text"
            ).strip()
            if self.structured_submission is not None:
                structured_result = self._handle_structured_turn(turn, tool_uses)
                if structured_result is not None:
                    return structured_result
                continue
            terminal_blocks = [
                block for block in content if block.get("type") in {"refusal", "error"}
            ]
            if terminal_blocks:
                self.log(
                    "provider_terminal",
                    turn=turn,
                    block_types=[str(block.get("type")) for block in terminal_blocks],
                )
                return 4
            if response.get("stop_reason") == "max_tokens" and not tool_uses:
                self.messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Continue from the incomplete response. Use the available tools "
                            "to keep working, or return a final text response only when the "
                            "task is complete."
                        ),
                    }
                )
                self.log("max_tokens_continuation", turn=turn)
                continue
            if not tool_uses:
                self.final_path.write_text(text + "\n", encoding="utf-8")
                self.log("finish", turn=turn, summary=text, explicit=False)
                return 0

            results: list[dict[str, Any]] = []
            should_finish = False
            finish_summary = ""
            for block in tool_uses:
                name = str(block.get("name") or "")
                arguments = block.get("input") or {}
                try:
                    result, image = self._execute_tool(name, arguments)
                    is_error = False
                except Exception as exc:
                    result = f"{type(exc).__name__}: {exc}"
                    image = None
                    is_error = True
                tool_result: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": _trim(result),
                    "is_error": is_error,
                }
                if image is not None:
                    mime_type, encoded, path = image
                    tool_result["content"] = [
                        {"type": "text", "text": f"CUA screenshot from {path}"},
                        {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": encoded,
                                },
                        },
                    ]
                results.append(tool_result)
                self.log("tool", turn=turn, name=name, arguments=arguments, result=_trim(result, 8000))
                if name == "finish" and not is_error:
                    should_finish = True
                    finish_summary = str(arguments.get("summary") or result)
            self.messages.append({"role": "user", "content": results})
            if should_finish:
                self.final_path.write_text(finish_summary + "\n", encoding="utf-8")
                self.log("finish", turn=turn, summary=finish_summary, explicit=True)
                return 0
        self.log("max_turns", max_turns=self.max_turns)
        return 3

    def _typed_validate_provider_response(
        self, response: Any
    ) -> tuple[str, list[dict[str, Any]], str, dict[str, Any]]:
        if not isinstance(response, dict):
            raise TypedTerminalProvider("response_decode_failure")
        try:
            json.dumps(response, allow_nan=False)
        except (TypeError, ValueError):
            raise TypedTerminalProvider("response_decode_failure") from None
        if response.get("type") == "error":
            error = response.get("error")
            if (
                not isinstance(error, dict)
                or not isinstance(error.get("type"), str)
                or not error.get("type")
                or not isinstance(error.get("message"), str)
                or not error.get("message")
            ):
                raise TypedTerminalProvider("response_decode_failure")
            raise TypedTerminalProvider("provider_terminal_stop")
        required = {"model", "content", "stop_reason", "usage"}
        if not required.issubset(response):
            raise TypedTerminalProvider("response_decode_failure")
        model = response["model"]
        content = response["content"]
        stop_reason = response["stop_reason"]
        usage = response["usage"]
        if (
            not isinstance(model, str)
            or not model
            or not isinstance(content, list)
            or not isinstance(stop_reason, str)
            or not isinstance(usage, dict)
            or not all(isinstance(block, dict) and isinstance(block.get("type"), str) for block in content)
        ):
            raise TypedTerminalProvider("response_decode_failure")
        response_ids: set[str] = set()
        for block in content:
            if block.get("type") != "tool_use":
                continue
            identifier = block.get("id")
            if not isinstance(identifier, str) or not identifier:
                raise TypedTerminalProvider("response_decode_failure")
            if identifier in response_ids or identifier in self.typed_tool_use_ids:
                raise TypedTerminalProvider("response_decode_failure")
            if not isinstance(block.get("name"), str) or "input" not in block:
                raise TypedTerminalProvider("response_decode_failure")
            response_ids.add(identifier)
        self.typed_tool_use_ids.update(response_ids)
        return model, content, stop_reason, usage

    def _typed_feedback_message(
        self,
        *,
        request_number: int,
        tool_uses: list[dict[str, Any]],
        category: str,
        source_inspect_error: bool = False,
        successful_result: str | None = None,
        submission_validation_error: TypedSubmissionValidationError | None = None,
        semantic_validation_error: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        if request_number >= 40:
            return None
        blocks: list[dict[str, Any]] = []
        if successful_result is not None:
            block = tool_uses[0]
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": successful_result,
                    "is_error": False,
                }
            )
        elif tool_uses:
            if source_inspect_error:
                content = TYPED_INSPECTION_ERROR_CONTENT[category]
            elif semantic_validation_error is not None:
                content = _format_typed_semantic_validation_error(
                    semantic_validation_error
                )
            elif submission_validation_error is not None:
                try:
                    content = _format_typed_submission_validation_error(
                        submission_validation_error
                    )
                except Exception:
                    content = TYPED_PROTOCOL_ERROR_CONTENT[category]
            else:
                content = TYPED_PROTOCOL_ERROR_CONTENT[category]
            for block in tool_uses:
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": content,
                        "is_error": True,
                    }
                )
        else:
            blocks.append(
                {
                    "type": "text",
                    "text": TYPED_PROTOCOL_ERROR_CONTENT[category],
                }
            )
        next_request = request_number + 1
        reminder = TYPED_PROTOCOL_REMINDERS.get(next_request)
        if reminder is not None:
            blocks.append({"type": "text", "text": reminder})
        return {"role": "user", "content": blocks}

    def _typed_append_feedback(self, message: dict[str, Any] | None) -> None:
        if message is not None:
            self.messages.append(message)

    def _validate_typed_submission_local(
        self, value: Any, schema_path: tuple[str, ...] = ()
    ) -> None:
        if isinstance(value, dict):
            for name, child in value.items():
                self._validate_typed_submission_local(child, schema_path + (name,))
            return
        if isinstance(value, list):
            if len(value) > 8:
                raise TypedSubmissionValidationError(
                    "local_max_items",
                    schema_path,
                    category="submission_constant_or_local_bound_invalid",
                    message="array local bound",
                )
            for child in value:
                self._validate_typed_submission_local(child, schema_path + ("*",))
            return
        if isinstance(value, str):
            if not 1 <= len(value) <= 1024 or len(value.encode("utf-8")) > 2048:
                raise TypedSubmissionValidationError(
                    "local_string_bound",
                    schema_path,
                    category="submission_constant_or_local_bound_invalid",
                    message="string local bound",
                )
            if schema_path in TYPED_IDENTIFIER_PATH_SCHEMA_PATHS and (
                len(value) > 256 or len(value.encode("utf-8")) > 512
            ):
                raise TypedSubmissionValidationError(
                    "local_identifier_bound",
                    schema_path,
                    category="submission_constant_or_local_bound_invalid",
                    message="identifier local bound",
                )

    def _typed_submission_result(
        self, arguments: Any
    ) -> tuple[
        str | None,
        bytes | None,
        TypedSubmissionValidationError | None,
    ]:
        if not isinstance(arguments, dict):
            return (
                "submission_schema_invalid",
                None,
                TypedSubmissionValidationError("type_mismatch", ()),
            )
        try:
            canonical_input = json.dumps(
                arguments,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            return "submission_schema_invalid", None, None
        if len(canonical_input) > TYPED_PROTOCOL_MAX_SUBMISSION_BYTES:
            return "submission_too_large", None, None
        try:
            _validate_typed_submission_instance(
                arguments, self.typed_source_protocol.schema
            )
        except TypedSubmissionValidationError as exc:
            return exc.category, None, exc
        except Exception:
            return "submission_schema_invalid", None, None
        try:
            self._validate_typed_submission_local(arguments)
        except TypedSubmissionValidationError as exc:
            return exc.category, None, exc
        except (UnicodeEncodeError, ValueError):
            return "submission_constant_or_local_bound_invalid", None, None
        canonical = canonical_input + b"\n"
        if len(canonical) > TYPED_PROTOCOL_MAX_SUBMISSION_BYTES:
            return "submission_too_large", None, None
        return None, canonical, None

    def _typed_submission_category(self, arguments: Any) -> tuple[str | None, bytes | None]:
        category, canonical, _ = self._typed_submission_result(arguments)
        return category, canonical

    def _run_typed_source_protocol(self) -> int:
        config = self.typed_source_protocol
        inspector = self.typed_inspector
        if config is None or inspector is None:
            raise RuntimeError("typed protocol is not configured")
        if self.max_turns != 40:
            raise ValueError("typed source protocol requires exactly 40 turns")
        self.log(
            "start",
            requested_model=self.client.model,
            workspace=str(self.workspace),
            mode="typed_source_inspection",
            proposal_sha256=TYPED_PROTOCOL_PROPOSAL_SHA256,
        )
        for request_number in range(1, 41):
            try:
                response = self.client.create(
                    self._messages_for_request(), request_number=request_number
                )
                returned_model, content, stop_reason, usage = self._typed_validate_provider_response(
                    response
                )
                requested_model = self.client.model
                if returned_model not in {
                    requested_model,
                    requested_model.removeprefix("anthropic."),
                }:
                    raise TypedTerminalProvider("response_decode_failure")
            except TypedTerminalProvider as exc:
                fields: dict[str, Any] = {
                    "request": request_number,
                    "category": exc.category,
                }
                if exc.transport_telemetry is not None:
                    fields.update(exc.transport_telemetry)
                self.log("typed_terminal", **fields)
                return 5
            except Exception:
                self.log("typed_terminal", request=request_number, category="transport_failure")
                return 5
            self.messages.append({"role": "assistant", "content": content})
            self.log(
                "assistant",
                turn=request_number,
                requested_model=self.client.model,
                returned_model=returned_model,
                stop_reason=stop_reason,
                usage=usage,
                content=[
                    block if block.get("type") != "thinking" else {"type": "thinking", "omitted": True}
                    for block in content
                ],
            )
            tool_uses = [block for block in content if block.get("type") == "tool_use"]
            if any(block.get("type") in {"refusal", "error"} for block in content):
                self.log("typed_terminal", request=request_number, category="provider_terminal_stop")
                return 5
            if stop_reason not in {"tool_use", "end_turn", "max_tokens"}:
                self.log("typed_terminal", request=request_number, category="provider_terminal_stop")
                return 5
            if stop_reason == "max_tokens":
                message = self._typed_feedback_message(
                    request_number=request_number,
                    tool_uses=tool_uses,
                    category="provider_truncated_submission",
                )
                self._typed_append_feedback(message)
                continue
            exact_shape = len(content) == 1 and len(tool_uses) == 1
            if stop_reason == "end_turn" or not exact_shape:
                category = (
                    "multiple_tool_calls_rejected"
                    if len(tool_uses) > 1
                    else "protocol_shape_error"
                )
                self.log("protocol_rejection", turn=request_number, category=category)
                message = self._typed_feedback_message(
                    request_number=request_number,
                    tool_uses=tool_uses,
                    category=category,
                )
                self._typed_append_feedback(message)
                continue
            block = tool_uses[0]
            name = block["name"]
            arguments = block["input"]
            if name == "source_inspect" and request_number <= 37:
                try:
                    result = inspector.inspect(arguments)
                except TypedRecoverableInspection as exc:
                    self.log(
                        "tool",
                        turn=request_number,
                        name=name,
                        arguments=arguments,
                        result=exc.category,
                    )
                    message = self._typed_feedback_message(
                        request_number=request_number,
                        tool_uses=tool_uses,
                        category=exc.category,
                        source_inspect_error=True,
                    )
                    self._typed_append_feedback(message)
                    continue
                except TypedCustodyFailure as exc:
                    self.log("typed_custody_failure", turn=request_number, category=str(exc))
                    return 4
                self.log(
                    "tool",
                    turn=request_number,
                    name=name,
                    arguments=arguments,
                    result=result,
                )
                message = self._typed_feedback_message(
                    request_number=request_number,
                    tool_uses=tool_uses,
                    category="protocol_shape_error",
                    successful_result=result,
                )
                self._typed_append_feedback(message)
                continue
            if name != "submit_design":
                self.log("protocol_rejection", turn=request_number, category="wrong_tool")
                message = self._typed_feedback_message(
                    request_number=request_number,
                    tool_uses=tool_uses,
                    category="wrong_tool",
                )
                self._typed_append_feedback(message)
                continue
            category, canonical, submission_validation_error = (
                self._typed_submission_result(arguments)
            )
            if category is not None or canonical is None:
                self.log(
                    "tool",
                    turn=request_number,
                    name=name,
                    arguments=arguments,
                    result=category,
                )
                message = self._typed_feedback_message(
                    request_number=request_number,
                    tool_uses=tool_uses,
                    category=category or "submission_schema_invalid",
                    submission_validation_error=submission_validation_error,
                )
                self._typed_append_feedback(message)
                continue
            semantic_validation_error: dict[str, str] | None = None
            if config.semantic_validator_bytes is not None:
                try:
                    semantic_validation_error = _run_typed_semantic_validator(
                        config.semantic_validator_bytes,
                        canonical,
                    )
                except TypedCustodyFailure as exc:
                    self.log(
                        "typed_custody_failure",
                        turn=request_number,
                        category=str(exc),
                    )
                    return 4
            if semantic_validation_error is not None:
                safe_result = {
                    key: value
                    for key, value in semantic_validation_error.items()
                    if key != "status"
                }
                self.log(
                    "tool",
                    turn=request_number,
                    name=name,
                    arguments=arguments,
                    result="submission_semantic_invalid",
                    semantic_error=safe_result,
                )
                message = self._typed_feedback_message(
                    request_number=request_number,
                    tool_uses=tool_uses,
                    category="submission_semantic_invalid",
                    semantic_validation_error=semantic_validation_error,
                )
                self._typed_append_feedback(message)
                continue
            try:
                warnings = _publish_typed_candidate(config, canonical, audit_log=self.log)
            except TypedCustodyFailure as exc:
                self.log("typed_custody_failure", turn=request_number, category=str(exc))
                return 4
            self.log(
                "finish",
                turn=request_number,
                explicit=True,
                mode="typed_source_inspection",
                candidate_output=str(config.candidate_output),
                warnings=list(warnings),
            )
            return 0
        self.log("max_turns", max_turns=40, category="turn_limit_without_submission")
        return 3

    def _handle_structured_turn(
        self,
        turn: int,
        tool_uses: list[dict[str, Any]],
    ) -> int | None:
        if not tool_uses:
            self.log("protocol_rejection", turn=turn, category="natural_text_without_tool")
            self.messages.append({"role": "user", "content": STRUCTURED_SUBMISSION_ERROR})
            return None

        submission_calls = [
            block for block in tool_uses if str(block.get("name") or "") == "submit_design"
        ]
        if submission_calls:
            if len(tool_uses) != 1 or len(submission_calls) != 1:
                self.structured_protocol_failed = True
                results = []
                for block in tool_uses:
                    name = str(block.get("name") or "")
                    arguments = block.get("input") or {}
                    self.log(
                        "tool",
                        turn=turn,
                        name=name,
                        arguments=arguments,
                        result="rejected_mixed_or_duplicate_submission",
                    )
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.get("id"),
                            "content": STRUCTURED_SUBMISSION_ERROR,
                            "is_error": True,
                        }
                    )
                self.messages.append({"role": "user", "content": results})
                return None

            block = submission_calls[0]
            arguments = block.get("input")
            try:
                if not isinstance(arguments, dict):
                    raise ValueError("submission tool input must be an object")
                _validate_instance(arguments, self.structured_submission.schema)
            except ValueError:
                self.log(
                    "tool",
                    turn=turn,
                    name="submit_design",
                    arguments=arguments,
                    result="rejected_schema_validation",
                )
                self.messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": block.get("id"),
                                "content": STRUCTURED_SUBMISSION_ERROR,
                                "is_error": True,
                            }
                        ],
                    }
                )
                return None

            try:
                self._publish_structured_submission(arguments)
            except Exception as exc:
                self.log(
                    "structured_submission_failure",
                    turn=turn,
                    category=type(exc).__name__,
                )
                return 4
            self.log(
                "tool",
                turn=turn,
                name="submit_design",
                arguments=arguments,
                result="accepted_structured_submission",
            )
            self.log(
                "finish",
                turn=turn,
                explicit=True,
                mode="structured_submission",
                schema_sha256=self.structured_submission.schema_sha256,
                candidate_output=str(self.structured_submission.candidate_output),
            )
            return 0

        results: list[dict[str, Any]] = []
        for block in tool_uses:
            name = str(block.get("name") or "")
            arguments = block.get("input") or {}
            if name != "shell":
                self.structured_protocol_failed = True
            try:
                result, image = self._execute_tool(name, arguments)
                if image is not None:
                    raise ValueError("images are unavailable in structured submission mode")
                is_error = False
            except Exception as exc:
                result = f"{type(exc).__name__}: {exc}"
                is_error = True
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": _trim(result),
                    "is_error": is_error,
                }
            )
            self.log("tool", turn=turn, name=name, arguments=arguments, result=_trim(result, 8000))
        self.messages.append({"role": "user", "content": results})
        return None

    def _publish_structured_submission(self, submission: dict[str, Any]) -> None:
        config = self.structured_submission
        if config is None:
            raise RuntimeError("structured submission is not configured")
        if self.structured_protocol_failed:
            raise RuntimeError("structured trajectory contains a protocol or command-audit failure")
        for command in self.shell_commands:
            _audit_read_only_command(command)
        if _source_manifest(self.workspace) != config.source_manifest:
            raise RuntimeError("source manifest changed during the structured trajectory")
        payload = (
            json.dumps(submission, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        _publish_no_replace(config.candidate_output, payload)

    def _messages_for_request(self) -> list[dict[str, Any]]:
        image_locations: list[tuple[int, int]] = []
        for message_index, message in enumerate(self.messages):
            if not isinstance(message.get("content"), list):
                continue
            for block_index, block in enumerate(message["content"]):
                if block.get("type") == "image":
                    image_locations.append((message_index, block_index))
        keep = set(image_locations[-4:])
        compacted = json.loads(json.dumps(self.messages))
        for message_index, block_index in image_locations:
            if (message_index, block_index) not in keep:
                compacted[message_index]["content"][block_index] = {
                    "type": "text",
                    "text": "[Older CUA screenshot omitted from context.]",
                }
        return compacted

    def _execute_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[str, tuple[str, str, str] | None]:
        if name == "shell":
            command = str(arguments.get("command") or "")
            if not command:
                raise ValueError("shell command must not be empty")
            if self.structured_submission is not None:
                self.shell_commands.append(command)
                try:
                    _audit_read_only_command(command)
                except ValueError:
                    self.structured_protocol_failed = True
                    raise
            timeout = min(max(int(arguments.get("timeout_sec", 120)), 1), 180)
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.workspace,
                    shell=True,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
                output = "\n".join(
                    [
                        f"exit_code: {completed.returncode}",
                        f"stdout:\n{completed.stdout}",
                        f"stderr:\n{completed.stderr}",
                    ]
                )
            except subprocess.TimeoutExpired as exc:
                output = "\n".join(
                    [
                        "exit_code: 124",
                        f"stdout:\n{exc.stdout or ''}",
                        f"stderr:\n{exc.stderr or ''}",
                        f"command timed out after {timeout} seconds",
                    ]
                )
            return _trim(output), None

        if name == "view_image":
            if self.client.code_only:
                raise ValueError("view_image is unavailable in the code-only condition")
            raw_path = Path(str(arguments.get("path") or "")).expanduser()
            path = raw_path if raw_path.is_absolute() else self.workspace / raw_path
            path = path.resolve()
            if not any(path.is_relative_to(root) for root in (self.workspace, self.rollout_dir)):
                raise ValueError("image path must be inside the workspace or rollout directory")
            if not path.is_file():
                raise ValueError(f"image does not exist: {path}")
            if path.stat().st_size > 5_000_000:
                raise ValueError("image exceeds the rollout image-size limit")
            mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"Attached screenshot {path}", (mime_type, encoded, str(path))

        if name == "finish":
            return str(arguments.get("summary") or "Finished."), None

        raise ValueError(f"unknown tool: {name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Claude model through the Messages API as a CUA agent")
    parser.add_argument("--model", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--rollout-dir", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-turns", type=int, default=100)
    parser.add_argument("--request-timeout-seconds", type=int, default=300)
    parser.add_argument("--request-attempts", type=int, default=10)
    parser.add_argument("--code-only", action="store_true")
    parser.add_argument(
        "--disable-finish-tool",
        action="store_true",
        help=(
            "Do not advertise the finish tool. The run completes only when the "
            "model returns an ordinary assistant-text response."
        ),
    )
    parser.add_argument("--submission-schema", type=Path)
    parser.add_argument("--expected-submission-schema-sha256")
    parser.add_argument("--candidate-output", type=Path)
    parser.add_argument("--source-manifest-before", type=Path)
    parser.add_argument("--expected-source-manifest-sha256")
    parser.add_argument(
        "--typed-source-inspection",
        action="store_true",
        help="Opt in to the reviewed iteration-02 typed source-inspection protocol.",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--expected-prompt-sha256")
    parser.add_argument("--expected-runner-sha256")
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--expected-source-archive-sha256")
    parser.add_argument("--protocol-proposal-03", type=Path)
    parser.add_argument("--expected-protocol-proposal-03-sha256")
    parser.add_argument("--protocol-proposal-04", type=Path)
    parser.add_argument("--expected-protocol-proposal-04-sha256")
    parser.add_argument("--protocol-proposal-05", type=Path)
    parser.add_argument("--expected-protocol-proposal-05-sha256")
    parser.add_argument("--implementation-review", type=Path)
    parser.add_argument("--expected-implementation-review-sha256")
    parser.add_argument("--typed-semantic-validator", type=Path)
    parser.add_argument("--expected-typed-semantic-validator-sha256")
    return parser.parse_args()


def _durably_log_typed_startup_recovery(
    rollout_dir: Path,
    config: TypedSourceProtocolConfig,
) -> None:
    if config.startup_outcome not in {"aborted_pre_commit", "candidate_already_committed"}:
        raise TypedCustodyFailure("startup_recovery_log_invariant")
    rollout = rollout_dir.absolute()
    try:
        if rollout.is_symlink():
            raise TypedCustodyFailure("startup_recovery_log_ambiguous")
        if not rollout.exists():
            rollout.mkdir()
            _fsync_directory(rollout.parent)
        if not rollout.is_dir():
            raise TypedCustodyFailure("startup_recovery_log_ambiguous")
        path = rollout / "anthropic-agent-trajectory.jsonl"
        payload = (
            json.dumps(
                {
                    "timestamp": _now(),
                    "event": "typed_startup_recovery",
                    "outcome": config.startup_outcome,
                    "warnings": list(config.startup_warnings),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            written = 0
            while written < len(payload):
                count = os.write(descriptor, payload[written:])
                if count <= 0:
                    raise TypedCustodyFailure("startup_recovery_log_short_write")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(rollout)
    except TypedCustodyFailure:
        raise
    except OSError as exc:
        raise TypedCustodyFailure("startup_recovery_log_failure") from exc


def main() -> int:
    args = parse_args()
    if getattr(args, "typed_source_inspection", False):
        typed_config = _prepare_typed_source_protocol(args)
        if typed_config.startup_outcome in {
            "aborted_pre_commit",
            "candidate_already_committed",
        }:
            _durably_log_typed_startup_recovery(args.rollout_dir, typed_config)
        if typed_config.startup_outcome == "candidate_already_committed":
            return 0
        return AnthropicAgent(
            client=MessagesClient(
                args.model,
                code_only=True,
                typed_submission_schema=typed_config.schema,
                request_timeout_seconds=getattr(args, "request_timeout_seconds", 300),
                request_attempts=getattr(args, "request_attempts", 10),
            ),
            workspace=args.workspace,
            rollout_dir=args.rollout_dir,
            prompt=args.prompt,
            max_turns=args.max_turns,
            typed_source_protocol=typed_config,
        ).run()
    structured_submission = _prepare_structured_submission(args)
    return AnthropicAgent(
        client=MessagesClient(
            args.model,
            code_only=args.code_only,
            allow_finish=not args.disable_finish_tool and structured_submission is None,
            submission_schema=(
                structured_submission.schema if structured_submission is not None else None
            ),
            request_timeout_seconds=getattr(args, "request_timeout_seconds", 300),
            request_attempts=getattr(args, "request_attempts", 10),
        ),
        workspace=args.workspace,
        rollout_dir=args.rollout_dir,
        prompt=args.prompt,
        max_turns=args.max_turns,
        structured_submission=structured_submission,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
