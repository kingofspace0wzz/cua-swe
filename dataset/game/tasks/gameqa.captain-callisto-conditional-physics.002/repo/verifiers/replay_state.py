#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def state(page):
    return page.evaluate("window.gameAPI.getState()")


def write_evidence(path: Path, evidence: dict) -> None:
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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

    evidence = {"post_release_samples": []}
    failure = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--single-process", "--autoplay-policy=no-user-gesture-required"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        replay_url = args.url
        try:
            page.goto(replay_url, wait_until="load")
        except Exception:
            if not replay_url.startswith("http://127.0.0.1"):
                raise
            replay_url = (
                Path("dist/index.html").resolve().as_uri()
                + "?benchmark=1&level=3"
            )
            page.goto(replay_url, wait_until="load")
        evidence["transport_url"] = replay_url
        page.wait_for_function("window.gameAPI && window.gameAPI.getState")
        page.evaluate("window.gameAPI.reset({seed: 44, level: 3})")
        page.wait_for_timeout(80)

        initial = state(page)
        evidence["initial"] = initial
        page.screenshot(path=str(args.evidence_dir / "initial.png"))
        if (
            initial["metrics"]["coins"] != 0
            or initial["metrics"]["remaining_coins"] != 0
            or initial["game_state"]["level"] != 3
        ):
            failure = f"invalid Level 3 lift lane: {initial}"

        pre_release = None
        page.keyboard.down("d")
        page.keyboard.down("Shift")
        for _ in range(180):
            page.wait_for_timeout(25)
            current = state(page)
            if current["game_state"]["player"]["x"] >= 14:
                pre_release = current
                break
            if not current["game_state"]["player"]["alive"]:
                break
        evidence["pre_release"] = pre_release
        page.screenshot(path=str(args.evidence_dir / "pre-release.png"))
        if failure is None and pre_release is None:
            failure = "the D+Shift approach did not clear the first lift"

        page.keyboard.up("Shift")
        release_sample = state(page)
        evidence["release"] = release_sample
        release_x = release_sample["game_state"]["player"]["x"]
        minimum_x = release_x
        maximum_x = release_x
        for _ in range(36):
            page.wait_for_timeout(25)
            current = state(page)
            evidence["post_release_samples"].append(current)
            current_x = current["game_state"]["player"]["x"]
            minimum_x = min(minimum_x, current_x)
            maximum_x = max(maximum_x, current_x)
        evidence["post_release_window"] = {
            "release_x": release_x,
            "minimum_x": minimum_x,
            "maximum_x": maximum_x,
            "leftward_delta": release_x - minimum_x,
            "forward_delta": maximum_x - release_x,
        }
        page.screenshot(path=str(args.evidence_dir / "post-release.png"))

        page.keyboard.up("d")
        final = evidence["post_release_samples"][-1]
        landed = None
        for _ in range(480):
            page.wait_for_timeout(25)
            final = state(page)
            if final["debug"]["grounded"]:
                landed = final
                break
            if (
                not final["game_state"]["player"]["alive"]
                or final["game_state"]["player"]["y"] > 140
            ):
                break
        evidence["landed"] = landed
        page.screenshot(path=str(args.evidence_dir / "landed.png"))

        if landed is not None:
            page.keyboard.down("d")
        for _ in range(600):
            if (
                final["terminal"]["isTerminal"]
                or not final["game_state"]["player"]["alive"]
            ):
                break
            page.wait_for_timeout(25)
            final = state(page)
        page.keyboard.up("d")
        evidence["final"] = final
        page.screenshot(path=str(args.evidence_dir / "final.png"))
        browser.close()

    write_evidence(args.evidence_dir / "state-replay.json", evidence)

    if failure is not None:
        raise AssertionError(failure)
    if release_x - minimum_x > 0.35:
        raise AssertionError(
            "the astronaut veered left after Shift was released while D stayed "
            f"held: release_x={release_x:.3f}, minimum_x={minimum_x:.3f}"
        )
    if maximum_x - release_x < 2.5:
        raise AssertionError(
            "the astronaut did not preserve rightward control after the release "
            f"transition: release_x={release_x:.3f}, maximum_x={maximum_x:.3f}"
        )
    if landed is None:
        raise AssertionError(
            "the astronaut did not settle onto the landing runway after crossing "
            "the second lift"
        )
    if not final["game_state"]["player"]["alive"]:
        raise AssertionError("the astronaut died before finishing the two-lift route")
    if (
        not final["terminal"]["isTerminal"]
        or final["terminal"]["outcome"] != "success"
    ):
        raise AssertionError(f"the two-lift route did not complete: {final}")

    print(
        json.dumps(
            {
                "status": "pass",
                "release_x": release_x,
                "minimum_x": minimum_x,
                "maximum_x": maximum_x,
                "landing_x": landed["game_state"]["player"]["x"],
                "terminal": final["terminal"]["outcome"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
