#!/usr/bin/env python3
"""Review candidate only. Delegate the pinned harness; retain already-owned data.

No CLI additions, extraction reruns, verifier wrapper, or score/result mutation.
Only three module bindings change, once before the original worker pool starts.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import hashlib
import importlib
import json
import os
from pathlib import Path
import stat
import sys

VERSION = "pre-verifier-retention-modifier-click-04"
BASE = Path(__file__).resolve().parent / "scripts/run_clean_ablation.py"
BASE_ENTRYPOINT_SHA256 = "50e9e63fe4d87833285df2f604926535609ed26b91ad6adac87be59fb23c3a74"
BASE_HARNESS_SHA256 = "b7f6364d8ce364bf5cb04b502943f4283de8defc2a392cfbd38d2f3a7517f51d"
ARTIFACT_DIR = "pre-verifier-retention-01"
CUSTODY_FIELDS = (
    "task_file_sha256", "task_input_sha256", "instruction_sha256",
    "source_only_sha256", "copied_source_only_sha256", "verifier_sha256",
    "runtime_contract_sha256", "harness_sha256", "source_symlinks",
)
SOURCE_FIELDS = (
    "post_common_setup_source_sha256", "pre_agent_source_sha256", "source_excludes",
    "pre_agent_source_excludes", "pre_agent_root_identities",
    "post_agent_root_identities", "protected_root_identities_unchanged",
)


class RetentionError(RuntimeError):
    """Handled by the frozen run_trial's infrastructure-error exception path."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extension_metadata() -> dict:
    return {
        "revision": VERSION,
        "extension_path": str(Path(__file__).absolute()),
        "extension_sha256": sha(Path(__file__).read_bytes()),
        "base_entrypoint_sha256": BASE_ENTRYPOINT_SHA256,
        "base_harness_sha256": BASE_HARNESS_SHA256,
        "digest_scope": "BASE harness only; extension_sha256 is separate, not an effective-code digest",
    }


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _open_directory(path: Path) -> int:
    """Walk an existing trusted output path without following any symlinks."""
    path = path.absolute()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            if part in (".", ".."):
                raise ValueError("noncanonical output path")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_json(fd: int, name: str) -> dict:
    # Only two named harness-owned metadata files, never workspace/audit/rollout.
    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(file_fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("custody metadata is not a regular file")
        return json.load(handle)


def _publish(fd: int, name: str, data: bytes) -> None:
    """Commit a new file only: sync bytes, publish without clobber, sync directory.

    A killed/failed writer may leave .partial files; they are never commitments.
    The extraction JSON is published only after patch.diff has been committed.
    """
    temporary = name + ".partial"
    file_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
    with os.fdopen(file_fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
    os.unlink(temporary, dir_fd=fd)
    os.fsync(fd)


@dataclass
class _TrialState:
    trial: object
    run_root: Path
    fd: int | None = None
    workspace: Path | None = None
    binding: dict | None = None
    digest_count: int = 0
    failure: str | None = None


_CURRENT: ContextVar[_TrialState | None] = ContextVar("retention_trial", default=None)


def _fail(state: _TrialState, phase: str, exc: Exception):
    state.failure = f"artifact retention failed [{phase}] for {state.trial.key}: {type(exc).__name__}: {exc}"
    # Also visible in the controller log if the original trial.json write fails.
    try:
        print("RetentionError: " + state.failure, file=sys.stderr, flush=True)
    finally:
        raise RetentionError(state.failure) from exc


def _retain_extracted(state, patch, containment, workspace, isolated_root, metadata):
    trial = state.trial
    components = (trial.condition, trial.model.key, trial.task_id, f"attempt-{trial.attempt}")
    if any(not c or c in (".", "..") or "/" in c or "\\" in c for c in components):
        raise ValueError("unsafe trial path component")
    trial_dir = state.run_root.absolute() / "trials" / Path(*components)
    if trial_dir.is_relative_to(isolated_root.absolute()):
        raise ValueError("retention destination is inside the agent sandbox")
    parent = _open_directory(trial_dir)
    try:
        row = _read_json(parent, "trial.json")
        attestation = _read_json(parent, "isolation_attestation.json")
        expected = {
            "ordinal": trial.ordinal, "key": trial.key, "task_id": trial.task_id,
            "attempt": trial.attempt, "condition": trial.condition,
            "observation_mode": trial.observation_mode, "port": trial.port,
            "task_digest": trial.task_digest,
        }
        if any(row["trial"].get(k) != v for k, v in expected.items()):
            raise ValueError("trial custody identity mismatch")
        if row["model"]["key"] != trial.model.key:
            raise ValueError("model custody identity mismatch")
        custody = {k: row.get("input_custody", {})[k]
                   for k in CUSTODY_FIELDS if k in row.get("input_custody", {})}
        if (custody.get("task_input_sha256") != trial.task_digest
                or custody.get("harness_sha256") != BASE_HARNESS_SHA256):
            raise ValueError("input/BASE harness custody mismatch")
        os.mkdir(ARTIFACT_DIR, mode=0o700, dir_fd=parent)  # existing attempt is never overwritten
        os.fsync(parent)
        state.fd = os.open(ARTIFACT_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                           dir_fd=parent)
    finally:
        os.close(parent)
    data = patch.encode("utf-8")  # exact returned str; no strip, joins, newline translation
    _publish(state.fd, "patch.diff", data)
    receipt = {
        "schema": 1, "phase": "extracted_before_protocol_and_verifier",
        "extension": metadata, "trial": row["trial"], "model_key": trial.model.key,
        "run_root": str(state.run_root.absolute()), "trial_dir": str(trial_dir),
        "scheduled_task_file": str(trial.task_file),
        "input_custody": custody,
        "input_custody_harness_sha256_scope": "BASE",
        "source_baseline": {k: attestation[k] for k in SOURCE_FIELDS if k in attestation},
        "patch_containment": containment,
        "patch": {"file": "patch.diff", "sha256": sha(data), "bytes": len(data),
                  "representation": "UTF-8 encoding of exact extracted str, not raw subprocess bytes"},
    }
    encoded = _json_bytes(receipt)
    _publish(state.fd, "extracted.json", encoded)
    state.binding = {"extracted_json_sha256": sha(encoded), "patch_sha256": sha(data),
                     "trial_key": trial.key, "task_input_sha256": trial.task_digest}
    state.workspace = workspace


def install(harness) -> dict:
    """Install once, before scheduling. Never install/uninstall per worker."""
    if (Path(harness.__file__).absolute() != BASE
            or sha(BASE.read_bytes()) != BASE_ENTRYPOINT_SHA256
            or harness._evaluation_harness_digest() != BASE_HARNESS_SHA256):
        raise RuntimeError("pinned BASE harness mismatch")
    if getattr(harness, "_retention_extension_installed", False):
        raise RuntimeError("retention extension already installed")
    metadata = extension_metadata()
    original_trial = harness.run_trial
    original_extract = harness._extract_agent_patch_contained
    original_digest = harness._tree_digest

    @wraps(original_trial)
    def run_trial(trial, run_root, python_bin, max_agent_tokens=200_000):
        state = _TrialState(trial, run_root)
        token = _CURRENT.set(state)
        try:
            result = original_trial(trial, run_root, python_bin, max_agent_tokens)
            if state.failure and not (result.get("infrastructure_error") is True
                                      and result.get("scorable") is False):
                raise RetentionError(state.failure)  # never invent a product result
            return result
        finally:
            _CURRENT.reset(token)
            if state.fd is not None:
                os.close(state.fd)

    @wraps(original_extract)
    def extract(workspace, python_bin, *, profile, isolated_root, timeout_sec):
        result = original_extract(workspace, python_bin, profile=profile,
                                  isolated_root=isolated_root, timeout_sec=timeout_sec)
        state = _CURRENT.get()
        if state is not None:
            try:
                if state.fd is not None:
                    raise ValueError("duplicate extraction in one trial")
                _retain_extracted(state, result[0], result[1], workspace, isolated_root, metadata)
            except Exception as exc:
                _fail(state, "extracted", exc)
        return result  # same object, patch and containment, not reconstructed

    @wraps(original_digest)
    def tree_digest(root, *, excludes, root_only_excludes=False):
        result = original_digest(root, excludes=excludes, root_only_excludes=root_only_excludes)
        state = _CURRENT.get()
        # In the pinned run_trial exactly two such calls follow extraction:
        # before fresh runtime start, and after start (both BEFORE verifier).
        # No new scan; out-of-trial, baseline and unrelated digests are untouched.
        if (state is not None and state.workspace == root and state.binding is not None
                and excludes == harness.PRE_AGENT_SOURCE_EXCLUDES and not root_only_excludes
                and state.digest_count < 2):
            phase = ("pre-evaluation-source", "post-evaluation-start-source")[state.digest_count]
            try:
                _publish(state.fd, phase + ".json", _json_bytes({
                    "schema": 1, "phase": phase, **state.binding,
                    "source_sha256": result, "excludes": sorted(excludes),
                    "algorithm": "BASE _tree_digest; file bytes and symlink identity",
                    "root_only_excludes": False,
                }))
                state.digest_count += 1
            except Exception as exc:
                _fail(state, phase, exc)
        return result

    harness.run_trial = run_trial
    harness._extract_agent_patch_contained = extract
    harness._tree_digest = tree_digest
    harness._retention_extension_installed = True
    return metadata


def main() -> int:
    # Preserve the frozen module's __file__/REPO_ROOT and sibling imports.
    sys.path.insert(0, str(BASE.parent))
    harness = importlib.import_module("run_clean_ablation")
    install(harness)
    return harness.main()  # original CLI, host lock, scheduling and exit behavior


if __name__ == "__main__":
    raise SystemExit(main())
