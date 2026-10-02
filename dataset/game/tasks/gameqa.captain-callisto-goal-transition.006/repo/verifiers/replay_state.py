#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def state(page):
    return page.evaluate("window.gameAPI.getState()")


def wait_for(page, predicate, *, samples=360, interval_ms=25):
    observed = state(page)
    snapshots = [observed]
    for sample in range(samples + 1):
        if predicate(observed):
            return observed, sample, snapshots
        page.wait_for_timeout(interval_ms)
        observed = state(page)
        snapshots.append(observed)
    return observed, samples, snapshots


def write_evidence(path: Path, evidence: dict) -> None:
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:42731/?benchmark=1&level=6",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("verifier-artifacts"),
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    failure = None
    evidence = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--single-process", "--autoplay-policy=no-user-gesture-required"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.gameAPI && window.gameAPI.getState")
        page.evaluate("window.gameAPI.reset({seed: 47, level: 6})")
        page.wait_for_timeout(250)

        initial = state(page)
        evidence["initial"] = initial
        page.screenshot(path=str(args.evidence_dir / "initial.png"))
        if (
            initial["metrics"]["coins"] != 0
            or initial["metrics"]["remaining_coins"] != 3
            or initial["terminal"]["isTerminal"]
            or initial["game_state"]["player"]["fuel"] != 100
        ):
            failure = f"invalid initial Level 6 stair state: {initial}"

        second_coin = initial
        second_samples = []
        page.keyboard.down("d")
        if failure is None:
            second_coin, _, second_samples = wait_for(
                page,
                lambda item: item["metrics"]["coins"] >= 2,
            )
            if second_coin["metrics"]["coins"] != 2:
                failure = f"stair route did not reach the second coin cleanly: {second_coin}"
        evidence["second_coin"] = second_coin

        final_coin = second_coin
        final_coin_samples = []
        if failure is None:
            final_coin, _, final_coin_samples = wait_for(
                page,
                lambda item: item["metrics"]["coins"] == 3,
            )
            if (
                final_coin["metrics"]["remaining_coins"] != 0
                or not final_coin["game_state"]["player"]["alive"]
            ):
                failure = f"final stair coin checkpoint was invalid: {final_coin}"
        evidence["final_stair_coin"] = final_coin
        page.screenshot(path=str(args.evidence_dir / "final-stair-coin.png"))

        pre_exit = final_coin
        pre_exit_samples = []
        if failure is None:
            pre_exit, _, pre_exit_samples = wait_for(
                page,
                lambda item: item["game_state"]["player"]["x"] >= 30.5,
                samples=120,
            )
            exit_state = pre_exit["game_state"]["environment"]["nearest_exit"]
            if (
                exit_state is None
                or exit_state["distance"] <= 2
                or exit_state["distance"] >= 3.5
            ):
                failure = f"stair approach did not stop outside the exit radius: {pre_exit}"
        evidence["pre_exit"] = pre_exit
        page.screenshot(path=str(args.evidence_dir / "pre-exit.png"))

        preview = pre_exit
        preview_samples = []
        if failure is None:
            page.keyboard.down("Shift")
            preview, _, preview_samples = wait_for(
                page,
                lambda item: (
                    item["debug"]["level_completion"] is not None
                    or item["terminal"]["isTerminal"]
                ),
                samples=180,
            )
            if (
                preview["debug"]["level_completion"] is None
                and not preview["terminal"]["isTerminal"]
            ):
                failure = (
                    "held forward+jetpack never opened the visible success stage: "
                    f"{preview}"
                )
        evidence["visible_success"] = preview
        page.screenshot(path=str(args.evidence_dir / "visible-success.png"))

        final = preview
        settle_samples = []
        if failure is None:
            final, _, settle_samples = wait_for(
                page,
                lambda item: (
                    item["terminal"]["isTerminal"]
                    or item["debug"]["level_completion"] is None
                ),
                samples=180,
            )
        page.keyboard.up("Shift")
        page.keyboard.up("d")
        page.wait_for_timeout(250)
        final = state(page)
        evidence["final"] = final
        evidence["sample_counts"] = {
            "to_second_coin": len(second_samples),
            "to_final_coin": len(final_coin_samples),
            "to_pre_exit": len(pre_exit_samples),
            "to_visible_success": len(preview_samples),
            "to_settle": len(settle_samples),
        }
        page.screenshot(path=str(args.evidence_dir / "final.png"))
        browser.close()

    write_evidence(args.evidence_dir / "state-replay.json", evidence)

    if failure is not None:
        raise AssertionError(failure)
    if preview["metrics"]["coins"] != 3:
        raise AssertionError(f"success preview did not follow the final stair coin: {preview}")
    if (
        preview["debug"]["level_completion"] is None
        and not preview["terminal"]["isTerminal"]
    ):
        raise AssertionError(f"success preview was not staged: {preview}")
    if (
        not final["terminal"]["isTerminal"]
        or final["terminal"]["outcome"] != "success"
        or final["debug"]["game_state"] != 5
    ):
        raise AssertionError(
            "the visible success stage did not commit and the level returned to "
            "playing: " + json.dumps(final, sort_keys=True)
        )
    print(
        json.dumps(
            {
                "status": "pass",
                "coins": final["metrics"]["coins"],
                "preview_ticket": (
                    preview["debug"]["level_completion"]["ticket"]
                    if preview["debug"]["level_completion"] is not None
                    else None
                ),
                "terminal": final["terminal"]["outcome"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
