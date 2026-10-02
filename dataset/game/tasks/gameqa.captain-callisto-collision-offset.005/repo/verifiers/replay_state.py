#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def state(page):
    return page.evaluate("window.gameAPI.getState()")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:44319/?benchmark=1&level=4",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("verifier-artifacts"),
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--single-process"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.gameAPI && window.gameAPI.getState")
        page.evaluate("window.gameAPI.reset({seed: 45, level: 4})")
        page.wait_for_timeout(250)

        initial = state(page)
        page.screenshot(path=str(args.evidence_dir / "initial.png"))
        if initial["metrics"]["coins"] != 0 or initial["metrics"]["remaining_coins"] != 3:
            raise AssertionError(f"invalid initial state: {initial}")
        if initial["game_state"]["player"]["fuel"] < 90:
            raise AssertionError(f"launch fuel was not initialized: {initial}")

        # Build a diagonal northeast trajectory, then release only the jetpack
        # while the movement keys remain held.
        page.keyboard.down("d")
        page.keyboard.down("w")
        page.keyboard.down("Shift")
        ascent_samples = []
        for _ in range(100):
            page.wait_for_timeout(20)
            sample = state(page)
            ascent_samples.append(sample)
            if sample["game_state"]["player"]["x"] >= 8.0:
                break
        before_release = ascent_samples[-1]
        page.screenshot(path=str(args.evidence_dir / "before-release.png"))
        if before_release["game_state"]["player"]["x"] < 8.0:
            raise AssertionError(f"northeast launch checkpoint was not reached: {before_release}")
        if before_release["game_state"]["player"]["velocity_y"] <= 0:
            raise AssertionError(f"jetpack ascent was not established: {before_release}")

        page.keyboard.up("Shift")
        descent_samples = []
        corner_locked = False
        clipped = None
        movement_released = False
        settled_on_deck = False
        slot_compact = False
        approach_expanded = False
        slot_sample = None
        approach_sample = None
        final = before_release
        for _ in range(240):
            page.wait_for_timeout(25)
            final = state(page)
            descent_samples.append(final)
            if (
                not movement_released
                and final["game_state"]["player"]["x"] >= 10.0
                and final["game_state"]["player"]["z"] >= 10.0
            ):
                page.keyboard.up("d")
                page.keyboard.up("w")
                movement_released = True
            if (
                final["game_state"]["player"]["velocity_y"] < 0
                and slot_sample is None
            ):
                slot_sample = final
                if final["debug"]["collision_radius"] <= 0.3:
                    slot_compact = True
                else:
                    page.keyboard.up("d")
                    page.keyboard.up("w")
                    page.screenshot(path=str(args.evidence_dir / "slot-blocked.png"))
                    browser.close()
                    evidence = {
                        "initial": initial,
                        "before_release": before_release,
                        "slot_sample": slot_sample,
                        "trajectory": {
                            "slot_compact": False,
                            "collision_radius": final["debug"]["collision_radius"],
                        },
                    }
                    (args.evidence_dir / "state-replay.json").write_text(
                        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    raise AssertionError(
                        "the astronaut did not retain the compact envelope "
                        "through the descending slot"
                    )
            if (
                final["game_state"]["player"]["velocity_y"] < 0
                and final["game_state"]["player"]["z"] >= 11.1
                and final["debug"]["collision_radius"] >= 0.65
            ):
                approach_expanded = True
                approach_sample = final
            if final["debug"]["corner_locked"]:
                corner_locked = True
                clipped = final
                page.screenshot(path=str(args.evidence_dir / "corner-contact.png"))
                break
            if (
                movement_released
                and 6.8 <= final["game_state"]["player"]["y"] <= 7.1
                and abs(final["game_state"]["player"]["velocity_x"]) <= 0.5
                and abs(final["game_state"]["player"]["velocity_z"]) <= 0.5
            ):
                settled_on_deck = True
                break
            if final["terminal"]["isTerminal"] or not final["game_state"]["player"]["alive"]:
                break

        if corner_locked:
            # Keep pushing northeast. A trapped mutant cannot leave the contact
            # even though both movement keys remain physically held.
            trapped_start = clipped
            page.keyboard.down("d")
            page.keyboard.down("w")
            page.wait_for_timeout(1200)
            trapped_end = state(page)
            page.screenshot(path=str(args.evidence_dir / "trapped.png"))
            page.keyboard.up("d")
            page.keyboard.up("w")
            browser.close()

            evidence = {
                "initial": initial,
                "before_release": before_release,
                "corner_contact": trapped_start,
                "trapped_end": trapped_end,
                "trajectory": {
                    "corner_locked": True,
                    "displacement_while_pushing": (
                        abs(
                            trapped_end["game_state"]["player"]["x"]
                            - trapped_start["game_state"]["player"]["x"]
                        )
                        + abs(
                            trapped_end["game_state"]["player"]["z"]
                            - trapped_start["game_state"]["player"]["z"]
                        )
                    ),
                },
            }
            (args.evidence_dir / "state-replay.json").write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            raise AssertionError(
                "the astronaut clipped into the northeast corner and remained trapped"
            )

        if not settled_on_deck:
            page.keyboard.up("d")
            page.keyboard.up("w")
            browser.close()
            raise AssertionError(f"the astronaut did not settle on the corner deck: {final}")
        if not slot_compact or not approach_expanded:
            browser.close()
            raise AssertionError(
                "the post-release envelope did not complete compact-slot and "
                f"expanded-corner phases: compact={slot_compact} "
                f"expanded={approach_expanded}"
            )
        if final["terminal"]["isTerminal"]:
            page.keyboard.up("d")
            page.keyboard.up("w")
            browser.close()
            raise AssertionError("the level completed before the deck opening was replayed")

        # Align on the deck with the opening center, then cross north.
        page.keyboard.down("d")
        alignment_samples = []
        for _ in range(160):
            page.wait_for_timeout(25)
            final = state(page)
            alignment_samples.append(final)
            if final["game_state"]["player"]["x"] >= 14.4:
                break
            if final["terminal"]["isTerminal"] or not final["game_state"]["player"]["alive"]:
                break
        page.keyboard.up("d")
        coast_samples = []
        for _ in range(120):
            page.wait_for_timeout(25)
            final = state(page)
            coast_samples.append(final)
            if abs(final["game_state"]["player"]["velocity_x"]) <= 0.5:
                break
        page.screenshot(path=str(args.evidence_dir / "gate-aligned.png"))
        if not 15.7 <= final["game_state"]["player"]["x"] <= 16.3:
            page.keyboard.up("w")
            browser.close()
            raise AssertionError(f"the astronaut could not align with the deck opening: {final}")

        gate_crossed = final["game_state"]["player"]["z"] >= 16.65
        gate_samples = []
        if not gate_crossed:
            page.keyboard.down("w")
            for _ in range(160):
                page.wait_for_timeout(25)
                final = state(page)
                gate_samples.append(final)
                if final["game_state"]["player"]["z"] >= 16.65:
                    gate_crossed = True
                    break
                if final["terminal"]["isTerminal"] or not final["game_state"]["player"]["alive"]:
                    break
            page.keyboard.up("w")
        else:
            page.keyboard.up("w")

        if not gate_crossed:
            page.screenshot(path=str(args.evidence_dir / "gate-blocked.png"))
            browser.close()
            evidence = {
                "initial": initial,
                "before_release": before_release,
                "final": final,
                "trajectory": {
                    "corner_locked": False,
                    "gate_crossed": False,
                    "gate_sample_count": len(gate_samples),
                    "maximum_gate_z": max(
                        sample["game_state"]["player"]["z"]
                        for sample in gate_samples
                    ),
                },
            }
            (args.evidence_dir / "state-replay.json").write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            raise AssertionError(
                "the astronaut cleared the corner but could not fit through "
                "the narrow deck opening"
            )

        page.screenshot(path=str(args.evidence_dir / "gate-crossed.png"))
        page.keyboard.down("d")
        page.keyboard.down("w")
        for _ in range(240):
            if final["terminal"]["isTerminal"] or not final["game_state"]["player"]["alive"]:
                break
            page.wait_for_timeout(50)
            final = state(page)
            descent_samples.append(final)
        page.keyboard.up("d")
        page.keyboard.up("w")
        page.screenshot(path=str(args.evidence_dir / "final.png"))
        browser.close()

    evidence = {
        "initial": initial,
        "before_release": before_release,
        "slot_sample": slot_sample,
        "approach_sample": approach_sample,
        "final": final,
        "trajectory": {
            "corner_locked": False,
            "slot_compact": slot_compact,
            "approach_expanded": approach_expanded,
            "gate_crossed": gate_crossed,
            "ascent_sample_count": len(ascent_samples),
            "descent_sample_count": len(descent_samples),
            "alignment_sample_count": len(alignment_samples),
            "coast_sample_count": len(coast_samples),
            "gate_sample_count": len(gate_samples),
            "minimum_corner_distance": min(
                (
                    (sample["game_state"]["player"]["x"] - 11) ** 2
                    + (sample["game_state"]["player"]["z"] - 11) ** 2
                )
                ** 0.5
                for sample in descent_samples
            ),
        },
    }
    (args.evidence_dir / "state-replay.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if not final["game_state"]["player"]["alive"]:
        raise AssertionError("the astronaut died after clearing the corner")
    if final["metrics"]["coins"] != 3:
        raise AssertionError(f"expected all three corner-lane coins: {final}")
    if not final["terminal"]["isTerminal"] or final["terminal"]["outcome"] != "success":
        raise AssertionError(f"corner lane did not complete: {final}")
    print(
        json.dumps(
            {
                "status": "pass",
                "corner_clear": True,
                "gate_crossed": True,
                "terminal": "success",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
