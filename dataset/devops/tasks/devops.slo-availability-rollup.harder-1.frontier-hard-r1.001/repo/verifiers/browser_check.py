from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import hashlib
import math
import subprocess
import time
import traceback
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright, expect


ROOT = Path(__file__).resolve().parents[1]
def free_port():
    while True:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        if port not in (51500, 51600):
            return port


APP_PORT = free_port()
SERVICE_PORT = free_port()
while SERVICE_PORT == APP_PORT:
    SERVICE_PORT = free_port()
APP = f"http://127.0.0.1:{APP_PORT}"
SERVICE = f"http://127.0.0.1:{SERVICE_PORT}/v1"
COVERAGE = {"states": [], "probes": [], "selections": 0, "filters": 0, "references": 0, "agreements": 0, "independent_oracle_checks": 0}
PROBES = ("probe-dilution", "probe-inverse", "probe-boundary", "probe-budget")


def request(action: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(
        f"{SERVICE}/{action}",
        data=data,
        method="GET" if payload is None else "POST",
        headers={"content-type": "application/json"},
    )
    with urlopen(req, timeout=5) as response:
        return json.load(response)


def start(command: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def stop(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        except ProcessLookupError:
            pass


def wait_service() -> None:
    for _ in range(80):
        try:
            request("catalog")
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("protected SLO ledger did not start")


def rounded(value):
    return round(value, 10) if isinstance(value, float) else value


def comparable_summary(summary: dict) -> dict:
    return {key: rounded(value) for key, value in summary.items()}


def comparable(snapshot: dict) -> dict:
    return {
        "summary": comparable_summary(snapshot["summary"]),
        "totals": {key: rounded(value) for key, value in snapshot["totals"].items()},
        "slices": [
            {
                key: rounded(value)
                for key, value in item.items()
                if key in {
                    "id",
                    "endpoint",
                    "region",
                    "good",
                    "bad",
                    "total",
                    "availability",
                    "verdict",
                }
            }
            for item in snapshot["slices"]
        ],
        "breakdowns": [
            {
                "dimension": group["dimension"],
                "rows": [
                    {key: rounded(value) for key, value in row.items()}
                    for row in group["rows"]
                ],
            }
            for group in snapshot["breakdowns"]
        ],
        "filter": snapshot["filter"],
        "replayCount": snapshot["replayCount"],
    }


def text(page, testid: str) -> str:
    return page.get_by_test_id(testid).locator("strong").inner_text().lower()


def wait_filter(page, verdict: str) -> dict:
    for _ in range(80):
        snapshot = request("snapshot")
        ids = page.locator("#slices tbody tr").evaluate_all(
            "(rows) => rows.map((row) => row.dataset.sliceId)"
        )
        if (
            snapshot["filter"]["verdict"] == verdict
            and page.get_by_test_id("verdict-filter").input_value() == verdict
            and ids == [item["id"] for item in snapshot["slices"]]
        ):
            return snapshot
        page.wait_for_timeout(25)
    raise AssertionError(f"verdict filter did not converge: {verdict}")


def region_oracle(rows: list[dict], objective: float) -> dict:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["region"], []).append(row)
    availability = 0.0
    consumed = 0.0
    for group in groups.values():
        total = sum(row["total"] for row in group)
        bad = sum(row["bad"] for row in group)
        availability += (total - bad) / total / len(groups)
        consumed += bad / (total * (1 - objective)) * 100 / len(groups)
    return {"objective": objective, "availability": availability,
            "verdict": "met" if availability >= objective else "missed",
            "budgetConsumed": consumed, "budgetRemaining": 100 - consumed}


def check_oracle(summary: dict, rows: list[dict], objective: float) -> None:
    wanted = region_oracle(rows, objective)
    for key, value in wanted.items():
        if isinstance(value, (int, float)):
            assert math.isclose(summary[key], value, rel_tol=1e-10, abs_tol=1e-8), (key, summary[key], value)
        else:
            assert summary[key] == value
    COVERAGE["independent_oracle_checks"] += 1


def check_expected_oracle(audit: dict) -> None:
    fixtures = json.loads((ROOT / "verifiers/profiles.json").read_text())
    profile = fixtures[audit["profileName"]]
    rows = list(profile["scenarios"][audit["scenarioId"]][audit["windowId"]])
    if audit["actual"]["replayCount"]:
        rows.append(profile["replay"])
    check_oracle(audit["expected"]["summary"], rows, profile["objective"])


def verify_agreement(page, snapshot: dict) -> None:
    agreement = snapshot["reportingAgreement"]
    details = page.locator("#reporting-agreement")
    details.locator("summary").click()
    expect(details).to_have_attribute("open", "")
    expect(details.locator("h3")).to_have_text(agreement["title"])
    expect(details.locator("dt")).to_have_text([x["label"] for x in agreement["fields"]])
    expect(details.locator("dd")).to_have_text([x["value"] for x in agreement["fields"]])
    expect(details.locator(".agreement-allocations span")).to_have_text([x["label"] + " " + x["value"] for x in agreement["allocations"]])
    regions = next(x["rows"] for x in snapshot["breakdowns"] if x["dimension"] == "region")
    assert [x["label"] for x in agreement["allocations"]] == [x["key"] for x in regions]
    assert all(x["value"] == f"{100 / len(regions):.3f}%" for x in agreement["allocations"])
    details.locator("summary").click()
    COVERAGE["agreements"] += 1


def check_page(page, audit: dict) -> None:
    actual = audit["actual"]
    expected = audit["expected"]
    same = comparable(actual) == comparable(expected)
    COVERAGE["states"].append({
        "profile": audit["profileName"], "scenario": audit["scenarioId"],
        "window": audit["windowId"], "replay": expected["replayCount"],
        "semantic_match": same,
        "expected_sha256": hashlib.sha256(json.dumps(comparable(expected), sort_keys=True).encode()).hexdigest(),
        "actual_sha256": hashlib.sha256(json.dumps(comparable(actual), sort_keys=True).encode()).hexdigest(),
    })
    assert same, f"{audit['profileName']} {audit['scenarioId']} {audit['windowId']} protected ledger mismatch"
    summary = expected["summary"]
    for key, value in {
        "availability": f"{summary['availability'] * 100:.3f}%",
        "objective": f"{summary['objective'] * 100:.3f}%",
        "verdict": summary["verdict"],
        "budget-consumed": f"{summary['budgetConsumed']:.1f}%",
        "budget-remaining": f"{summary['budgetRemaining']:.1f}%",
    }.items():
        expect(page.get_by_test_id(key).locator("strong")).to_have_text(value)
    for key, value in {
        "good-total": str(expected["totals"]["good"]),
        "bad-total": str(expected["totals"]["bad"]),
        "event-total": str(expected["totals"]["total"]),
        "allowed-total": f"{expected['totals']['allowedFailures']:.2f}",
    }.items():
        expect(page.get_by_test_id(key)).to_have_text(value)
    rows = page.locator("#slices tbody tr")
    expect(rows).to_have_count(len(expected["slices"]))
    for i, item in enumerate(expected["slices"]):
        row = rows.nth(i)
        expect(row).to_have_attribute("data-slice-id", item["id"])
        expect(row.locator("td")).to_have_text([
            item["endpoint"], item["region"], str(item["good"]), str(item["bad"]),
            str(item["total"]), f"{item['availability'] * 100:.3f}%", item["verdict"],
        ])
    groups = page.locator("#breakdowns .breakdown")
    expect(groups).to_have_count(len(expected["breakdowns"]))
    for i, group in enumerate(expected["breakdowns"]):
        rendered = groups.nth(i)
        expect(rendered.locator("h3")).to_have_text(group["dimension"])
        expect(rendered.locator("div")).to_have_count(len(group["rows"]))
        for j, item in enumerate(group["rows"]):
            row = rendered.locator("div").nth(j)
            expect(row.locator("span")).to_have_text(item["key"])
            expect(row.locator("strong")).to_have_text(f"{item['availability'] * 100:.3f}%")
            expect(row.locator("small")).to_have_text(f"{item['bad']} / {item['total']} bad")


def ui_action(page, callback):
    # Every operator action completes with a fresh snapshot. Match that response
    # before consulting the protected audit, so a previous result cannot pass.
    with page.expect_response(lambda response: response.url.endswith("/api/snapshot") and response.request.method == "GET") as refreshed:
        callback()
    response = refreshed.value
    assert response.status == 200, "operator snapshot request failed"
    return response.json()


def exercise_selection_and_filter(page, expected: dict) -> None:
    rows = expected["slices"]
    ui_action(page, lambda: page.locator("#slices tbody tr").nth(1).locator("button").click())
    item = rows[1]
    expect(page.get_by_test_id("detail").locator("dd")).to_have_text([
        item["id"], item["endpoint"], item["region"], f"{item['availability'] * 100:.3f}%",
        f"{item['good']} / {item['bad']} / {item['total']}", item["verdict"],
    ])
    COVERAGE["selections"] += 1
    for verdict in ("met", "missed", "all"):
        ui_action(page, lambda: page.get_by_test_id("verdict-filter").select_option(verdict))
        snapshot = wait_filter(page, verdict)
        wanted = [item for item in rows if verdict == "all" or item["verdict"] == verdict]
        assert [item["id"] for item in snapshot["slices"]] == [item["id"] for item in wanted]
        # Filtering is a view operation and must not change the complete ledger.
        assert comparable_summary(snapshot["summary"]) == comparable_summary(expected["summary"])
        assert snapshot["totals"] == expected["totals"]
        COVERAGE["filters"] += 1


def exercise_probes(page) -> None:
    for probe_id in PROBES:
        page.get_by_test_id("probe").select_option(probe_id)
        with page.expect_response(lambda response: response.url.endswith("/api/probe") and response.request.post_data_json == {"probeId": probe_id}) as response:
            ui_action(page, lambda: page.get_by_test_id("run-probe").click())
        assert response.value.status == 200
        response.value.json()
        audit = request("audit")
        actual = comparable_summary(audit["actualProbe"])
        expected = comparable_summary(audit["expectedProbe"])
        fixtures = json.loads((ROOT / "verifiers/profiles.json").read_text())
        probe = next(x for x in fixtures["probes"] if x["id"] == probe_id)
        check_oracle(audit["expectedProbe"], probe["slices"], probe["objective"])
        COVERAGE["probes"].append({"profile": audit["profileName"], "scenario": audit["scenarioId"], "window": audit["windowId"], "probe": probe_id, "semantic_match": actual == expected})
        assert actual == expected, f"probe mismatch: {probe_id}"
        expect(page.get_by_test_id("probe-result").locator("strong")).to_have_text(expected["verdict"])
        expect(page.get_by_test_id("probe-result").locator("span")).to_have_text(
            f"{expected['availability'] * 100:.3f}% · {expected['budgetConsumed']:.1f}% budget"
        )


def verify_reference(page) -> None:
    reference = request("catalog")["rollupReference"]
    details = page.locator("#rollup-reference")
    details.locator("summary").click()
    expect(details).to_have_attribute("open", "")
    options = details.locator(".rollup-option")
    expect(options).to_have_count(len(reference))
    for i, item in enumerate(reference):
        option = options.nth(i)
        expect(option.locator("h3")).to_have_text(item["label"])
        expect(option.locator("p")).to_have_text(item["description"])
        expect(option.locator("dd")).to_have_text([item["mode"], item["weight"] or "none"])
    details.locator("summary").click()
    COVERAGE["references"] += 1


def verify_profile(page, profile: str) -> None:
    request("reset", {"profileName": profile})
    page.goto(APP, wait_until="networkidle")
    page.wait_for_function(
        "document.querySelector('[data-testid=app]')?.dataset.ready === 'yes'"
    )
    verify_reference(page)
    signatures: set[str] = set()
    for scenario in ("dilution", "inverse", "regional"):
        ui_action(page, lambda: page.get_by_test_id("scenario").select_option(scenario))
        for window in ("30d", "7d"):
            ui_action(page, lambda: page.get_by_test_id("window").select_option(window))
            for _ in range(80):
                audit = request("audit")
                if audit["scenarioId"] == scenario and audit["windowId"] == window:
                    break
                page.wait_for_timeout(25)
            else:
                raise AssertionError(f"state did not converge: {scenario}/{window}")
            check_expected_oracle(audit)
            check_page(page, audit)
            verify_agreement(page, audit["actual"])
            exercise_selection_and_filter(page, audit["expected"])
            exercise_probes(page)
            signatures.add(json.dumps(comparable(audit["expected"]), sort_keys=True))
            if scenario == "regional" and window == "7d":
                ui_action(page, lambda: page.get_by_test_id("replay").click())
                for _ in range(80):
                    replay = request("audit")
                    if replay["actual"]["replayCount"] == 1:
                        break
                    page.wait_for_timeout(25)
                check_expected_oracle(replay)
                check_page(page, replay)
                verify_agreement(page, replay["actual"])
    assert len(signatures) == 6


def check_audit_is_not_proxied() -> None:
    try:
        urlopen(f"{APP}/api/audit", timeout=3)
    except HTTPError as error:
        assert error.code == 404
        return
    raise AssertionError("application host exposed protected audit")


def main() -> None:
    env = dict(os.environ)
    service = start(["node", "verifiers/slo_service.mjs"], {**env, "PORT": str(SERVICE_PORT)})
    app = start(
        ["node", "server.mjs"],
        {**env, "PORT": str(APP_PORT), "CUA_SWE_EXTERNAL_SERVICE_ORIGIN": f"http://127.0.0.1:{SERVICE_PORT}"},
    )
    try:
        wait_service()
        for _ in range(80):
            if app.poll() is not None or service.poll() is not None:
                raise RuntimeError("construction runtime exited before readiness")
            try:
                with urlopen(APP, timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("SLO application did not start")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            verify_profile(page, "visible")
            verify_profile(page, "hidden")
            check_audit_is_not_proxied()
            browser.close()
        print(json.dumps({"passed": True, "profiles": 2, "states": 12, "coverage": COVERAGE, "infrastructure_error": False}))
    except AssertionError as error:
        print(json.dumps({
            "passed": False, "infrastructure_error": False, "coverage": COVERAGE,
            "error": f"{type(error).__name__}: {error}",
            "traceback": traceback.format_exc(),
        }))
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({"infrastructure_error": True, "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc(), "coverage": COVERAGE}))
        raise SystemExit(2)
    finally:
        stop(app)
        stop(service)


if __name__ == "__main__":
    main()
