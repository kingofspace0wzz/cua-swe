from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _output_to_text(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return output


def run_command(command: str, cwd: Path, timeout_sec: int) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _output_to_text(exc.stdout)
        stderr = _output_to_text(exc.stderr)
        timeout_message = f"Command timed out after {timeout_sec} seconds"
        if stderr:
            stderr = f"{stderr}\n{timeout_message}"
        else:
            stderr = timeout_message
        return CommandResult(
            command=command,
            exit_code=124,
            stdout=stdout,
            stderr=stderr,
        )
    return CommandResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


class RunningCommand:
    def __init__(self, command: str, cwd: Path) -> None:
        self.command = command
        self.cwd = cwd
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self._result: CommandResult | None = None

    def result_if_exited(self) -> CommandResult | None:
        if self._result is not None:
            return self._result
        exit_code = self.process.poll()
        if exit_code is None:
            return None
        stdout, stderr = self.process.communicate()
        self._result = CommandResult(
            command=self.command,
            exit_code=exit_code,
            stdout=_output_to_text(stdout),
            stderr=_output_to_text(stderr),
        )
        return self._result

    def stop(self, timeout_sec: int = 5) -> CommandResult:
        existing = self.result_if_exited()
        if existing is not None:
            return existing

        self._terminate()
        try:
            stdout, stderr = self.process.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired as exc:
            self._kill()
            stdout, stderr = self.process.communicate()
            timeout_message = f"Long-running command did not stop after {timeout_sec} seconds"
            stderr_text = _output_to_text(exc.stderr) or _output_to_text(stderr)
            if stderr_text:
                stderr_text = f"{stderr_text}\n{timeout_message}"
            else:
                stderr_text = timeout_message
            self._result = CommandResult(
                command=self.command,
                exit_code=self.process.returncode if self.process.returncode is not None else -9,
                stdout=_output_to_text(exc.stdout) or _output_to_text(stdout),
                stderr=stderr_text,
            )
            return self._result

        self._result = CommandResult(
            command=self.command,
            exit_code=self.process.returncode if self.process.returncode is not None else -15,
            stdout=_output_to_text(stdout),
            stderr=_output_to_text(stderr),
        )
        return self._result

    def _terminate(self) -> None:
        if self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except (AttributeError, ProcessLookupError):
            self.process.terminate()

    def _kill(self) -> None:
        if self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except (AttributeError, ProcessLookupError):
            self.process.kill()


def start_command(command: str, cwd: Path) -> RunningCommand:
    return RunningCommand(command=command, cwd=cwd)
