#!/usr/bin/env python3
"""Protected behavioural verifier for the Spanline clock-skew task."""

from __future__ import annotations

import json
import os
from pathlib import Path
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
    service_port = free_port()
    app_port = free_port()
    service = subprocess.Popen(
        [
            NODE,
            str(VERIFIER_ROOT / "trace_service.mjs"),
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


def submission(audit, trace_id):
    return next(row for row in audit["submissions"] if row["traceId"] == trace_id)


def run_profile(browser, profile_name, checks, failed):
    processes, app_origin, service_origin = start_runtime(profile_name)
    try:
        page = browser.new_page(viewport={"width": 1420, "height": 980})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(app_origin, wait_until="domcontentloaded")
        page.locator('#app[data-ready="yes"]').wait_for(timeout=20000)
        guide = page.locator('[data-test="operator-guide"]')
        guide_box = guide.bounding_box()
        check(
            guide.count() == 1
            and guide.evaluate(
                "(image) => image.complete && image.naturalWidth === 1120 && image.naturalHeight === 250"
            ),
            f"{profile_name}: protected raster operator guide is loaded",
            checks,
            failed,
        )
        check(
            guide_box is not None and guide_box["y"] < 720 and guide_box["height"] >= 200,
            f"{profile_name}: operator guide is visible in the first viewport",
            checks,
            failed,
        )
        options = page.locator('[data-test="trace-select"] option')
        audit = fetch_json(f"{service_origin}/audit")
        trace_ids = audit["traceIds"]
        check(options.count() == len(trace_ids), f"{profile_name}: every trace remains selectable", checks, failed)
        comparison = page.locator('[data-test="skew-comparison-card"]')
        check(
            comparison.count() == 2
            and {
                comparison.nth(index).get_attribute("data-direction")
                for index in range(comparison.count())
            }
            == {"leads", "trails"},
            f"{profile_name}: comparison preselects opposite clock directions",
            checks,
            failed,
        )
        check(
            all(
                comparison.nth(index).get_attribute("data-corrected") == "true"
                and comparison.nth(index).locator(".comparison-raw").inner_text().strip()
                and comparison.nth(index).locator(".comparison-shown").inner_text().strip()
                and comparison.nth(index).locator(".comparison-duration").inner_text().strip()
                for index in range(comparison.count())
            ),
            f"{profile_name}: comparison colocates corrected geometry and duration",
            checks,
            failed,
        )

        for index, trace_id in enumerate(trace_ids):
            if index:
                page.locator('[data-test="trace-select"]').select_option(trace_id)
                page.locator(f'[data-test="trace-id"]', has_text=trace_id).wait_for(timeout=10000)
            audit = fetch_json(f"{service_origin}/audit")
            row = submission(audit, trace_id)
            check(row["submitted"], f"{profile_name}: {trace_id} reached protected evaluator", checks, failed)
            check(row["passed"], f"{profile_name}: {trace_id} matches protected corrected geometry", checks, failed)
            check(
                len(row["actual"]) == len(row["raw"]),
                f"{profile_name}: {trace_id} preserves span inventory",
                checks,
                failed,
            )
            raw = {span["id"]: span for span in row["raw"]}
            actual = {span["id"]: span for span in row["actual"]}
            roots = [span for span in row["raw"] if span["parentId"] is None]
            check(
                all(actual[root["id"]] == root for root in roots),
                f"{profile_name}: {trace_id} preserves root geometry",
                checks,
                failed,
            )
            check(
                all(actual[span_id]["durationMs"] == span["durationMs"] for span_id, span in raw.items()),
                f"{profile_name}: {trace_id} preserves every host duration",
                checks,
                failed,
            )
            authorities = row["hostAuthorities"]
            for authority, expected_shift in row["expectedAuthorityShifts"].items():
                shifts = {
                    actual[span_id]["startMs"] - span["startMs"]
                    for span_id, span in raw.items()
                    if authorities[span["host"]] == authority
                }
                check(
                    shifts == {expected_shift},
                    f"{profile_name}: {trace_id} applies one coherent shift to authority {authority}",
                    checks,
                    failed,
                )
            if all(shift == 0 for shift in row["expectedAuthorityShifts"].values()):
                check(
                    row["actual"] == row["raw"],
                    f"{profile_name}: {trace_id} control geometry stays reported as-is",
                    checks,
                    failed,
                )
            check(
                page.locator('[data-test="waterfall"] .span-row').count() == len(row["raw"]),
                f"{profile_name}: {trace_id} waterfall keeps every span",
                checks,
                failed,
            )
            check(
                page.locator('[data-test="span-detail"] .detail-row').count() == len(row["raw"]) + 1,
                f"{profile_name}: {trace_id} raw detail is inspectable",
                checks,
                failed,
            )
            check(
                page.locator('[data-test="hosts"] .host-row').count() == len(authorities),
                f"{profile_name}: {trace_id} host comparison is complete",
                checks,
                failed,
            )
            for host_name, authority in sorted(authorities.items()):
                note = page.locator(f'[data-test="host-{host_name}"] .host-note')
                check(
                    note.count() == 1 and authority in note.inner_text(),
                    f"{profile_name}: {trace_id} operator note names the runtime authority of {host_name}",
                    checks,
                    failed,
                )
            check(
                page.locator('[data-test="warnings"] .advisory').count()
                == len(row["advisories"]),
                f"{profile_name}: {trace_id} renders every runtime operator advisory",
                checks,
                failed,
            )

        audit = fetch_json(f"{service_origin}/audit")
        check(
            set(audit["sequence"]) == set(trace_ids),
            f"{profile_name}: every trace was submitted",
            checks,
            failed,
        )
        check(
            all(row["passed"] for row in audit["submissions"]),
            f"{profile_name}: complete protected trace set passes",
            checks,
            failed,
        )
        try:
            urlopen(f"{app_origin}/api/audit", timeout=5)
            hidden = False
        except HTTPError as error:
            hidden = error.code == 404
        check(hidden, f"{profile_name}: protected audit is not exposed by application host", checks, failed)
        check(not page_errors, f"{profile_name}: no page errors", checks, failed)
        page.close()
    finally:
        stop(processes)


def main():
    checks = []
    failed = []
    try:
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
