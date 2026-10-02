#!/usr/bin/env python3
"""Protected deterministic Chromium replay for the Core Ball contract."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


URL = os.environ.get("CUA_SWE_WEB_URL", "http://127.0.0.1:51200/?scenario=contract")
ARTIFACTS = Path(os.environ.get("CUA_SWE_VERIFIER_ARTIFACTS", "verifier-artifacts"))
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def close(actual: float, expected: float, tolerance: float = 0.02) -> bool:
    return math.isclose(float(actual), expected, abs_tol=tolerance)


def main() -> int:
    checks: list[dict[str, Any]] = []
    checkpoints: dict[str, Any] = {}
    console_errors: list[str] = []

    def check(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    def state(page: Any, name: str) -> dict[str, Any]:
        value = page.evaluate("window.gameAPI.getState()")
        checkpoints[name] = value
        return value

    def shot(page: Any, name: str) -> None:
        page.locator("#game").screenshot(path=str(ARTIFACTS / f"{name}.png"))

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.goto(URL, wait_until="networkidle", timeout=30_000)
            page.wait_for_function("window.gameAPI && window.gameAPI.getState")
            page.evaluate("window.gameAPI.reset({seed: 808, level: 1, manual: true})")
            shot(page, "initial")
            page.locator("#start").click()

            canvas = page.locator("#game")
            canvas.click(position={"x": 380, "y": 610})
            page.evaluate("window.gameAPI.advance(7000)")
            canvas.click(position={"x": 380, "y": 610})
            queued = state(page, "queue_window")
            queue_text = page.locator("#queue-state").inner_text()
            shot(page, "queue-window")
            check(
                "ordinary_coordinate_queue_window",
                queued["round"]["phase"] == "playing"
                and queued["shots"]["waiting"] == 1
                and 0.3 < queued["shots"]["active"]["progress"] < 0.4
                and queued["metrics"]["inputs"] == 2
                and close(queued["motion"]["angle"], 252)
                and queue_text == "NEXT PIN READY",
                {"state": queued, "queue_text": queue_text},
            )

            page.evaluate("window.gameAPI.advance(12000)")
            before_first = state(page, "pre_first_contact")
            shot(page, "pre-first-contact")
            check(
                "long_visible_first_flight_preserves_queue",
                before_first["round"]["phase"] == "playing"
                and before_first["metrics"]["attachments"] == 0
                and before_first["shots"]["waiting"] == 1
                and close(before_first["shots"]["active"]["progress"], 0.95)
                and close(before_first["motion"]["angle"], 324)
                and before_first["occupancy"]["pins"] == [180, 300, 359],
                before_first,
            )

            page.evaluate("window.gameAPI.advance(1000)")
            first = state(page, "first_attachment_commit")
            shot(page, "pace-transition")
            promoted_after_commit = (
                first["round"]["phase"] == "playing"
                and first["metrics"]["attachments"] == 1
                and first["round"]["remaining"] == 3
                and first["motion"]["transition"]["active"]
                and first["shots"]["waiting"] == 0
                and first["shots"]["active"] is not None
                and first["shots"]["active"]["launchProfile"] == "shifting"
                and first["shots"]["active"]["flightTime"] == 710
                and close(first["lastAttachment"]["localAngle"], 90)
            )
            check("waiting_shot_promoted_from_committed_pace", promoted_after_commit, first)

            page.evaluate("window.gameAPI.advance(700)")
            approach = state(page, "second_approach")
            shot(page, "second-approach")
            check(
                "visible_followup_approaches_open_gap",
                approach["round"]["phase"] == "playing"
                and approach["metrics"]["attachments"] == 1
                and approach["shots"]["active"] is not None
                and approach["shots"]["active"]["progress"] > 0.9
                and close(approach["motion"]["angle"], 58.275)
                and approach["metrics"]["failures"] == 0,
                approach,
            )

            page.evaluate("window.gameAPI.advance(80)")
            after = state(page, "post_trigger")
            shot(page, "post-trigger")
            aligned = (
                promoted_after_commit
                and after["round"]["phase"] == "playing"
                and after["metrics"]["attachments"] == 2
                and after["metrics"]["failures"] == 0
                and after["round"]["remaining"] == 2
                and close(after["scenario"]["timeMs"], 20780)
                and close(after["motion"]["angle"], 69.147)
                and close(after["lastAttachment"]["at"], 20710)
                and close(after["lastAttachment"]["coreAngle"], 59.58675)
                and close(after["lastAttachment"]["localAngle"], 30.41325)
                and after["lastAttachment"]["launchProfile"] == "shifting"
                and close(
                    (
                        after["lastAttachment"]["localAngle"]
                        + after["lastAttachment"]["coreAngle"]
                    )
                    % 360,
                    after["lastAttachment"]["worldAngle"],
                )
            )
            check("post_commit_promotion_transaction", aligned, after)

            if aligned:
                attached_angles = list(after["occupancy"]["pins"])
                page.evaluate("window.gameAPI.advance(1220)")
                persisted = state(page, "post_transition_persistence")
                shot(page, "post-transition")
                check(
                    "attachment_persists_through_pace_change",
                    persisted["round"]["phase"] == "playing"
                    and persisted["occupancy"]["pins"] == attached_angles
                    and not persisted["motion"]["transition"]["active"]
                    and close(persisted["scenario"]["timeMs"], 22000),
                    persisted,
                )

                canvas.click(position={"x": 380, "y": 610})
                page.evaluate("window.gameAPI.advance(580)")
                shot(page, "third-approach")
                page.evaluate("window.gameAPI.advance(20)")
                third = state(page, "third_attachment")
                check(
                    "ordinary_spaced_shot_after_transition",
                    third["round"]["phase"] == "playing"
                    and third["metrics"]["attachments"] == 3
                    and third["lastAttachment"]["launchProfile"] == "sprint"
                    and close(third["lastAttachment"]["localAngle"], 118.8),
                    third,
                )

                page.evaluate("window.gameAPI.advance(1000)")
                canvas.click(position={"x": 380, "y": 610})
                page.evaluate("window.gameAPI.advance(600)")
                completed = state(page, "completed")
                shot(page, "final")
                check(
                    "normal_round_completion",
                    completed["round"]["phase"] == "passed"
                    and completed["round"]["remaining"] == 0
                    and completed["metrics"]["attachments"] == 4
                    and completed["metrics"]["completed"] == 1
                    and close(completed["lastAttachment"]["localAngle"], 248.4),
                    completed,
                )
            else:
                for name in (
                    "attachment_persists_through_pace_change",
                    "ordinary_spaced_shot_after_transition",
                    "normal_round_completion",
                ):
                    check(name, False, "post-trigger contract failed")

            page.locator("#restart").click()
            restarted = state(page, "restart_before_collision_probe")
            check(
                "restart_clears_round_occupancy_and_motion",
                restarted["round"] == {"phase": "ready", "remaining": 4}
                and restarted["occupancy"]["pins"] == [180, 300, 359]
                and restarted["metrics"]
                == {"inputs": 0, "attachments": 0, "failures": 0, "completed": 0}
                and not restarted["motion"]["transition"]["active"],
                restarted,
            )

            page.locator("#start").click()
            page.evaluate("window.gameAPI.advance(2500)")
            canvas.click(position={"x": 380, "y": 610})
            page.evaluate("window.gameAPI.advance(20000)")
            rejected = state(page, "rejected_attachment_transaction")
            shot(page, "rejected-collision")
            check(
                "rejected_collision_is_not_committed",
                rejected["round"]["phase"] == "failed"
                and rejected["metrics"]["failures"] == 1
                and rejected["metrics"]["attachments"] == 0
                and rejected["lastAttachment"]["accepted"] is False
                and rejected["occupancy"]["pins"] == [180, 300, 359],
                rejected,
            )

            page.locator("#restart").click()
            final_restart = state(page, "final_restart")
            shot(page, "restart")
            check(
                "restart_remains_normal_after_rejected_collision",
                final_restart["round"] == {"phase": "ready", "remaining": 4}
                and final_restart["occupancy"]["pins"] == [180, 300, 359]
                and final_restart["metrics"]
                == {"inputs": 0, "attachments": 0, "failures": 0, "completed": 0},
                final_restart,
            )

            check("browser_console_clean", not console_errors, console_errors)
            browser.close()
    except Exception as exc:
        checks.append(
            {
                "name": "chromium_replay_completed",
                "passed": False,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )

    report = {
        "url": URL,
        "checks": checks,
        "checkpoints": checkpoints,
        "console_errors": console_errors,
        "success": bool(checks) and all(item["passed"] for item in checks),
    }
    (ARTIFACTS / "state-replay.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
