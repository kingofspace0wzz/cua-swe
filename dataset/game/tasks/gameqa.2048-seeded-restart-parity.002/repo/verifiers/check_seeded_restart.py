#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Page, sync_playwright


SEEDS = (42, 1337, 3735928559)
MOVES = ("ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft")


def snapshot(page: Page) -> dict[str, Any]:
    state = page.evaluate("window.gameAPI.getState()")
    columns = state["game_state"]["environment"]
    size = len(columns)
    return {
        "seed": state["seed"],
        "board": [[columns[x][y] for x in range(size)] for y in range(size)],
        "score": state["game_state"]["score"],
        "filled_cells": state["metrics"]["filled_cells"],
        "max_tile": state["metrics"]["max_tile"],
    }


def reset(page: Page, seed: int) -> dict[str, Any]:
    result = page.evaluate("seed => window.gameAPI.reset({seed})", seed)
    if not result["ok"]:
        raise AssertionError(f"reset failed for seed {seed}: {result}")
    page.wait_for_timeout(80)
    return snapshot(page)


def play(page: Page) -> list[dict[str, Any]]:
    rows = []
    for key in MOVES:
        page.keyboard.press(key)
        page.wait_for_timeout(30)
        rows.append(snapshot(page))
    return rows


def held_restart(page: Page, restart: Callable[[Page], None]) -> dict[str, Any]:
    page.keyboard.down("ArrowLeft")
    page.wait_for_timeout(40)
    restart(page)
    page.wait_for_timeout(320)
    page.keyboard.up("ArrowLeft")
    page.wait_for_timeout(80)
    return snapshot(page)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:4394/")
    parser.add_argument("--evidence-dir", type=Path, default=Path("verifier-artifacts"))
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    evidence: dict[str, Any] = {"url": args.url, "seeds": {}, "failures": failures}
    restart_paths: tuple[tuple[str, Callable[[Page], None]], ...] = (
        ("space", lambda page: page.keyboard.press("Space")),
        (
            "button",
            lambda page: page.evaluate(
                "document.querySelector('.retry-button').click()"
            ),
        ),
        ("api", lambda page: page.evaluate("window.gameAPI.restart()")),
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.gameAPI && window.__gameManager")

        for seed in SEEDS:
            seed_rows: dict[str, Any] = {}
            evidence["seeds"][str(seed)] = seed_rows
            try:
                opening = reset(page, seed)
                control = play(page)
                seed_rows["opening"] = opening
                seed_rows["control"] = control

                for label, restart_path in restart_paths:
                    reset(page, seed)
                    play(page)
                    after_restart = held_restart(page, restart_path)
                    seed_rows[label] = {"after_restart": after_restart}
                    if after_restart != opening:
                        failures.append(
                            f"seed {seed} {label}: held input advanced the fresh "
                            f"episode: expected={opening}, actual={after_restart}"
                        )
                        continue
                    replay = play(page)
                    seed_rows[label]["replay"] = replay
                    if replay != control:
                        failures.append(
                            f"seed {seed} {label}: post-restart replay diverged"
                        )

                reset(page, seed)
                before_hold = snapshot(page)
                page.keyboard.down("ArrowRight")
                page.wait_for_timeout(340)
                page.keyboard.up("ArrowRight")
                page.wait_for_timeout(80)
                after_hold = snapshot(page)
                seed_rows["ordinary_hold"] = {
                    "before": before_hold,
                    "after": after_hold,
                }
                if after_hold == before_hold:
                    failures.append(
                        f"seed {seed}: ordinary held-key repeat was disabled"
                    )

                if seed == 42:
                    page.screenshot(
                        path=str(args.evidence_dir / "seed-42-final.png")
                    )
            except Exception as error:  # noqa: BLE001
                failures.append(f"seed {seed}: {error}")
        browser.close()

    (args.evidence_dir / "seeded-restart-state.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        raise AssertionError("; ".join(failures))
    print(json.dumps({"status": "pass", "seeds": list(SEEDS)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
