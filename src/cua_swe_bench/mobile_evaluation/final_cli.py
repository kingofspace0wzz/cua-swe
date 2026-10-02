"""Real native CLI adapter used by the protected Mobile evaluator."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile
import time

from cua_swe_bench.mobile_evaluation import admission, runner
from cua_swe_bench.mobile_evaluation.agent import Agent, BROWSER
from cua_swe_bench.mobile_evaluation.core import Fault, Protocol, evidence, sha, write_json
from cua_swe_bench.mobile_evaluation.sandbox import SAFE_ENV
from .cli_bridge_host import CapabilityBroker, image_records
from .cli_pixels import CliPixels
from .cli_transport import Budget, OwnedStreamingTransport, ROUTES, TransportStop

from .settings import TOOLCHAIN, CATALOG, PYTHON
MODULES = (
    "final_cli.py", "cli_session_worker.py", "cli_commands.py",
    "cli_bridge_client.py", "cli_bridge_host.py", "cli_pixels.py",
    "cli_transport.py", "cli_provider_worker.py",
)


def protocol_class(route_id):
    if route_id not in ROUTES:
        raise Fault("configuration", "undeclared native CLI route")
    route = ROUTES[route_id]
    selected_id = route_id

    @dataclass(frozen=True)
    class CliProtocol(Protocol):
        name: str = "mobile-final-native-cli-v1"
        model: str = route["returned_model"]
        provider: str = route["provider"]
        reasoning: str = "adaptive/high" if route["kind"] == "messages" else "high"
        route_id: str = selected_id

        def record(self):
            return {
                **super().record(), "request_model": route["request_model"],
                "native_cli": "Codex0.155.1" if selected_id == "codex-sol" else "ClaudeCode2.1.278",
                "adapter_sources": {n: evidence(Path(__file__).with_name(n)) for n in MODULES},
                "cli_manifest": evidence(TOOLCHAIN / "source-manifest.json"),
                "sol_metadata_catalog": evidence(CATALOG),
                "client_sha256": sha(Path(__file__).with_name("cli_provider_worker.py")),
                "evidence_format": "native-cli-stream-receipts-v1",
            }
    return CliProtocol


def verify_installation():
    manifest_path = TOOLCHAIN / "source-manifest.json"
    if sha(manifest_path) != "22def400a5c066e502e51f18bf6f085cb50e9ca3166ecf90b7de036c732b5aeb":
        raise Fault("configuration", "CLI installation manifest changed")
    if sha(CATALOG) != "f6d9b14876ed864941d2f8acf9dd6a9d060f766786973f0e1d47040f451ab8fb":
        raise Fault("configuration", "Sol native metadata changed")
    dependencies = TOOLCHAIN / "dependencies"
    files, links = {}, {}
    for path in dependencies.rglob("*"):
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(dependencies):
                raise Fault("configuration", "CLI package link leaves its declared installation")
            links[str(path.relative_to(dependencies))] = os.readlink(path)
        elif path.is_file():
            files[str(path.relative_to(dependencies))] = sha(path)
    if files != json.loads(manifest_path.read_text()):
        raise Fault("configuration", "CLI installation files changed")
    return {"manifest": evidence(manifest_path), "files_verified": len(files), "links": links,
            "sol_catalog": evidence(CATALOG)}


def cli_transport_not_api(*args, **kwargs):
    raise Fault("configuration", "native CLI transport cannot be used as a direct API agent")


class CliAgent(Agent):
    route_id = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.condition != "cua":
            raise Fault("configuration", "final native CLI rows are CUA conditions only")
        self.protocol = protocol_class(self.route_id)()
        self.transport = self.pixels = self.broker = None
        self.stop_at = None

    def worker_argv(self):
        """A test subclass may supply a deterministic offline provider worker."""
        return [PYTHON, "-I",
                str(Path(__file__).with_name("cli_provider_worker.py"))]

    def run(self):
        start = time.monotonic()
        try:
            self._execute(start)
        except (Fault, TransportStop) as error:
            self.state["faults"].append({"category": error.category, "message": str(error)})
            self.state["termination"] = error.category
        except Exception as error:
            self.state["faults"].append({"category": "harness", "message": repr(error)})
            self.state["termination"] = "harness"
        finally:
            # _execute closes the broker and drains all accepted callbacks.
            self.stop_at = self.stop_at or time.monotonic()
            self.state["active_seconds"] = self.stop_at - start
            self.state["cleanup_seconds"] = max(0, time.monotonic() - self.stop_at)
            write_json(self.root / "agent.json", self.state)
        return self.state

    def _prompt(self):
        path = self.sandbox.workspace / "TASK.md"
        if sha(path) != self.task.c["instruction"]["sha256"]:
            raise Fault("missing_instruction", "delivered instruction differs from frozen task")
        prompt = (
            "Repair the application described below. Public instruction is /workspace/TASK.md. "
            "Ordinary source, dependencies, and nonvisual builds/tests are available. Modify only: "
            + json.dumps(self.task.c["editable"]) + ". "
            "Use your ordinary native file and shell tools. Use only the mobile browser pixel/action "
            "tool for runtime observation. Submit by ending your response after saving the changes. "
            "Budget: 60 model responses, 45 minutes active time, at most16384 output tokens per response.\n\n"
            + path.read_text()
            + "\n\nTop-level public source paths: "
            + ", ".join(sorted({name.split("/")[0] for name in self.baseline})) + "."
        )
        write_json(self.root / "prompt.json", {
            "prompt": prompt, "instruction_sha256": sha(path), "native_cli": self.route_id,
        })
        return prompt

    def _send_startup(self, process, raw, budget):
        os.set_blocking(process.stdin.fileno(), False)
        view = memoryview(raw)
        while view:
            if budget.remaining() <= 0:
                budget.latch("time_cap", "active CLI deadline during startup")
                raise TransportStop("time_cap", "active CLI deadline during startup")
            _, ready, _ = select.select([], [process.stdin], [], min(.1, budget.remaining()))
            if ready:
                try:
                    view = view[os.write(process.stdin.fileno(), view[:65536]):]
                except BlockingIOError:
                    continue
        process.stdin.close()

    def _execute(self, start):
        installation = verify_installation()
        write_json(self.root / "installation.json", installation)
        prompt = self._prompt()
        budget = Budget(self.protocol.responses, self.protocol.active_seconds, started=start)
        self.transport = OwnedStreamingTransport(
            self.route_id, self.root / "transport", budget, self.worker_argv())
        self.pixels = CliPixels(self.task, self.baseline, self.sandbox.workspace, self.runtime, self.root / "pixels")
        (self.root / "cli-home").mkdir()
        process = None
        observed_exit = False
        with tempfile.TemporaryDirectory(prefix="mobile-cli-", dir="/tmp") as temporary:
            socket_path = Path(temporary) / "cap.sock"
            browser_tool = {"name": "browser", "description": BROWSER["description"],
                            "inputSchema": BROWSER["parameters"]}
            self.broker = CapabilityBroker(socket_path, self.root / "broker", self.transport, browser_tool, self.pixels)
            module_root = Path(__file__).parent
            mounts = [
                (TOOLCHAIN / "dependencies", "/cli", False),
                (module_root / "cli_session_worker.py", "/bridge/session.py", False),
                (module_root / "cli_bridge_client.py", "/bridge/client.py", False),
                (module_root / "cli_commands.py", "/bridge/commands.py", False),
                (CATALOG, "/bridge/model-catalog.json", False),
                (self.root / "cli-home", "/cli-home", True),
                (socket_path, "/cap.sock", False),
            ]
            argv = self.sandbox.argv(["/usr/bin/python3", "-I", "/bridge/session.py"], mounts)
            try:
                with (self.root / "cli.stdout").open("xb") as out, (self.root / "cli.stderr").open("xb") as err:
                    process = subprocess.Popen(
                        argv, stdin=subprocess.PIPE, stdout=out, stderr=err,
                        env=SAFE_ENV, start_new_session=True,
                    )
                    start_ticks = Path(f"/proc/{process.pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
                    write_json(self.root / "cli-launch.json", {
                        "argv": argv, "pid": process.pid, "process_start_ticks": start_ticks,
                        "started_monotonic": start, "native_cli": self.route_id,
                    })
                    self._send_startup(process, json.dumps({"route": self.route_id, "prompt": prompt}).encode(), budget)
                    while True:
                        # WNOWAIT keeps the PID owned until its entire process
                        # group is stopped; never signal a potentially reused PID.
                        terminal = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                        if terminal is not None:
                            observed_exit = True
                            break
                        if budget.stop is not None:
                            break
                        if budget.remaining() <= 0:
                            budget.latch("time_cap", "absolute active CLI deadline")
                            break
                        time.sleep(min(.1, max(.001, budget.remaining())))
            finally:
                self.stop_at = time.monotonic()
                if process is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=8)
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                    write_json(self.root / "cli-exit.json", {
                        "pid": process.pid, "returncode": process.returncode,
                        "normal_exit_observed": observed_exit, "reaped": True,
                        "stop": budget.stop, "stopped_monotonic": self.stop_at,
                    })
                # Normal CLI completion may precede host validation of its last
                # streamed receipt. Let accepted requests finish in that case.
                self.broker.close(cancel_transport=not observed_exit or budget.stop is not None)
                self.pixels.close()
                self._collect()
        if budget.stop:
            category, message = budget.stop
            if category in {"time_cap", "response_cap"}:
                self.state["termination"] = category
            else:
                raise TransportStop(category, message)
        elif process is None or process.returncode != 0 or not observed_exit:
            raise Fault("cli_runtime", "native CLI did not complete normally")
        else:
            self.state["termination"] = "submitted"
        if self.state["faults"]:
            self.state["termination"] = self.state["faults"][0]["category"]

    def _collect(self):
        self.state["images_created"] = list(self.pixels.images_created)
        self.state["pixel_actions"] = self.pixels.actions
        self.state["runtime_syncs"] = self.pixels.syncs
        self.state["tool_seconds"] = self.pixels.seconds
        self.state["provider_dispatches"] = self.transport.budget.dispatched
        seen = set()
        for receipt_path in sorted(self.transport.root.glob("*.receipt.json")):
            prefix = receipt_path.name.split(".", 1)[0]
            receipt = json.loads(receipt_path.read_text())
            request_path = self.transport.root / (prefix + ".request.json")
            request = json.loads(request_path.read_text())
            if receipt["id"] in seen:
                raise Fault("provider", "duplicate native CLI provider response identity")
            seen.add(receipt["id"])
            req_ref, res_ref = evidence(request_path), evidence(receipt_path)
            self.state["requests"].append({
                "request": req_ref, "response": res_ref, "response_id": receipt["id"],
                "raw_response": evidence(self.transport.root / (prefix + ".raw")),
            })
            self.state["returned_models"].append(receipt["model"])
            self.state["usage"].append(receipt.get("usage"))
            self.state["responses"] += 1
            for image in image_records(request["sent_body"]):
                previous = [event for event in self.pixels.image_events
                            if event["image"]["sha256"] == image["sha256"]
                            and event["created_monotonic"] <= request["started_monotonic"]]
                if previous:
                    self.state["images_delivered"].append({
                        "image": previous[-1]["image"], "request": req_ref,
                        "response": res_ref, "response_id": receipt["id"],
                    })
        if self.state["responses"] != self.transport.budget.completed:
            raise Fault("provider", "native CLI response accounting differs from receipts")
        self.state["model_seconds"] = sum(
            json.loads(p.read_text())["seconds"] for p in self.transport.root.glob("*.completion.json"))
        for path in self.pixels.root.glob("*.fault.json"):
            self.state["faults"].append(json.loads(path.read_text()))
        if self.transport.processes:
            raise Fault("harness", "provider workers still owned after CLI closure")


@contextmanager
def selected_cli_context(route_id):
    selected = protocol_class(route_id)

    class SelectedAgent(CliAgent):
        pass
    SelectedAgent.route_id = route_id
    old = runner.Protocol, runner.Agent, admission.Protocol
    runner.Protocol, runner.Agent, admission.Protocol = selected, SelectedAgent, selected
    try:
        yield
    finally:
        runner.Protocol, runner.Agent, admission.Protocol = old


def run_cli_attempt(route_id, *args, **kwargs):
    """Final dispatcher must verify the release and this route's preflight."""
    if "client_factory" in kwargs or not kwargs.get("dispatch_approval"):
        raise Fault("configuration", "native CLI requires a reviewed dispatch and fixed transport")
    with selected_cli_context(route_id):
        return runner.run_attempt(*args, client_factory=cli_transport_not_api, **kwargs)
