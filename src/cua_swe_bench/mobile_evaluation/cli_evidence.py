from .settings import PYTHON
"""Audit actual native CLI streams and pixel custody without API-shaped fiction."""
from pathlib import Path
import json
import math

from cua_swe_bench.mobile_evaluation.core import Fault, evidence, verify_ref
from .cli_bridge_host import image_records
from .cli_transport import ROUTES, pinned_request, response_receipt


def require(condition, message):
    if not condition:
        raise Fault("evidence", message)


def read(path):
    return json.loads(Path(path).read_text())


def owned_ref(reference, root):
    require(isinstance(reference, dict) and verify_ref(reference), "missing or changed artifact")
    path = Path(reference["path"])
    require(path.resolve().is_relative_to(Path(root).resolve()) and not path.is_symlink(),
            "artifact outside its owned evidence root")
    return path


def audit_cli_agent(root, runtime_root, protocol, *, test_limits=None):
    """Production requires60/2700/16384; explicit test limits cannot certify a trial."""
    root, runtime_root = Path(root), Path(runtime_root)
    route_id = protocol["route_id"]
    require(route_id in ROUTES, "unknown CLI route")
    route = ROUTES[route_id]
    limits = test_limits or (60, 2700, 16384)
    require((protocol["responses"], protocol["active_seconds"], protocol["max_output_tokens"]) == limits,
            "unrecognized CLI budget")
    require(protocol["model"] == route["returned_model"]
            and protocol["request_model"] == route["request_model"]
            and protocol["provider"] == route["provider"] and protocol["transport_attempts"] == 1,
            "CLI protocol route differs")
    for reference in protocol["adapter_sources"].values():
        require(verify_ref(reference), "CLI adapter source changed")
    require(verify_ref(protocol["cli_manifest"]) and verify_ref(protocol["sol_metadata_catalog"]),
            "CLI installation/catalog identity changed")
    state = read(root / "agent.json")
    launch, exit_record = read(root / "cli-launch.json"), read(root / "cli-exit.json")
    require(launch["native_cli"] == route_id and exit_record["pid"] == launch["pid"]
            and exit_record["reaped"], "CLI ownership/cleanup evidence absent")
    require(state["termination"] in {"submitted", "response_cap", "time_cap"}
            and not state["faults"], "not a healthy scorable CLI terminal outcome")
    started, stopped = launch["started_monotonic"], exit_record["stopped_monotonic"]
    require(all(type(v) in (int, float) and math.isfinite(v) for v in
                (started, stopped, state["active_seconds"], state["cleanup_seconds"])),
            "invalid CLI timing")
    require(started <= stopped and abs(stopped - started - state["active_seconds"]) < .001,
            "CLI active clock differs")
    require(0 <= state["active_seconds"] <= protocol["active_seconds"] + 2,
            "CLI active budget exceeded")
    if state["termination"] == "submitted":
        require(exit_record["normal_exit_observed"] and exit_record["returncode"] == 0
                and exit_record["stop"] is None, "CLI submission lacks normal exit")
    else:
        require(exit_record["stop"] and exit_record["stop"][0] == state["termination"],
                "CLI cap evidence differs")
    if state["termination"] == "time_cap":
        require(state["active_seconds"] >= protocol["active_seconds"] - .1,
                "early stop mislabeled as active deadline")

    requests = sorted((root / "transport").glob("*.request.json"))
    completions = sorted((root / "transport").glob("*.completion.json"))
    require(len(requests) == len(completions) == state["provider_dispatches"],
            "unaccounted native CLI provider dispatch")
    require(0 < state["responses"] <= state["provider_dispatches"] <= protocol["responses"],
            "native CLI response budget accounting differs")
    if state["termination"] == "response_cap":
        require(state["provider_dispatches"] == protocol["responses"], "early response cap")
    require([p.name for p in requests] == [f"{i:03d}.request.json" for i in range(1, len(requests) + 1)],
            "CLI request sequence has gaps")
    rows, returned, usage, seen = [], [], [], set()
    for request_path, completion_path in zip(requests, completions):
        prefix = request_path.name.split(".", 1)[0]
        require(completion_path.name == prefix + ".completion.json", "completion sequence differs")
        request, completion = read(request_path), read(completion_path)
        require(request["route"] == route_id and request["transport_attempts"] == 1,
                "CLI request route/transport count differs")
        if test_limits is None:
            require(request.get("worker_argv") == [
                PYTHON, "-I",
                protocol["adapter_sources"]["cli_provider_worker.py"]["path"]],
                "production CLI did not dispatch its pinned provider worker")
        sent, overrides = pinned_request(route_id, request["path"], request["original_body"])
        require(sent == request["sent_body"] and overrides == request["request_overrides"],
                "native CLI envelope modified beyond declared token limit")
        require(started <= request["started_monotonic"] <= stopped + .01
                and 0 < request["timeout_seconds"] <= 600
                and request["timeout_seconds"] <= started + protocol["active_seconds"] - request["started_monotonic"] + .05,
                "CLI request deadline differs")
        raw_path = root / "transport" / (prefix + ".raw")
        require(evidence(raw_path)["sha256"] == completion["raw_sha256"] and completion["reaped"],
                "raw CLI stream or provider cleanup differs")
        receipt_path = root / "transport" / (prefix + ".receipt.json")
        if not receipt_path.exists():
            require(request_path == requests[-1] and state["termination"] == "time_cap"
                    and completion["error"]["category"] in {"time_cap", "cancelled"}
                    and completion["valid_receipt"] is None,
                    "unexplained provider interruption cannot earn failure credit")
            continue
        require(completion["error"] is None and completion["returncode"] == 0,
                "completed CLI response has a provider error")
        envelope = read(root / "transport" / (prefix + ".envelope.json"))
        require(envelope["transport_attempts"] == 1, "provider envelope transport count differs")
        receipt = response_receipt(route_id, envelope, raw_path.read_bytes())
        require(receipt == read(receipt_path) == completion["valid_receipt"],
                "CLI receipt does not match its original stream")
        require(receipt["id"] not in seen, "duplicate CLI response identity")
        seen.add(receipt["id"])
        receipt_usage = receipt["usage"]
        tokens = receipt_usage["end"]["output_tokens"] if route["kind"] == "messages" else receipt_usage["output_tokens"]
        cap = sent["max_tokens" if route["kind"] == "messages" else "max_output_tokens"]
        require(type(tokens) is int and 0 <= tokens <= cap <= protocol["max_output_tokens"],
                "CLI provider output-token receipt exceeds its cap")
        rows.append({"request": evidence(request_path), "response": evidence(receipt_path),
                     "response_id": receipt["id"], "raw_response": evidence(raw_path)})
        returned.append(receipt["model"])
        usage.append(receipt_usage)
    require(rows == state["requests"] and len(rows) == state["responses"]
            and returned == state["returned_models"] and usage == state["usage"],
            "CLI state differs from original provider streams")

    events = [read(p) for p in sorted((root / "pixels").glob("*.image.json"))]
    require([event["image"] for event in events] == state["images_created"],
            "CLI image creation differs from callback receipts")
    for event in events:
        owned_ref(event["image"], runtime_root)
        require(started <= event["created_monotonic"], "pixel image predates this CLI attempt")
    require(len(list((root / "pixels").glob("*.action.json"))) == state["pixel_actions"]
            and len(list((root / "pixels").glob("*.sync.json"))) == state["runtime_syncs"],
            "CLI pixel action/sync accounting differs")
    deliveries = []
    for row in rows:
        request = read(owned_ref(row["request"], root))
        for image in image_records(request["sent_body"]):
            prior = [event for event in events if event["image"]["sha256"] == image["sha256"]
                     and event["created_monotonic"] <= request["started_monotonic"]]
            if prior:
                deliveries.append({"image": prior[-1]["image"], "request": row["request"],
                                   "response": row["response"], "response_id": row["response_id"]})
    require(deliveries == state["images_delivered"], "CLI screenshot-delivery custody differs")
    return {
        "passed": True, "production_budget": test_limits is None,
        "route": route_id, "responses": len(rows), "provider_dispatches": len(requests),
        "images_created": len(events), "images_delivered": len(deliveries),
        "termination": state["termination"], "active_seconds": state["active_seconds"],
        "agent": evidence(root / "agent.json"), "protocol": protocol,
        "native_stream_receipts_recomputed": True, "exact_image_chronology_verified": True,
        "claimed_scope": "Provider/CLI/pixel evidence only. Task controls, source binding and final native grading must be checked separately.",
    }
