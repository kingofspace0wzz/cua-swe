#!/usr/bin/env python3
"""Protected behavioral verifier for the reset-lineage late-arrival counter query-order task."""

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
        r"service_stream_total|panel_counter_total|ledger_stream_total|"
        r"target_stream_total|archive_stream_total|lateFlush"
    )
    return [
        str(path.relative_to(WORKSPACE))
        for path in sorted((WORKSPACE / "src").rglob("*.js"))
        if forbidden.search(path.read_text(encoding="utf-8"))
    ]


def choose(page, selector, index, observed_selector):
    prior = page.locator(observed_selector).text_content()
    page.locator(selector).nth(index).click()
    page.wait_for_function(
        """({selector, prior}) => {
          const node = document.querySelector(selector);
          return node && node.textContent !== prior;
        }""",
        arg={"selector": observed_selector, "prior": prior},
        timeout=10000,
    )


def inspect(page, service_origin, profile, window_number, scenario_number, panel_number, checks, failed):
    audit = fetch_json(f"{service_origin}/audit")
    expected = audit["expected"]
    where = f"{profile}: window {window_number} scenario {scenario_number} panel {panel_number}"
    check(
        audit["actualSignature"] == audit["expectedSignature"],
        f"{where} protected query semantics match",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="window"]').text_content() == expected["window"]["label"],
        f"{where} visible window label matches",
        checks,
        failed,
    )
    points = page.locator('[data-test="chart"] .point')
    check(
        points.count() == audit["protectedPointCount"],
        f"{where} preserves every point",
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
        f"{where} point identities and rates match",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="peak"]').inner_text() == expected["summary"]["peak"]
        and page.locator('[data-test="total"]').inner_text() == expected["summary"]["total"],
        f"{where} summary matches",
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
        f"{where} visible sample times match",
        checks,
        failed,
    )
    expected_markers = [[item["id"], item["time"], item["label"]] for item in expected["markers"]]
    check(
        actual_markers == expected_markers,
        f"{where} markers match",
        checks,
        failed,
    )
    targets = page.locator('[data-test="targets"] .target-row')
    actual_targets = [
        [
            targets.nth(index).get_attribute("data-target-id"),
            *[targets.nth(index).locator("td").nth(column).inner_text() for column in range(5)],
        ]
        for index in range(targets.count())
    ]
    expected_targets = [
        [
            item["id"],
            item["label"],
            str(item["resetCount"]),
            item["lastReset"],
            item["state"],
            item["publication"],
        ]
        for item in expected["targets"]
    ]
    check(
        actual_targets == expected_targets,
        f"{where} target reset and publication evidence matches",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="range"]').inner_text() == expected["diagnostics"]["range"]
        and int(page.locator('[data-test="series-count"]').inner_text())
        == expected["diagnostics"]["seriesCount"],
        f"{where} diagnostics match",
        checks,
        failed,
    )
    check(
        page.locator('[data-test="scenario-controls"] .control').count()
        == audit["protectedScenarioCount"]
        and page.locator('[data-test="panel-controls"] .control').count()
        == audit["protectedPanelCount"]
        and page.locator('[data-test="window-controls"] .control').count()
        == audit["protectedWindowCount"]
        and targets.count() == audit["protectedTargetCount"],
        f"{where} inventories remain complete",
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
        page.wait_for_function(
            "document.querySelector('#app') && document.querySelector('#app').dataset.ready !== 'no'",
            timeout=20000,
        )
        configured = page.locator("#app").get_attribute("data-ready") == "yes"
        check(configured, f"{profile}: console configures against the deployed windows", checks, failed)
        if not configured:
            page.close()
            return
        complete_controls = (
            page.locator('[data-test="scenario-controls"] .control').count() == 3
            and page.locator('[data-test="panel-controls"] .control').count() == 3
            and page.locator('[data-test="window-controls"] .control').count() == 2
        )
        check(
            complete_controls,
            f"{profile}: initial scenario, panel, and window controls remain complete",
            checks,
            failed,
        )
        if not complete_controls:
            page.close()
            return
        catalog = fetch_json(f"{service_origin}/catalog")
        definitions = catalog["definitions"]
        record_visible = page.locator('[data-test="collection-panel"]').is_visible()
        check(record_visible, f"{profile}: collection record observable", checks, failed)
        if record_visible:
            entries = page.locator('[data-test="collection"] .collection-window')
            check(
                entries.count() == len(catalog["windows"]),
                f"{profile}: collection record covers every window",
                checks,
                failed,
            )
            for index, window in enumerate(catalog["windows"]):
                entry = entries.nth(index)
                transition = window.get("transition")
                transition_ok = (
                    entry.locator(".collection-transition").count() == 0
                    if not transition
                    else entry.locator(".collection-transition").inner_text()
                    == f"{transition['time']}s \u00b7 {transition['label']}"
                )
                check(
                    entry.get_attribute("data-window-id") == window["id"]
                    and entry.locator("strong").inner_text() == window["label"]
                    and entry.locator(".collection-note").inner_text() == window["note"]
                    and transition_ok,
                    f"{profile}: collection record window {index + 1} matches the deployment",
                    checks,
                    failed,
                )
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
                and card.locator(".definition-labels").inner_text() == f"Input labels: {definition['inputLabels']} \u2192 Output labels: {definition['outputLabels']}",
                f"{profile}: definition {index + 1} expression and ingestion lineage match deployment", checks, failed)
        page.locator('[data-test="definitions-panel"] summary').click()
        signatures = {}
        for window_index in range(2):
            if window_index:
                choose(
                    page,
                    '[data-test="window-controls"] .control',
                    window_index,
                    '[data-test="window"]',
                )
            for scenario_index in range(3):
                if page.locator('[data-test="scenario"]').text_content() != page.locator(
                    '[data-test="scenario-controls"] .control'
                ).nth(scenario_index).text_content():
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
                    signatures[(window_index, scenario_index, panel_index)] = inspect(
                        page,
                        service_origin,
                        profile,
                        window_index + 1,
                        scenario_index + 1,
                        panel_index + 1,
                        checks,
                        failed,
                    )
        choose(page, '[data-test="window-controls"] .control', 0, '[data-test="window"]')
        returned = inspect(page, service_origin, profile, 1, 3, 3, checks, failed)
        check(
            returned == signatures[(0, 2, 2)],
            f"{profile}: returning to the earlier window reproduces the exact paired state",
            checks,
            failed,
        )
        final = fetch_json(f"{service_origin}/audit")
        check(
            final["scenarioSelectCount"] == 5
            and final["panelSelectCount"] >= 16
            and final["windowSelectCount"] == 2,
            f"{profile}: every window, scenario, and panel was exercised",
            checks,
            failed,
        )
        check(
            len(set(signatures.values())) == 18,
            f"{profile}: every window, scenario, and panel has a distinct signature",
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
