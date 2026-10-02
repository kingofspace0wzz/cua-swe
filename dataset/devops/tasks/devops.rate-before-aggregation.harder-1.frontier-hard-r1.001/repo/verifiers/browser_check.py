#!/usr/bin/env python3
"""Protected behavioral verifier for the counter query-order task."""

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


VERIFIER_ROOT = Path(os.environ.get("CUA_SWE_VERIFIER_ROOT") or Path(__file__).resolve().parent)
WORKSPACE = Path(os.environ.get("CUA_SWE_WORKSPACE") or Path.cwd()).resolve()
NODE = os.environ.get("CUA_SWE_NODE") or "node"


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return free_port() if port in (51300, 51400) else port


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
            str(VERIFIER_ROOT / "counter_service.mjs"),
            "--host", "127.0.0.1",
            "--port", str(service_port),
            "--profile", profile,
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
        r"checkout-a|checkout-b|router-n7|router-p4|burst-control|"
        r"rolling-restart|restart-in-burst|load-wave|target-recycle|"
        r"counter_service|profiles\\.json|expectedSignature|"
        r"service_stream_total|panel_counter_total|target_stream_total|"
        r"archive_stream_total"
    )
    return [
        str(path.relative_to(WORKSPACE))
        for path in sorted((WORKSPACE / "src").rglob("*.js"))
        if forbidden.search(path.read_text(encoding="utf-8"))
    ]


def choose(page, selector, index, observed_selector):
    prior = page.locator(observed_selector).inner_text()
    page.locator(selector).nth(index).click()
    page.wait_for_function(
        """({selector, prior}) => {
          const node = document.querySelector(selector);
          return node && node.textContent !== prior;
        }""",
        arg={"selector": observed_selector, "prior": prior},
        timeout=10000,
    )


def inspect(page, service_origin, profile, scenario_number, panel_number, checks, failed):
    audit = fetch_json(f"{service_origin}/audit")
    expected = audit["expected"]
    check(
        audit["actualSignature"] == audit["expectedSignature"],
        f"{profile}: scenario {scenario_number} panel {panel_number} protected query semantics match",
        checks,
        failed,
    )
    points = page.locator('[data-test="chart"] .point')
    check(
        points.count() == audit["protectedPointCount"],
        f"{profile}: scenario {scenario_number} panel {panel_number} preserves every point",
        checks,
        failed,
    )
    actual_points = [
        [
            points.nth(index).get_attribute("data-point-id"),
            int(points.nth(index).get_attribute("data-time")),
            float(points.nth(index).get_attribute("data-value")),
        ]
        for index in range(points.count())
    ]
    expected_points = [[item["id"], item["time"], item["value"]] for item in expected["points"]]
    check(
        actual_points == expected_points,
        f"{profile}: scenario {scenario_number} panel {panel_number} point identities and rates match",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="peak"]').inner_text() == expected["summary"]["peak"]
        and page.locator('[data-test="total"]').inner_text() == expected["summary"]["total"],
        f"{profile}: scenario {scenario_number} panel {panel_number} summary matches",
        checks,
        failed,
    )
    markers = page.locator('[data-test="markers"] .marker')
    actual_markers = [
        [
            markers.nth(index).get_attribute("data-marker-id"),
            int(markers.nth(index).get_attribute("data-marker-time")),
            markers.nth(index).locator("span").inner_text(),
        ]
        for index in range(markers.count())
    ]
    check(
        page.locator('[data-test="time-axis"] .time-tick').all_text_contents()
        == [f"{item['time']}s" for item in expected["points"]],
        f"{profile}: scenario {scenario_number} panel {panel_number} visible sample times match",
        checks,
        failed,
    )
    expected_markers = [[item["id"], item["time"], item["label"]] for item in expected["markers"]]
    check(
        actual_markers == expected_markers,
        f"{profile}: scenario {scenario_number} panel {panel_number} markers match",
        checks,
        failed,
    )
    targets = page.locator('[data-test="targets"] .target-row')
    actual_targets = [
        [
            targets.nth(index).get_attribute("data-target-id"),
            *[targets.nth(index).locator("td").nth(column).inner_text() for column in range(4)],
        ]
        for index in range(targets.count())
    ]
    expected_targets = [
        [item["id"], item["label"], str(item["resetCount"]), item["lastReset"], item["state"]]
        for item in expected["targets"]
    ]
    check(
        actual_targets == expected_targets,
        f"{profile}: scenario {scenario_number} panel {panel_number} target reset evidence matches",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="range"]').inner_text() == expected["diagnostics"]["range"]
        and int(page.locator('[data-test="series-count"]').inner_text())
        == expected["diagnostics"]["seriesCount"],
        f"{profile}: scenario {scenario_number} panel {panel_number} diagnostics match",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="scenario-controls"] .control').count()
        == audit["protectedScenarioCount"]
        and page.locator('[data-test="panel-controls"] .control').count()
        == audit["protectedPanelCount"]
        and targets.count() == audit["protectedTargetCount"],
        f"{profile}: scenario {scenario_number} panel {panel_number} inventories remain complete",
        checks,
        failed,
    )
    return audit["expectedSignature"]


