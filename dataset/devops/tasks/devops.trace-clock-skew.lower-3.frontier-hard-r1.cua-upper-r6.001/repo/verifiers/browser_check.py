#!/usr/bin/env python3
"""Protected behavioural verifier for the Spanline operator-calibration clock-skew task."""

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

EXPECTED_CARDS = {
    "visible": ["leads", "trails"],
    "hidden": ["trails", "leads"],
}

# Board-published filing codes. Their meaning exists only on the evaluator-owned
# raster calibration board; it must never appear in a machine-readable channel.
ARCHIVE_REGISTER = "R-207"
RECHECK_REGISTER = "R-311"
STANDING_DISPOSITION = "D-41"
WITHDRAWN_DISPOSITION = "D-17"
RECHECK_DISPOSITION = "D-63"
RESET_AUTHORITY_CREW = "crew-12"
INSTRUMENTATION_CREW = "crew-07"

BOARD_SHEETS = {1: (1120, 340), 2: (1120, 310), 3: (1120, 330)}

# Semantic vocabulary that must stay off every machine-readable payload channel
# (catalog, trace titles, capture metadata, advisories, identifiers).
FORBIDDEN_PAYLOAD_TERMS = [
    "before-reset",
    "after-reset",
    "before the",
    "after the",
    "supersede",
    "superseded",
    "withdrawn",
    "standing",
    "current",
    "certified",
    "authoritative",
    "reference",
    "sign-off",
    "maintenance owner",
    "resetevent",
    "recordedby",
    "supersededby",
    "window",
    "status",
    "resync",
    "recal",
]
ALLOWED_CAPTURE_KEYS = {"workload", "register", "capturedAt", "crew", "disposition"}
ALLOWED_TRANSITION_KEYS = {"at", "label", "bulletin"}


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


def outside_count(spans):
    index = {span["id"]: span for span in spans}
    count = 0
    for span in spans:
        parent = index.get(span["parentId"]) if span["parentId"] is not None else None
        if parent and (span["startMs"] < parent["startMs"] or span["endMs"] > parent["endMs"]):
            count += 1
    return count


def span_signature(spans):
    return sorted((span["service"], span["operation"], span["host"], span["durationMs"]) for span in spans)


def root_span(spans):
    return next(span for span in spans if span["parentId"] is None)


def replay_deltas(broken_row, candidate_row):
    """One coherent per-authority delta between a broken capture and a replay,
    matched span by span through service, operation, and host; None when the
    match is incomplete or incoherent."""
    matched = {
        (span["service"], span["operation"], span["host"]): span
        for span in candidate_row["raw"]
    }
    deltas = {}
    for span in broken_row["raw"]:
        partner = matched.get((span["service"], span["operation"], span["host"]))
        if partner is None or partner["durationMs"] != span["durationMs"]:
            return None
        authority = broken_row["hostAuthorities"][span["host"]]
        delta = partner["startMs"] - span["startMs"]
        if partner["endMs"] - span["endMs"] != delta:
            return None
        if authority in deltas and deltas[authority] != delta:
            return None
        deltas[authority] = delta
    return deltas


def payload_leak_terms(catalog):
    """Semantic mapping terms present on the machine-readable catalog channel."""
    fragments = [json.dumps(catalog.get("transition") or {}, sort_keys=True)]
    for entry in catalog.get("traces", []):
        fragments.append(entry.get("id") or "")
        fragments.append(entry.get("title") or "")
        fragments.append(json.dumps(entry.get("capture") or {}, sort_keys=True))
    haystack = "\n".join(fragments).lower()
    return sorted({term for term in FORBIDDEN_PAYLOAD_TERMS if term in haystack})


def advisory_leak_terms(rows):
    haystack = "\n".join(a for row in rows for a in row.get("advisories", [])).lower()
    return sorted({term for term in FORBIDDEN_PAYLOAD_TERMS if term in haystack})


def board_state(page):
    image = page.locator('[data-test="calibration-board"]')
    if image.count() != 1:
        return None
    return image.evaluate(
        "(image) => ({complete: image.complete, width: image.naturalWidth,"
        " height: image.naturalHeight, src: image.currentSrc || image.src})"
    )


