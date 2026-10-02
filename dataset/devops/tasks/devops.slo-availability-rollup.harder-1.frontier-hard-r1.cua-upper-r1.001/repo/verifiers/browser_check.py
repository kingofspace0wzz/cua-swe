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
COVERAGE = {"states": [], "probes": [], "selections": 0, "filters": 0, "references": 0, "agreements": 0, "rollouts": 0, "independent_oracle_checks": 0}
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


def comparable_rollout(rollout: dict | None) -> dict | None:
    if not rollout:
        return None
    return {
        "reportDate": rollout["reportDate"],
        "scopes": [
            {key: item[key] for key in ("scope", "label")}
            for item in rollout["scopes"]
        ],
        "ledger": [
            {
                "epoch": row["epoch"],
                "caption": row["caption"],
                "cells": [
                    {key: cell[key] for key in ("scope", "covered", "mode", "weight") if key in cell}
                    for cell in row["cells"]
                ],
            }
            for row in rollout["ledger"]
        ],
        "views": [
            {
                "slot": view["slot"],
                "epoch": view["epoch"],
                "title": view["title"],
                "caption": view["caption"],
                "basis": view["basis"],
                "availability": rounded(view["availability"]),
                "verdict": view["verdict"],
                "budgetConsumed": rounded(view["budgetConsumed"]),
                "budgetRemaining": rounded(view["budgetRemaining"]),
            }
            for view in rollout["views"]
        ],
    }