def run_profile(browser, profile, checks, failed):
    processes, app_origin, service_origin = start_runtime(profile)
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(app_origin, wait_until="domcontentloaded")
        page.locator('#app[data-ready="yes"]').wait_for(timeout=20000)
        complete_controls = (
            page.locator('[data-test="scenario-controls"] .control').count() == 3
            and page.locator('[data-test="panel-controls"] .control').count() == 3
        )
        check(
            complete_controls,
            f"{profile}: initial scenario and panel controls remain complete",
            checks,
            failed,
        )
        if not complete_controls:
            page.close()
            return
        definitions = fetch_json(f"{service_origin}/catalog")["definitions"]
        definitions_visible = page.locator('[data-test="definitions-panel"]').is_visible()
        check(definitions_visible, f"{profile}: deployed definitions observable", checks, failed)
        if not definitions_visible:
            page.close()
            return
        page.locator('[data-test="definitions-panel"] summary').click()
        cards = page.locator('[data-test="definitions"] .definition-card')
        check(cards.count() == len(definitions), f"{profile}: deployed definitions complete", checks, failed)
        for index, definition in enumerate(definitions):
            card = cards.nth(index)
            check(card.get_attribute("data-definition-id") == definition["id"]
                and card.locator(".definition-step").all_text_contents() == definition["steps"]
                and card.locator(".definition-lineage").all_text_contents() == definition["lineage"]
                and card.locator(".definition-labels").inner_text() == f"Input labels: {definition['inputLabels']} → Output labels: {definition['outputLabels']}",
                f"{profile}: definition {index + 1} expression and upstream lineage match deployment", checks, failed)
        page.locator('[data-test="definitions-panel"] summary').click()
        signatures = []
        for scenario_index in range(3):
            if scenario_index:
                choose(
                    page,
                    '[data-test="scenario-controls"] .control',
                    scenario_index,
                    '[data-test="scenario"]',
                )
            for panel_index in range(3):
                if page.locator('[data-test="panel-title"]').inner_text() != page.locator(
                    '[data-test="panel-controls"] .control'
                ).nth(panel_index).inner_text():
                    choose(
                        page,
                        '[data-test="panel-controls"] .control',
                        panel_index,
                        '[data-test="panel-title"]',
                    )
                signatures.append(
                    inspect(
                        page,
                        service_origin,
                        profile,
                        scenario_index + 1,
                        panel_index + 1,
                        checks,
                        failed,
                    )
                )
        final = fetch_json(f"{service_origin}/audit")
        check(
            final["scenarioSelectCount"] == 2 and final["panelSelectCount"] >= 8,
            f"{profile}: every scenario and panel was exercised",
            checks,
            failed,
        )
        check(
            len(set(signatures)) == 9,
            f"{profile}: every scenario and panel has a distinct signature",
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
            "agent-visible source contains no protected targets schedules or query service",
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
