#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
PAYLOADS = json.loads((ROOT / "contract_payloads.json").read_text())
SCENARIOS = {
    "primary": {
        "center_units": 1,
        "total_units": 2,
        "active_ref": "glyph-zeta-315",
        "trace_fragments": (
            "standbyCargoRouteV13=route-amber-219",
            "activeCargoRouteV13=route-cobalt-864",
            "standbyCargoMapV13=map-lyra-418",
            "activeCargoMapV13=map-orion-705",
            "cargoShadowRouteMapV13.0.aliasGlyphV13=alias-saffron-481",
            "cargoRouteMapV13.1.mapGlyphV13=map-orion-705",
            "cargoRouteMapV13.1.aliasGlyphV13=alias-indigo-926",
            "cargoAliasMapV13.1.relayGlyphV13=relay-onyx-804",
            "cargoRelayMapV13.1.receiptGlyphV13=glyph-zeta-315",
            "cargoReceiptMatrixV13.2.receiptGlyphV13=glyph-zeta-315",
        ),
    },
    "secondary": {
        "center_units": 2,
        "total_units": 3,
        "active_ref": "glyph-lambda-642",
        "trace_fragments": (
            "activeCargoRouteV13=route-amber-219",
            "standbyCargoRouteV13=route-cobalt-864",
            "activeCargoMapV13=map-lyra-418",
            "standbyCargoMapV13=map-orion-705",
            "cargoShadowRouteMapV13.0.aliasGlyphV13=alias-indigo-926",
            "cargoRouteMapV13.1.mapGlyphV13=map-lyra-418",
            "cargoRouteMapV13.1.aliasGlyphV13=alias-saffron-481",
            "cargoAliasMapV13.0.relayGlyphV13=relay-silver-357",
            "cargoRelayMapV13.0.receiptGlyphV13=glyph-lambda-642",
            "cargoReceiptMatrixV13.1.receiptGlyphV13=glyph-lambda-642",
        ),
    },
}


class ContractHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json({"ok": True})
            return
        if parsed.path != "/api/cargo-manifest":
            self.send_error(404)
            return
        key = (
            "secondary"
            if parse_qs(parsed.query).get("scenario", [""])[0] == "secondary"
            else "primary"
        )
        self._json(PAYLOADS[key])

    def _json(self, value: object) -> None:
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_contract_service() -> ThreadingHTTPServer | None:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 4174), ContractHandler)
    except OSError:
        return None
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def scenario_url(base_url: str, scenario: str) -> str:
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)
    query.update({"benchmark": ["1"], "level": ["3"], "scenario": [scenario]})
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def state(page):
    return page.evaluate("window.gameAPI.getState()")


def replay(page, base_url: str, scenario: str, evidence_dir: Path) -> dict:
    expected = SCENARIOS[scenario]
    page.goto(scenario_url(base_url, scenario), wait_until="load")
    page.wait_for_function("window.gameAPI && window.gameAPI.getState")
    page.evaluate("window.gameAPI.reset({seed: 45, level: 3})")
    page.wait_for_function(
        "window.gameAPI.getState().metrics.cargo_contract_ready === true"
    )
    page.wait_for_timeout(150)

    initial = state(page)
    page.screenshot(path=str(evidence_dir / f"{scenario}-initial.png"))
    if (
        initial["seed"] != 45
        or initial["metrics"]["coins"] != 0
        or initial["metrics"]["coins_total"] != expected["total_units"]
        or initial["metrics"]["remaining_coins"] != expected["total_units"]
        or initial["metrics"]["world_collected_coins"] != 0
        or initial["metrics"]["semantic_mismatch"]
    ):
        raise AssertionError(f"{scenario} invalid initial state: {initial}")
    trace = initial["debug"]["cargo_trace"]
    if not all(fragment in trace for fragment in expected["trace_fragments"]):
        raise AssertionError(f"{scenario} live cargo trace was incomplete: {trace}")

    page.keyboard.down("d")
    after_center = initial
    trigger_frames = 0
    for trigger_frames in range(1, 41):
        page.wait_for_timeout(100)
        after_center = state(page)
        if after_center["metrics"]["remaining_coins"] == 1:
            break
    page.keyboard.up("d")
    page.screenshot(path=str(evidence_dir / f"{scenario}-after-center.png"))

    checkpoint_path = evidence_dir / f"{scenario}-checkpoint-state.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "initial": initial,
                "after_center": after_center,
                "trigger_frames": trigger_frames,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    metrics = after_center["metrics"]
    if metrics["remaining_coins"] != 1:
        raise AssertionError(f"{scenario} center cargo was not isolated: {after_center}")
    if after_center["debug"]["lift_direction"] >= -0.1:
        raise AssertionError(
            f"{scenario} cargo was not collected while the lift descended: "
            f"{after_center}"
        )
    if metrics["world_collected_coins"] != expected["center_units"]:
        raise AssertionError(
            f"{scenario} removed world units were wrong: {after_center}"
        )
    if metrics["coins"] != expected["center_units"] or metrics["semantic_mismatch"]:
        raise AssertionError(
            f"{scenario} inventory disagreed with rendered world cargo: "
            + json.dumps(after_center, sort_keys=True)
        )
    if metrics["last_inventory_receipt"] != expected["active_ref"]:
        raise AssertionError(
            f"{scenario} selected the wrong live cargo receipt: "
            f"expected {expected['active_ref']}, got "
            f"{metrics['last_inventory_receipt']}"
        )
    if metrics["pending_inventory_receipts"] != 0:
        raise AssertionError(f"{scenario} receipts did not settle: {after_center}")

    page.keyboard.down("d")
    final = after_center
    completion_frames = 0
    for completion_frames in range(1, 81):
        page.wait_for_timeout(100)
        final = state(page)
        if final["terminal"]["isTerminal"] or not final["game_state"]["player"]["alive"]:
            break
    page.keyboard.up("d")
    page.screenshot(path=str(evidence_dir / f"{scenario}-final.png"))

    if not final["game_state"]["player"]["alive"]:
        raise AssertionError(f"{scenario} player died before the flag: {final}")
    if (
        not final["terminal"]["isTerminal"]
        or final["terminal"]["outcome"] != "success"
        or final["metrics"]["coins"] != expected["total_units"]
        or final["metrics"]["coins_total"] != expected["total_units"]
    ):
        raise AssertionError(f"{scenario} Level 3 did not complete: {final}")

    return {
        "scenario": scenario,
        "initial": initial,
        "after_center": after_center,
        "final": final,
        "replay": {
            "trigger_frames": trigger_frames,
            "completion_frames": completion_frames,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:4173/?benchmark=1&level=3",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("verifier-artifacts"),
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    contract_server = start_contract_service()
    results = []
    try:
        with sync_playwright() as playwright:
            launch_options = {"headless": True}
            executable = os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE")
            if executable:
                launch_options["executable_path"] = executable
            browser = playwright.chromium.launch(**launch_options)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            for scenario in ("primary", "secondary"):
                results.append(
                    replay(page, args.url, scenario, args.evidence_dir)
                )
            browser.close()
    finally:
        if contract_server:
            with suppress(Exception):
                contract_server.shutdown()
                contract_server.server_close()

    evidence = {"status": "pass", "scenarios": results}
    (args.evidence_dir / "state-replay.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "status": "pass",
                "scenarios": 2,
                "totals": [2, 3],
                "terminal": "success",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
