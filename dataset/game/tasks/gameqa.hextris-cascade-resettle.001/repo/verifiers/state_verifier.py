#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page, sync_playwright


def protected_state(page: Page) -> dict:
    return page.evaluate("window.__cuaSweInspectHextrisCascadeFixture()")


def wait_for(
    page: Page,
    predicate: Callable[[dict], bool],
    *,
    timeout_ms: int = 6000,
    interval_ms: int = 20,
) -> tuple[dict, list[dict]]:
    samples: list[dict] = []
    for _ in range(max(1, timeout_ms // interval_ms)):
        observed = protected_state(page)
        samples.append(observed)
        if predicate(observed):
            return observed, samples
        page.wait_for_timeout(interval_ms)
    return samples[-1], samples


def reset_and_inject(page: Page, fixture_source: str, *, pair_only: bool = False) -> dict:
    result = page.evaluate(
        """async () => {
          const reset = await window.gameAPI.reset({level: 1});
          if (!reset.ok) throw new Error("gameAPI reset failed: " + JSON.stringify(reset));
          return reset;
        }"""
    )
    page.wait_for_timeout(50)
    page.evaluate(fixture_source)
    initial = page.evaluate(
        "(pairOnly) => window.__cuaSweInstallHextrisCascadeFixture({pairOnly})",
        pair_only,
    )
    initial["reset"] = result
    return initial


def run_primary(page: Page, fixture_source: str, evidence_dir: Path) -> dict:
    initial = reset_and_inject(page, fixture_source)
    if (
        initial["score"] != 0
        or initial["position"] != 0
        or initial["activeBlocks"] != 1
        or initial["api"]["game_state"]["environment"]["settled_blocks"] != 7
    ):
        raise AssertionError("invalid protected initial state: " + json.dumps(initial))

    page.screenshot(path=str(evidence_dir / "primary-initial.png"))
    page.wait_for_timeout(100)
    page.keyboard.press("ArrowLeft")

    rotated, _ = wait_for(page, lambda item: item["position"] == 1, timeout_ms=1000)
    if rotated["position"] != 1:
        raise AssertionError("ArrowLeft did not rotate exactly one lane")

    first_clear, first_samples = wait_for(
        page, lambda item: item["score"] >= 9, timeout_ms=5000
    )
    if first_clear["score"] != 9:
        raise AssertionError(
            "first clear did not stop at 9: " + json.dumps(first_clear)
        )
    page.screenshot(path=str(evidence_dir / "primary-first-clear.png"))

    final, cascade_samples = wait_for(
        page, lambda item: item["score"] >= 41, timeout_ms=6000
    )
    trace = final["consolidationTrace"]
    premature = []
    waited_for_unrelated = []
    protected_names = (
        "cascade_mobile_a_v1",
        "cascade_mobile_b_v1",
        "cascade_mobile_c_v2",
    )
    for entry in trace:
        if entry["after_score"] <= entry["before_score"]:
            continue
        roles = entry["roles"]
        if any(
            name in roles and roles[name]["settled"] is not True
            for name in protected_names
        ):
            premature.append(entry)
        if (
            entry["before_score"] == 9
            and entry["after_score"] > 9
            and roles.get("unrelated_green_v3", {}).get("settled") is True
        ):
            waited_for_unrelated.append(entry)
    if premature:
        raise AssertionError(
            "cascade scored while a protected blue block was airborne: "
            + json.dumps(premature)
        )
    if waited_for_unrelated:
        raise AssertionError(
            "blue cascade incorrectly waited for an unrelated color to settle: "
            + json.dumps(waited_for_unrelated)
        )
    if final["score"] != 41:
        raise AssertionError(
            "settled blue cascade did not score exactly once: " + json.dumps(final)
        )

    cleared, empty_samples = wait_for(
        page,
        lambda item: (
            not any(name in item["roles"] for name in protected_names)
            and item["api"]["game_state"]["environment"]["settled_blocks"] == 1
            and item["activeBlocks"] == 0
        ),
        timeout_ms=5000,
    )
    if (
        any(name in cleared["roles"] for name in protected_names)
        or cleared["api"]["game_state"]["environment"]["settled_blocks"] != 1
        or cleared["activeBlocks"] != 0
    ):
        raise AssertionError(
            "blue cohort did not clear independently: " + json.dumps(cleared)
        )
    page.screenshot(path=str(evidence_dir / "primary-final.png"))

    return {
        "initial": initial,
        "first_clear": first_clear,
        "final": cleared,
        "sample_counts": {
            "first_clear": len(first_samples),
            "cascade": len(cascade_samples),
            "empty": len(empty_samples),
        },
    }


def run_no_rotation(page: Page, fixture_source: str, evidence_dir: Path) -> dict:
    initial = reset_and_inject(page, fixture_source)
    final, samples = wait_for(
        page, lambda item: item["activeBlocks"] == 0, timeout_ms=6000
    )
    if final["score"] != 0:
        raise AssertionError(
            "no-rotation control unexpectedly scored: " + json.dumps(final)
        )
    page.screenshot(path=str(evidence_dir / "no-rotation-final.png"))
    return {"initial": initial, "final": final, "samples": len(samples)}


def run_pair_only(page: Page, fixture_source: str, evidence_dir: Path) -> dict:
    initial = reset_and_inject(page, fixture_source, pair_only=True)
    page.wait_for_timeout(100)
    page.keyboard.press("ArrowLeft")
    final, samples = wait_for(
        page, lambda item: item["activeBlocks"] == 0, timeout_ms=6000
    )
    if final["score"] != 0:
        raise AssertionError("pair-only control scored: " + json.dumps(final))
    page.screenshot(path=str(evidence_dir / "pair-only-final.png"))
    return {"initial": initial, "final": final, "samples": len(samples)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:4173/?benchmark=1&level=1",
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("verifier-artifacts"),
    )
    args = parser.parse_args()

    fixture = args.fixture.expanduser().resolve()
    if not fixture.is_file():
        raise FileNotFoundError(
            "protected Hextris fixture is unavailable; set "
            "CUA_SWE_HEXTRIS_FIXTURE to the evaluator-owned file"
        )
    fixture_source = fixture.read_text(encoding="utf-8")
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    launch_options: dict[str, object] = {"headless": True}
    executable = os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE")
    if executable:
        launch_options["executable_path"] = executable

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.gameAPI && window.gameAPI.getState")
        evidence = {
            "status": "pass",
            "primary": run_primary(page, fixture_source, args.evidence_dir),
            "no_rotation": run_no_rotation(page, fixture_source, args.evidence_dir),
            "pair_only": run_pair_only(page, fixture_source, args.evidence_dir),
        }
        browser.close()

    evidence_path = args.evidence_dir / "state-replay.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "pass",
                "final_score": evidence["primary"]["final"]["score"],
                "negative_controls": 2,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
