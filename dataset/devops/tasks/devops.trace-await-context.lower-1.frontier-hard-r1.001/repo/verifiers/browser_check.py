#!/usr/bin/env python3
"""Protected behavioral verifier for the Continuum async-context task."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


VERIFIER_ROOT = Path(
    os.environ.get("CUA_SWE_VERIFIER_ROOT") or Path(__file__).resolve().parent
)
WORKSPACE = Path(os.environ.get("CUA_SWE_WORKSPACE") or Path.cwd()).resolve()
NODE = os.environ.get("CUA_SWE_NODE") or "node"


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def wait_for(url: str, timeout: float = 25) -> None:
    deadline = time.time() + timeout
    error = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, OSError) as exc:
            error = exc
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {url}: {error}")


def fetch_json(url: str) -> dict:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def start_runtime(profile: str):
    service_port, app_port = free_port(), free_port()
    service = subprocess.Popen(
        [
            NODE,
            str(VERIFIER_ROOT / "context_service.mjs"),
            "--host",
            "127.0.0.1",
            "--port",
            str(service_port),
            "--profile",
            profile,
        ],
        cwd=str(VERIFIER_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    service_origin = f"http://127.0.0.1:{service_port}"
    wait_for(f"{service_origin}/health")

    environment = dict(os.environ)
    environment["CUA_SWE_EXTERNAL_SERVICE_ORIGIN"] = service_origin
    app = subprocess.Popen(
        [NODE, "server.mjs", "--host", "127.0.0.1", "--port", str(app_port)],
        cwd=str(WORKSPACE),
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    app_origin = f"http://127.0.0.1:{app_port}"
    wait_for(app_origin)
    return [app, service], app_origin, service_origin


def stop(processes) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()


def check(condition, label: str, checks: list[str], failed: list[str]) -> None:
    checks.append(label)
    if not condition:
        failed.append(label)


def source_shortcuts() -> list[str]:
    forbidden = re.compile(
        r"visible-sequential|hidden-sequential|visible-overlap|hidden-overlap|"
        r"store-sequential|store-overlap|continuation-store|"
        r"vseq-root|hseq-root|sseq-root|refresh-service|reconcile-ledger|"
        r"compact-exports|compact-tenant|"
        r"expectedParentId|expectedSignature|context_service|profiles\.json"
    )
    offenders = []
    for path in sorted((WORKSPACE / "src").rglob("*.js")):
        if forbidden.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(WORKSPACE)))
    return offenders


def descends_from(span_by_id: dict[str, dict], span: dict, root_id: str) -> bool:
    visited = set()
    current = span
    while current and current["id"] not in visited:
        if current["id"] == root_id:
            return True
        visited.add(current["id"])
        parent_id = current.get("parentId")
        current = span_by_id.get(parent_id) if parent_id else None
    return False


def integer_text(page, selector: str) -> int:
    return int(page.locator(selector).inner_text().strip())


def inspect_scenario(
    page,
    service_origin: str,
    profile: str,
    scenario_number: int,
    checks: list[str],
    failed: list[str],
) -> dict:
    audit = fetch_json(f"{service_origin}/audit")
    actual = audit["actual"]
    spans = actual["spans"]
    span_by_id = {span["id"]: span for span in spans}

    check(
        audit["actualSignature"] == audit["expectedSignature"],
        f"{profile}: scenario {scenario_number} exact protected ancestry matches",
        checks,
        failed,
    )
    check(
        len(actual["operations"]) == audit["protectedOperationCount"],
        f"{profile}: scenario {scenario_number} preserves every operation",
        checks,
        failed,
    )
    check(
        len(spans) == audit["protectedSpanCount"],
        f"{profile}: scenario {scenario_number} preserves every span",
        checks,
        failed,
    )

    roots_are_exact = True
    ancestry_is_exact = True
    for operation in actual["operations"]:
        owned = [span for span in spans if span["operationId"] == operation["id"]]
        roots = [span for span in owned if span["parentId"] is None]
        roots_are_exact &= (
            len(roots) == 1
            and roots[0]["id"] == operation["rootId"]
            and roots[0]["kind"] == "operation"
        )
        ancestry_is_exact &= all(
            descends_from(span_by_id, span, operation["rootId"]) for span in owned
        )
    check(
        roots_are_exact,
        f"{profile}: scenario {scenario_number} has exactly one root per operation",
        checks,
        failed,
    )
    check(
        ancestry_is_exact,
        f"{profile}: scenario {scenario_number} spans descend from their own root",
        checks,
        failed,
    )

    automatic = [span for span in spans if span["kind"].startswith("auto-")]
    check(
        len(automatic) == audit["protectedAutomaticCount"]
        and len({span["kind"] for span in automatic}) >= 2,
        f"{profile}: scenario {scenario_number} keeps protected automatic coverage",
        checks,
        failed,
    )
    check(
        all(item["status"] == "preserved" for item in actual["transitions"]),
        f"{profile}: scenario {scenario_number} preserves every async transition",
        checks,
        failed,
    )

    if len(actual["operations"]) > 1:
        operation_traces = [operation["traceId"] for operation in actual["operations"]]
        check(
            len(operation_traces) == len(set(operation_traces)),
            f"{profile}: overlapping operations use distinct traces",
            checks,
            failed,
        )
        cross_parent = any(
            span["parentId"]
            and span_by_id[span["parentId"]]["operationId"] != span["operationId"]
            for span in spans
        )
        check(
            not cross_parent,
            f"{profile}: overlapping operations have no cross-parentage",
            checks,
            failed,
        )

    check(
        integer_text(page, '[data-test="operation-count"]') == len(actual["operations"]),
        f"{profile}: scenario {scenario_number} operation summary is complete",
        checks,
        failed,
    )
    check(
        integer_text(page, '[data-test="trace-count"]') == len(actual["traces"]),
        f"{profile}: scenario {scenario_number} trace summary is complete",
        checks,
        failed,
    )
    check(
        integer_text(page, '[data-test="span-count"]') == len(spans)
        and page.locator('[data-test="spans"] .span-card').count() == len(spans)
        and page.locator('[data-test="waterfall"] .span-row').count() == len(spans),
        f"{profile}: scenario {scenario_number} span surfaces are complete",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="transitions"] li').count()
        == len(actual["transitions"]),
        f"{profile}: scenario {scenario_number} transition surface is complete",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="instrumentation"] .instrument-card').count()
        == len(actual["instrumentation"]),
        f"{profile}: scenario {scenario_number} instrumentation surface is complete",
        checks,
        failed,
    )
    return audit


def run_profile(browser, profile: str, checks: list[str], failed: list[str]) -> None:
    processes, app_origin, service_origin = start_runtime(profile)
    try:
        page = browser.new_page(viewport={"width": 1420, "height": 980})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(app_origin, wait_until="domcontentloaded")
        page.locator('#app[data-ready="yes"]').wait_for(timeout=20000)

        first = inspect_scenario(page, service_origin, profile, 1, checks, failed)
        prior_label = page.locator('[data-test="scenario"]').inner_text()
        page.locator('[data-test="advance"]').click()
        page.wait_for_function(
            """prior => {
              const label = document.querySelector('[data-test="scenario"]');
              const button = document.querySelector('[data-test="advance"]');
              return label && label.textContent !== prior && button && button.disabled;
            }""",
            arg=prior_label,
            timeout=10000,
        )
        second = inspect_scenario(page, service_origin, profile, 2, checks, failed)
        check(
            second["scenarioIndex"] == 1 and second["advanceCount"] == 1,
            f"{profile}: browser reached the protected overlapping scenario",
            checks,
            failed,
        )
        check(
            first["actualSignature"] != second["actualSignature"],
            f"{profile}: scenario transition changes protected topology",
            checks,
            failed,
        )

        try:
            urlopen(f"{app_origin}/api/audit", timeout=5)
            audit_hidden = False
        except HTTPError as error:
            audit_hidden = error.code == 404
        check(
            audit_hidden,
            f"{profile}: protected audit is not exposed by the host",
            checks,
            failed,
        )
        check(not page_errors, f"{profile}: no page errors", checks, failed)
        page.close()
    finally:
        stop(processes)


def main() -> int:
    checks: list[str] = []
    failed: list[str] = []
    try:
        check(
            not source_shortcuts(),
            "agent-visible source contains no protected schedule or ancestry literals",
            checks,
            failed,
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                run_profile(browser, "visible", checks, failed)
                run_profile(browser, "hidden", checks, failed)
                run_profile(browser, "hidden-store", checks, failed)
            finally:
                browser.close()
    except Exception as error:
        failed.append(f"verifier infrastructure: {type(error).__name__}: {error}")

    result = {"passed": not failed, "failed_checks": failed, "checks": checks}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
