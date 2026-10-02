#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def state(page):
    return page.evaluate("window.gameAPI.getState()")


def wait_game_delta(page, start_time: float, delta: float) -> None:
    page.wait_for_function(
        "target => window.gameAPI.getState().game_state.elapsed_time >= target",
        arg=start_time + delta,
        timeout=8000,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:4392/?benchmark=1&level=3",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("verifier-artifacts"),
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    failures = []
    pulses = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.gameAPI && window.gameAPI.getState")
        page.evaluate("window.gameAPI.reset({seed: 44, level: 3})")
        page.wait_for_function("window.gameAPI.getState().is_actionable")
        initial = state(page)
        page.screenshot(path=str(args.evidence_dir / "initial.png"))

        page.keyboard.down("d")
        for pulse_index in range(3):
            before = state(page)
            page.keyboard.down("Shift")
            page.wait_for_function(
                "window.gameAPI.getState().game_state.player.jetpack_visible"
            )
            ignition = state(page)
            wait_game_delta(
                page,
                ignition["game_state"]["elapsed_time"],
                0.12,
            )
            early = state(page)
            page.screenshot(
                path=str(
                    args.evidence_dir
                    / f"pulse-{pulse_index + 1}-early.png"
                )
            )

            wait_game_delta(
                page,
                ignition["game_state"]["elapsed_time"],
                0.55,
            )
            mature = state(page)
            page.keyboard.up("Shift")
            page.wait_for_function(
                "!window.gameAPI.getState().game_state.player.jetpack_visible"
            )
            release = state(page)
            wait_game_delta(
                page,
                release["game_state"]["elapsed_time"],
                0.20,
            )
            off = state(page)
            page.screenshot(
                path=str(
                    args.evidence_dir
                    / f"pulse-{pulse_index + 1}-off.png"
                )
            )

            early_fuel_use = (
                ignition["game_state"]["player"]["fuel"]
                - early["game_state"]["player"]["fuel"]
            )
            gap_fuel_use = (
                mature["game_state"]["player"]["fuel"]
                - off["game_state"]["player"]["fuel"]
            )
            velocity_decayed = (
                off["game_state"]["player"]["velocity_y"]
                < mature["game_state"]["player"]["velocity_y"] - 1.0
                or (
                    off["game_state"]["player"]["y"] <= 4.05
                    and abs(off["game_state"]["player"]["velocity_y"]) < 0.3
                )
            )
            pulse = {
                "before": before,
                "ignition": ignition,
                "early": early,
                "mature": mature,
                "release": release,
                "off": off,
                "measurements": {
                    "early_fuel_use": early_fuel_use,
                    "gap_fuel_use": gap_fuel_use,
                    "velocity_decayed": velocity_decayed,
                },
            }
            pulses.append(pulse)

            if early_fuel_use > 2.2:
                failures.append(
                    f"pulse {pulse_index + 1} reached full output before "
                    f"the visible ignition envelope matured: {early_fuel_use:.3f}"
                )
            if off["game_state"]["player"]["jetpack_visible"]:
                failures.append(
                    f"pulse {pulse_index + 1} exhaust remained visible in the gap"
                )
            if gap_fuel_use > 1.0:
                failures.append(
                    f"pulse {pulse_index + 1} consumed fuel after release: "
                    f"{gap_fuel_use:.3f}"
                )
            if not velocity_decayed:
                failures.append(
                    f"pulse {pulse_index + 1} vertical velocity did not decay "
                    "during the visible gap"
                )

        page.keyboard.up("d")
        if failures:
            final = state(page)
        else:
            page.wait_for_function(
                "window.gameAPI.getState().game_state.player.y <= 4.1",
                timeout=10000,
            )
            final = state(page)
            active_key = None
            for _ in range(300):
                if final["terminal"]["isTerminal"]:
                    break
                target = (
                    final["game_state"]["environment"]["nearest_coin"]
                    or final["game_state"]["environment"]["nearest_exit"]
                )
                if target is None:
                    break
                desired_key = (
                    "d"
                    if target["x"] >= final["game_state"]["player"]["x"]
                    else "a"
                )
                if desired_key != active_key:
                    if active_key is not None:
                        page.keyboard.up(active_key)
                    page.keyboard.down(desired_key)
                    active_key = desired_key
                page.wait_for_timeout(100)
                final = state(page)
                if not final["game_state"]["player"]["alive"]:
                    break
            if active_key is not None:
                page.keyboard.up(active_key)
        page.screenshot(path=str(args.evidence_dir / "final.png"))
        browser.close()

    if not failures and final["metrics"]["coins"] != 3:
        failures.append(
            f"expected all three pulse-lane coins, got {final['metrics']['coins']}"
        )
    if not failures and not final["terminal"]["isTerminal"]:
        failures.append("pulse lane did not complete")

    evidence = {
        "url": args.url,
        "initial": initial,
        "pulses": pulses,
        "final": final,
        "failures": failures,
    }
    (args.evidence_dir / "state-replay.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        raise AssertionError("; ".join(failures))
    print(json.dumps({"status": "pass", "pulses": 3, "coins": 3}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