def assert_board_sheet(page, sheet, label, checks, failed):
    page.wait_for_function(
        f"""() => {{
            const image = document.querySelector('[data-test="calibration-board"]');
            return image && image.complete && image.naturalWidth === {BOARD_SHEETS[sheet][0]}
                && image.naturalHeight === {BOARD_SHEETS[sheet][1]};
        }}""",
        timeout=10000,
    )
    state = board_state(page)
    sheet_text = page.locator('[data-test="board-sheet"]').inner_text().strip()
    check(
        state is not None
        and state["complete"]
        and (state["width"], state["height"]) == BOARD_SHEETS[sheet]
        and f"sheet={sheet}" in state["src"]
        and sheet_text == f"Sheet {sheet} of 3",
        label,
        checks,
        failed,
    )


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
        assert_board_sheet(
            page, 1, f"{profile_name}: calibration board opens on sheet 1", checks, failed
        )
        page.locator('[data-test="board-next"]').click()
        assert_board_sheet(
            page, 2, f"{profile_name}: board advances to the crew-roster sheet", checks, failed
        )
        page.locator('[data-test="board-next"]').click()
        assert_board_sheet(
            page, 3, f"{profile_name}: board advances to the disposition sheet", checks, failed
        )
        page.locator('[data-test="board-next"]').click()
        assert_board_sheet(
            page, 1, f"{profile_name}: board wraps deterministically back to sheet 1", checks, failed
        )
        page.locator('[data-test="board-prev"]').click()
        assert_board_sheet(
            page, 3, f"{profile_name}: board steps back deterministically", checks, failed
        )
        page.locator('[data-test="board-prev"]').click()
        page.locator('[data-test="board-prev"]').click()
        assert_board_sheet(
            page, 1, f"{profile_name}: board returns to sheet 1 for the walkthrough", checks, failed
        )

        options = page.locator('[data-test="trace-select"] option')
        audit = fetch_json(f"{service_origin}/audit")
        catalog = fetch_json(f"{service_origin}/catalog")
        trace_ids = audit["traceIds"]
        check(options.count() == len(trace_ids), f"{profile_name}: every capture remains selectable", checks, failed)
        transition = catalog.get("transition") or {}
        check(
            bool(transition.get("at"))
            and set(transition) <= ALLOWED_TRANSITION_KEYS,
            f"{profile_name}: transition notice is published without any crew or authority field",
            checks,
            failed,
        )
        check(
            all(
                set(entry.get("capture") or {}) <= ALLOWED_CAPTURE_KEYS
                for entry in catalog.get("traces", [])
            ),
            f"{profile_name}: capture metadata carries only opaque filing codes",
            checks,
            failed,
        )
        leaks = payload_leak_terms(catalog)
        check(
            not leaks,
            f"{profile_name}: catalog channel is free of semantic mapping terms ({leaks})",
            checks,
            failed,
        )
        advisory_leaks = advisory_leak_terms(audit["submissions"])
        check(
            not advisory_leaks,
            f"{profile_name}: advisories are free of semantic mapping terms ({advisory_leaks})",
            checks,
            failed,
        )

        broken_rows = [
            row
            for row in audit["submissions"]
            if row["capture"]["register"] == ARCHIVE_REGISTER
            and any(shift != 0 for shift in row["expectedAuthorityShifts"].values())
        ]
        check(len(broken_rows) == 2, f"{profile_name}: two archive captures carry the skew", checks, failed)
        broken_workloads = {row["capture"]["workload"] for row in broken_rows}
        candidates_by_workload = {}
        board_states = set()
        for row in broken_rows:
            workload = row["capture"]["workload"]
            candidates = [
                item
                for item in audit["submissions"]
                if item["capture"]["register"] == RECHECK_REGISTER
                and item["capture"]["workload"] == workload
            ]
            candidates_by_workload[workload] = candidates
            check(
                len(candidates) >= 4,
                f"{profile_name}: {row['traceId']} has at least four post-transition replay candidates",
                checks,
                failed,
            )
            check(
                all(
                    span_signature(item["raw"]) == span_signature(row["raw"])
                    and (root_span(item["raw"])["startMs"], root_span(item["raw"])["endMs"])
                    == (root_span(row["raw"])["startMs"], root_span(row["raw"])["endMs"])
                    and all(shift == 0 for shift in item["expectedAuthorityShifts"].values())
                    for item in candidates
                ),
                f"{profile_name}: {row['traceId']} replay candidates overlap in service, operation, host, duration, and root geometry",
                checks,
                failed,
            )
            dispositions = [item["capture"].get("disposition") for item in candidates]
            standing = [
                item for item in candidates if item["capture"].get("disposition") == STANDING_DISPOSITION
            ]
            check(
                len({item["capture"]["crew"] for item in candidates}) >= 3
                and WITHDRAWN_DISPOSITION in dispositions
                and any(
                    item["capture"].get("disposition") == RECHECK_DISPOSITION
                    and item["capture"]["crew"] == INSTRUMENTATION_CREW
                    for item in candidates
                ),
                f"{profile_name}: {row['traceId']} candidates span three crews with withdrawn and sensor-recheck filings",
                checks,
                failed,
            )
            check(
                len(standing) >= 2
                and len({item["capture"]["crew"] for item in standing}) >= 2,
                f"{profile_name}: {row['traceId']} has competing standing replays from different crews",
                checks,
                failed,
            )
            authoritative = [
                item for item in standing if item["capture"]["crew"] == RESET_AUTHORITY_CREW
            ]
            check(
                len(authoritative) == 1,
                f"{profile_name}: {row['traceId']} has exactly one standing reset-authority replay",
                checks,
                failed,
            )
            check(
                bool(authoritative)
                and replay_deltas(row, authoritative[0]) == row["expectedAuthorityShifts"],
                f"{profile_name}: {row['traceId']} reset-authority replay deltas equal the protected correction",
                checks,
                failed,
            )
            check(
                bool(authoritative)
                and all(
                    replay_deltas(row, item) != row["expectedAuthorityShifts"]
                    for item in candidates
                    if item["traceId"] != authoritative[0]["traceId"]
                ),
                f"{profile_name}: {row['traceId']} every other replay candidate disagrees with the protected correction",
                checks,
                failed,
            )

        comparison = page.locator('[data-test="skew-comparison-card"]')
        expected_directions = EXPECTED_CARDS[profile_name]
        check(
            comparison.count() == 2
            and [
                comparison.nth(index).get_attribute("data-direction")
                for index in range(comparison.count())
            ]
            == expected_directions,
            f"{profile_name}: comparison preselects opposite clock directions",
            checks,
            failed,
        )
        check(
            comparison.count() == 2
            and all(
                comparison.nth(index).locator(".comparison-raw").inner_text().strip()
                and comparison.nth(index).locator(".comparison-shown").inner_text().strip()
                and comparison.nth(index).locator(".comparison-duration").inner_text().strip()
                for index in range(comparison.count())
            ),
            f"{profile_name}: comparison colocates reported and displayed geometry with duration",
            checks,
            failed,
        )
        check(
            comparison.count() == 2
            and comparison.nth(0).get_attribute("data-corrected") == "true",
            f"{profile_name}: direct-evidence card resolves within its reported parent",
            checks,
            failed,
        )
        if comparison.count() == 2:
            raw_text = comparison.nth(1).locator(".comparison-raw").inner_text()
            shown_text = comparison.nth(1).locator(".comparison-shown").inner_text()
            check(
                comparison.nth(1).get_attribute("data-corrected") == "false"
                and raw_text.replace("reported", "").strip()
                == shown_text.replace("displayed", "").strip(),
                f"{profile_name}: ambiguous-boundary card leaves the non-owner span unmoved",
                checks,
                failed,
            )

        board_probe_ids = set()
        if broken_rows:
            board_probe_ids.add(broken_rows[0]["traceId"])
            first_candidates = candidates_by_workload[broken_rows[0]["capture"]["workload"]]
            if first_candidates:
                board_probe_ids.add(first_candidates[0]["traceId"])
        board_probe_ids.add(trace_ids[-1])

        for index, trace_id in enumerate(trace_ids):
            if index:
                page.locator('[data-test="trace-select"]').select_option(trace_id)
                page.locator(
                    '[data-test="trace-id"]',
                    has_text=re.compile(rf"^{re.escape(trace_id)}$"),
                ).wait_for(timeout=10000)
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
            title_text = page.locator('[data-test="trace-title"]').inner_text().strip()
            check(
                title_text == row["title"],
                f"{profile_name}: {trace_id} shows its runtime capture title",
                checks,
                failed,
            )
            capture = row["capture"]
            check(
                capture["register"] in title_text and capture["crew"] in title_text,
                f"{profile_name}: {trace_id} title carries its register and crew codes on screen",
                checks,
                failed,
            )
            if capture["register"] == RECHECK_REGISTER and capture["workload"] in broken_workloads:
                warnings_text = page.locator('[data-test="warnings"]').inner_text()
                check(
                    capture["crew"] in warnings_text,
                    f"{profile_name}: {trace_id} advisory names its filing crew code on screen",
                    checks,
                    failed,
                )
                check(
                    capture.get("disposition") in title_text,
                    f"{profile_name}: {trace_id} shows its disposition code on screen",
                    checks,
                    failed,
                )
            if trace_id in board_probe_ids:
                state = board_state(page)
                check(
                    state is not None
                    and state["complete"]
                    and (state["width"], state["height"]) == BOARD_SHEETS[1],
                    f"{profile_name}: {trace_id} calibration board stays readable in this state",
                    checks,
                    failed,
                )
            check(
                page.locator('[data-test="outside-count"]').inner_text().strip()
                == str(outside_count(row["expected"])),
                f"{profile_name}: {trace_id} renders the corrected boundary count",
                checks,
                failed,
            )
            moved = sum(
                1
                for span_id, span in raw.items()
                if row["expectedAuthorityShifts"].get(authorities[span["host"]], 0) != 0
            )
            check(
                page.locator('[data-test="adjusted-count"]').inner_text().strip() == str(moved),
                f"{profile_name}: {trace_id} reports how many spans were translated",
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
            f"{profile_name}: every capture was submitted",
            checks,
            failed,
        )
        check(
            all(row["passed"] for row in audit["submissions"]),
            f"{profile_name}: complete protected capture set passes",
            checks,
            failed,
        )
        pre_instr = next(
            (
                row
                for row in audit["submissions"]
                if row["capture"]["register"] == ARCHIVE_REGISTER and row["advisories"]
            ),
            None,
        )
        post_instr = next(
            (
                row
                for row in audit["submissions"]
                if pre_instr is not None
                and row["capture"]["register"] == RECHECK_REGISTER
                and row["capture"]["workload"] == pre_instr["capture"]["workload"]
            ),
            None,
        )
        check(
            pre_instr is not None
            and post_instr is not None
            and outside_count(pre_instr["expected"]) == outside_count(post_instr["expected"]) > 0
            and pre_instr["actual"] == pre_instr["raw"]
            and post_instr["actual"] == post_instr["raw"],
            f"{profile_name}: flagged sensor boundary persists across the transition untouched",
            checks,
            failed,
        )
        instrumentation_crew = pre_instr["capture"]["crew"] if pre_instr else None
        check(
            pre_instr is not None
            and instrumentation_crew == INSTRUMENTATION_CREW
            and instrumentation_crew != RESET_AUTHORITY_CREW
            and any(instrumentation_crew in advisory for advisory in pre_instr["advisories"])
            and all(
                any(
                    item["capture"]["crew"] == instrumentation_crew
                    for item in candidates
                )
                for candidates in candidates_by_workload.values()
            ),
            f"{profile_name}: flagged-control crew code recurs on a replay candidate of every broken workload",
            checks,
            failed,
        )
        sequence_before = len(audit["sequence"])
        page.locator('[data-test="trace-select"]').select_option(trace_ids[0])
        page.locator(
            '[data-test="trace-id"]',
            has_text=re.compile(rf"^{re.escape(trace_ids[0])}$"),
        ).wait_for(timeout=10000)
        audit = fetch_json(f"{service_origin}/audit")
        row = submission(audit, trace_ids[0])
        check(
            len(audit["sequence"]) == sequence_before + 1
            and audit["sequence"][-1] == trace_ids[0]
            and row["passed"],
            f"{profile_name}: reselecting a capture resubmits identical corrected geometry",
            checks,
            failed,
        )
        state = board_state(page)
        check(
            state is not None and state["complete"],
            f"{profile_name}: calibration board survives the reselection reset",
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