def comparable(snapshot: dict) -> dict:
    return {
        "summary": comparable_summary(snapshot["summary"]),
        "rollout": comparable_rollout(snapshot.get("rollout")),
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


EXPECTED_SCHEDULE_CHIPS = {
    ("rev-2411", "standing"): ("pooled_events", "none"),
    ("rev-2411", "review"): ("pooled_events", "none"),
    ("rev-2503", "standing"): ("mean_of_slices", "none"),
    ("rev-2503", "review"): ("weighted_slices", "region_equal"),
    ("rev-2507", "standing"): ("weighted_slices", "region_equal"),
    ("rev-2509", "standing"): ("weighted_slices", "good"),
    ("rev-2509", "review"): ("weighted_slices", "good"),
}


def pooled_view_oracle(rows: list[dict], objective: float) -> dict:
    total = sum(row["total"] for row in rows)
    bad = sum(row["bad"] for row in rows)
    availability = (total - bad) / total
    consumed = bad / (total * (1 - objective)) * 100
    return {"availability": availability,
            "verdict": "met" if availability >= objective else "missed",
            "budgetConsumed": consumed, "budgetRemaining": 100 - consumed}


def mean_view_oracle(rows: list[dict], objective: float) -> dict:
    availability = sum((row["total"] - row["bad"]) / row["total"] for row in rows) / len(rows)
    consumed = sum(row["bad"] / (row["total"] * (1 - objective)) for row in rows) / len(rows) * 100
    return {"availability": availability,
            "verdict": "met" if availability >= objective else "missed",
            "budgetConsumed": consumed, "budgetRemaining": 100 - consumed}


def good_weighted_view_oracle(rows: list[dict], objective: float) -> dict:
    goods = [row["total"] - row["bad"] for row in rows]
    denominator = sum(goods)
    availability = sum((good / row["total"]) * good for good, row in zip(goods, rows)) / denominator
    consumed = sum(
        (row["bad"] / (row["total"] * (1 - objective))) * good
        for good, row in zip(goods, rows)
    ) / denominator * 100
    return {"availability": availability,
            "verdict": "met" if availability >= objective else "missed",
            "budgetConsumed": consumed, "budgetRemaining": 100 - consumed}


def check_expected_rollout(audit: dict, fixtures: dict, opening: list[dict], rows: list[dict], objective: float) -> None:
    rollout = audit["expected"]["rollout"]
    assert rollout, "expected snapshot must carry the deployment rollout"
    fixture_rollout = fixtures["rollout"]
    scope = next(item["scope"] for item in fixture_rollout["scopes"] if item["window"] == audit["windowId"])
    assert rollout["reportDate"] == fixture_rollout["reportDate"]
    assert [
        {key: item[key] for key in ("scope", "label")} for item in rollout["scopes"]
    ] == [
        {key: item[key] for key in ("scope", "label")} for item in fixture_rollout["scopes"]
    ]
    records = fixture_rollout["records"]
    assert [row["epoch"] for row in rollout["ledger"]] == [record["epoch"] for record in records]
    for row, record in zip(rollout["ledger"], records):
        assert row["caption"] == record["caption"], ("ledger caption", row)
        for cell, scope_entry in zip(row["cells"], fixture_rollout["scopes"]):
            cell_scope = scope_entry["scope"]
            assert cell["scope"] == cell_scope, ("cell scope", row["epoch"], cell)
            if cell_scope not in record["coverage"]:
                assert cell["covered"] is False, ("cell must be uncovered", row["epoch"], cell)
                continue
            assert cell["covered"] is True, ("cell must be covered", row["epoch"], cell)
            mode, weight = EXPECTED_SCHEDULE_CHIPS[(row["epoch"], cell_scope)]
            assert (cell["mode"], cell["weight"]) == (mode, weight), ("ledger chip", row["epoch"], cell)
    views = {view["slot"]: view for view in rollout["views"]}
    assert set(views) == {"archive", "prior", "staged"}, "expected rollout views must cover archive, prior, and staged"
    prior_epoch = fixture_rollout["priors"][scope]
    wanted_views = (
        ("archive", fixture_rollout["views"]["archive"]["epoch"], pooled_view_oracle(opening, objective)),
        ("prior", prior_epoch,
         mean_view_oracle(rows, objective) if scope == "standing" else pooled_view_oracle(rows, objective)),
        ("staged", fixture_rollout["views"]["staged"]["epoch"], good_weighted_view_oracle(rows, objective)),
    )
    for slot, epoch, wanted in wanted_views:
        view = views[slot]
        record = next(item for item in records if item["epoch"] == epoch)
        assert view["epoch"] == epoch, (slot, "epoch", view["epoch"], epoch)
        assert view["title"] == fixture_rollout["views"][slot]["title"], (slot, "title")
        assert view["caption"] == record["caption"], (slot, "caption")
        assert view["basis"] == fixture_rollout["views"][slot]["basis"], (slot, "basis")
        for key, value in wanted.items():
            if isinstance(value, str):
                assert view[key] == value, (slot, key, view[key], value)
            else:
                assert math.isclose(view[key], value, rel_tol=1e-10, abs_tol=1e-8), (slot, key, view[key], value)
    COVERAGE["independent_oracle_checks"] += 1


def check_expected_oracle(audit: dict) -> None:
    fixtures = json.loads((ROOT / "verifiers/profiles.json").read_text())
    profile = fixtures[audit["profileName"]]
    opening = list(profile["scenarios"][audit["scenarioId"]][audit["windowId"]])
    rows = list(opening)
    if audit["actual"]["replayCount"]:
        rows.append(profile["replay"])
    check_oracle(audit["expected"]["summary"], rows, profile["objective"])
    check_expected_rollout(audit, fixtures, opening, rows, profile["objective"])


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


def verify_deployments(page, snapshot: dict) -> None:
    rollout = snapshot["rollout"]
    assert rollout, "runtime snapshot is missing the deployment rollout"
    panel = page.get_by_test_id("deployments")
    expect(panel.get_by_test_id("report-date")).to_have_text(rollout["reportDate"])
    expect(panel.locator("thead th")).to_have_text(
        ["Revision", "Record"] + [item["label"] for item in rollout["scopes"]]
    )
    rows = panel.locator("tbody tr")
    expect(rows).to_have_count(len(rollout["ledger"]))
    for i, item in enumerate(rollout["ledger"]):
        row = rows.nth(i)
        expect(row).to_have_attribute("data-epoch", item["epoch"])
        expect(row.locator("td")).to_have_text(
            [item["epoch"], item["caption"]]
            + [
                f"{cell['mode']} · {cell['weight']}" if cell["covered"] else "not covered"
                for cell in item["cells"]
            ]
        )
    views = page.locator("#rollout-views .rollout-view")
    expect(views).to_have_count(len(rollout["views"]))
    for i, item in enumerate(rollout["views"]):
        view = views.nth(i)
        expect(view).to_have_attribute("data-view", item["slot"])
        expect(view.locator("h3")).to_have_text(f"{item['title']} {item['epoch']}")
        expect(view.locator("p")).to_have_text(f"{item['caption']} — {item['basis']}")
        expect(view.locator("dd")).to_have_text([
            f"{item['availability'] * 100:.3f}%", item["verdict"],
            f"{item['budgetConsumed']:.1f}%", f"{item['budgetRemaining']:.1f}%",
        ])
    COVERAGE["rollouts"] += 1


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
    rollout_ready = False
    for _ in range(120):
        if (
            request("snapshot")["rollout"] is not None
            and page.locator("#deployments table").count() > 0
            and page.locator("#rollout-views .rollout-view").count() > 0
        ):
            rollout_ready = True
            break
        page.wait_for_timeout(25)
    assert rollout_ready, "deployment rollout was not published and rendered"
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
            verify_deployments(page, audit["actual"])
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
                verify_deployments(page, replay["actual"])
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
