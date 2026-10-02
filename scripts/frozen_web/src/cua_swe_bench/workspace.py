from __future__ import annotations

import shutil
import shlex
from dataclasses import dataclass
from pathlib import Path

from cua_swe_bench.commands import CommandResult, run_command
from cua_swe_bench.schema import RepoSnapshot


class WorkspaceError(RuntimeError):
    pass


def _raise_for_failed_command(result: CommandResult, context: str) -> None:
    if result.ok:
        return
    raise WorkspaceError(
        "\n".join(
            [
                context,
                f"command: {result.command}",
                f"exit_code: {result.exit_code}",
                f"stdout: {result.stdout}",
                f"stderr: {result.stderr}",
            ]
        )
    )


def _run_git_or_raise(command: str, cwd: Path) -> None:
    result = run_command(command, cwd=cwd, timeout_sec=30)
    _raise_for_failed_command(result, "Workspace git setup command failed")


@dataclass(frozen=True)
class Workspace:
    task_id: str
    path: Path

    def diff(self) -> str:
        result = run_command("git diff --no-ext-diff", cwd=self.path, timeout_sec=30)
        _raise_for_failed_command(result, "Workspace diff command failed")
        parts = [result.stdout]
        parts.extend(self._untracked_file_diffs())
        return "\n".join(part for part in parts if part)

    def _untracked_file_diffs(self) -> list[str]:
        result = run_command("git ls-files --others --exclude-standard", cwd=self.path, timeout_sec=30)
        _raise_for_failed_command(result, "Workspace untracked file listing failed")

        diffs: list[str] = []
        for rel_path in result.stdout.splitlines():
            if not rel_path:
                continue
            diff_result = run_command(
                f"git diff --no-ext-diff --no-index -- /dev/null {shlex.quote(rel_path)}",
                cwd=self.path,
                timeout_sec=30,
            )
            if diff_result.exit_code == 0:
                continue
            if diff_result.exit_code != 1:
                _raise_for_failed_command(diff_result, "Workspace untracked file diff command failed")
            diffs.append(diff_result.stdout)
        return diffs


class WorkspaceManager:
    def __init__(self, runs_root: Path | str) -> None:
        self.runs_root = Path(runs_root).expanduser().resolve()
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def prepare(self, task_id: str, snapshot: RepoSnapshot) -> Workspace:
        if snapshot.source == "mobilegym_overlay":
            return self._prepare_mobilegym_overlay(task_id, snapshot)
        if snapshot.source != "local":
            raise NotImplementedError("vertical slice supports local and mobilegym_overlay repo snapshots only")
        if snapshot.path is None:
            raise ValueError("local repo snapshot path is required")

        safe_task_id = task_id.replace("/", "_")
        target = self.runs_root / safe_task_id / "workspace"
        if target.exists():
            shutil.rmtree(target)
        if snapshot.copy_mode == "exact":
            shutil.copytree(
                snapshot.path,
                target,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git"),
            )
        else:
            shutil.copytree(
                snapshot.path,
                target,
                ignore=shutil.ignore_patterns(".git", "node_modules", "dist", "verifier-artifacts"),
            )

        _run_git_or_raise("git init", cwd=target)
        _run_git_or_raise("git add .", cwd=target)
        _run_git_or_raise(
            "git -c user.name=cua-swe -c user.email=cua-swe@example.invalid commit -m baseline",
            cwd=target,
        )
        return Workspace(task_id=task_id, path=target)

    def _prepare_mobilegym_overlay(self, task_id: str, snapshot: RepoSnapshot) -> Workspace:
        if snapshot.path is None:
            raise ValueError("mobilegym_overlay repo snapshot path is required")

        source = Path(snapshot.path).expanduser()
        if not source.is_absolute():
            source = Path.cwd() / source
        source = source.resolve()
        if not source.exists():
            raise WorkspaceError(f"missing MobileGym overlay source: {source}")

        safe_task_id = task_id.replace("/", "_")
        target = self.runs_root / safe_task_id / "workspace"
        if target.exists():
            shutil.rmtree(target)

        if (source / ".git").exists():
            _run_git_or_raise(
                f"git clone --local --no-hardlinks {shlex.quote(str(source))} {shlex.quote(str(target))}",
                cwd=self.runs_root,
            )
            if snapshot.ref and snapshot.ref not in {"seed", "head", "HEAD", "upstream"}:
                _run_git_or_raise(f"git checkout {shlex.quote(snapshot.ref)}", cwd=target)
        else:
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "node_modules", "dist"))
            _run_git_or_raise("git init", cwd=target)
            _run_git_or_raise("git add .", cwd=target)
            _run_git_or_raise(
                "git -c user.name=cua-swe -c user.email=cua-swe@example.invalid commit -m upstream",
                cwd=target,
            )

        if snapshot.overlay_patch:
            patch_path = Path(snapshot.overlay_patch).expanduser()
            if not patch_path.is_absolute():
                patch_path = Path.cwd() / patch_path
            patch_path = patch_path.resolve()
            if not patch_path.exists():
                raise WorkspaceError(f"missing MobileGym overlay patch: {patch_path}")
            _run_git_or_raise(f"git apply --whitespace=nowarn {shlex.quote(str(patch_path))}", cwd=target)
            self._commit_all_if_needed(target, "cua-swe mobilegym overlay baseline")

        if snapshot.link_node_modules:
            source_node_modules = source / "node_modules"
            target_node_modules = target / "node_modules"
            if source_node_modules.exists() and not target_node_modules.exists():
                target_node_modules.symlink_to(source_node_modules, target_is_directory=True)

        return Workspace(task_id=task_id, path=target)

    def _commit_all_if_needed(self, target: Path, message: str) -> None:
        _run_git_or_raise("git add .", cwd=target)
        diff_result = run_command("git diff --cached --quiet", cwd=target, timeout_sec=30)
        if diff_result.exit_code == 0:
            return
        if diff_result.exit_code != 1:
            _raise_for_failed_command(diff_result, "Workspace git diff command failed")
        _run_git_or_raise(
            f"git -c user.name=cua-swe -c user.email=cua-swe@example.invalid commit -m {shlex.quote(message)}",
            cwd=target,
        )
