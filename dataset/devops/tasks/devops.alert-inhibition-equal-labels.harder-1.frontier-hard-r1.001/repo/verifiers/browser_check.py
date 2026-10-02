#!/usr/bin/env python3
"""Protected behavioral verifier for the Sentinel inhibition task."""

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


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def wait_for(url, timeout=25):
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


def fetch_json(url):
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def start_runtime(profile):
    service_port, app_port = free_port(), free_port()
    service = subprocess.Popen(
        [
            NODE,
            str(VERIFIER_ROOT / "inhibition_service.mjs"),
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


def stop(processes):
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()


def check(condition, label, checks, failed):
    checks.append(label)
    if not condition:
        failed.append(label)


def source_shortcuts():
    forbidden = re.compile(
        r"v-node-west|h-source-cobalt|visible-initial|hidden-initial|"
        r"BillingQueueStuck|SettlementJobsStuck|LedgerReplayLag|"
        r"CacheEvictionsStalled|expectedSignature|"
        r"inhibition_service|profiles\.json"
    )
    return [
        str(path.relative_to(WORKSPACE))
        for path in sorted((WORKSPACE / "src").rglob("*.js"))
        if forbidden.search(path.read_text(encoding="utf-8"))
    ]


def inspect_incident(page, service_origin, profile, number, checks, failed):
    audit = fetch_json(f"{service_origin}/audit")
    actual = audit["actual"]
    check(
        audit["actualSignature"] == audit["expectedSignature"],
        f"{profile}: incident {number} exact protected inhibition matches",
        checks,
        failed,
    )
    check(
        len(actual["alerts"]) == audit["protectedAlertCount"],
        f"{profile}: incident {number} preserves every protected alert",
        checks,
        failed,
    )
    check(
        len(actual["suppressed"]) == audit["protectedSuppressedCount"],
        f"{profile}: incident {number} protected suppression count matches",
        checks,
        failed,
    )
    check(
        all(alert["scopeState"] == "present" for alert in actual["suppressed"]),
        f"{profile}: incident {number} no unscoped alert is held",
        checks,
        failed,
    )
    check(
        all(edge["sourceId"] and edge["targetId"] for edge in actual["edges"]),
        f"{profile}: incident {number} every suppression has a protected edge",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="firing"] .alert-card').count()
        == len(actual["firing"])
        and page.locator('[data-test="suppressed"] .alert-card').count()
        == len(actual["suppressed"]),
        f"{profile}: incident {number} queue surfaces are complete",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="graph"] .edge').count() == len(actual["edges"])
        and page.locator('[data-test="comparisons"] .comparison').count()
        == len(actual["comparisons"]),
        f"{profile}: incident {number} diagnostic surfaces are complete",
        checks,
        failed,
    )
    return audit


def run_profile(browser, profile, checks, failed):
    processes, app_origin, service_origin = start_runtime(profile)
    try:
        page = browser.new_page(viewport={"width": 1420, "height": 980})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(app_origin, wait_until="domcontentloaded")
        page.locator('#app[data-ready="yes"]').wait_for(timeout=20000)
        catalog = fetch_json(f"{service_origin}/catalog")
        registry_text = page.locator('[data-test="dimensions"]').inner_text().lower()
        check(
            page.locator('[data-test="dimensions"] .dimension').count()
            == len(catalog["dimensions"])
            and all(
                dimension["name"].lower() in registry_text
                and dimension["role"].lower() in registry_text
                and dimension["note"].lower() in registry_text
                for dimension in catalog["dimensions"]
            ),
            f"{profile}: scope-dimension registry surface is complete",
            checks,
            failed,
        )
        advisory_text = page.locator('[data-test="advisories"]').inner_text()
        check(
            page.locator('[data-test="advisories"] .advisory').count()
            == len(catalog["advisories"])
            and all(advisory in advisory_text for advisory in catalog["advisories"]),
            f"{profile}: incident advisory surface is complete",
            checks,
            failed,
        )
        first = inspect_incident(page, service_origin, profile, 1, checks, failed)
        prior = page.locator('[data-test="incident"]').inner_text()
        page.locator('[data-test="advance"]').click()
        page.wait_for_function(
            """prior => {
              const label=document.querySelector('[data-test="incident"]');
              const button=document.querySelector('[data-test="advance"]');
              return label && label.textContent !== prior && button && button.disabled;
            }""",
            arg=prior,
            timeout=10000,
        )
        second = inspect_incident(page, service_origin, profile, 2, checks, failed)
        check(
            second["incidentIndex"] == 1 and second["advanceCount"] == 1,
            f"{profile}: browser reached the arriving-alert incident",
            checks,
            failed,
        )
        check(
            first["actualSignature"] != second["actualSignature"],
            f"{profile}: arriving batch changes protected state",
            checks,
            failed,
        )
        try:
            urlopen(f"{app_origin}/api/audit", timeout=5)
            hidden = False
        except HTTPError as error:
            hidden = error.code == 404
        check(hidden, f"{profile}: protected audit is not exposed", checks, failed)
        check(not page_errors, f"{profile}: no page errors", checks, failed)
        page.close()
    finally:
        stop(processes)


def main():
    checks, failed = [], []
    try:
        check(
            not source_shortcuts(),
            "agent-visible source contains no protected alert literals",
            checks,
            failed,
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                run_profile(browser, "visible", checks, failed)
                run_profile(browser, "hidden", checks, failed)
            finally:
                browser.close()
    except Exception as error:
        failed.append(f"verifier infrastructure: {type(error).__name__}: {error}")
    result = {"passed": not failed, "failed_checks": failed, "checks": checks}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
