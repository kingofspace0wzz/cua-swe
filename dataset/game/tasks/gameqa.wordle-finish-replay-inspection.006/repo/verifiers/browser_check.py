#!/usr/bin/env python3
"""Protected Chromium replay for repeatable finish-motion inspection."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
FIXTURE = (WORKSPACE.parent / "env" / "challenge.json").resolve()


def game_state(page: Page) -> dict[str, Any]:
    return page.evaluate("window.gameAPI.getState()")


def type_guess(page: Page, value: str) -> None:
    page.keyboard.type(value, delay=10)
    page.keyboard.press("Enter")


def model_board_empty(snapshot: dict[str, Any]) -> bool:
    return all(
        not tile["letter"] and tile["status"] == "empty" and not tile["revealed"]
        for row in snapshot["rows"]
        for tile in row["tiles"]
    )


def presentation_board_empty(snapshot: dict[str, Any]) -> bool:
    return all(
        not tile["letter"] and tile["status"] == "empty"
        for tile in snapshot["presentation"]["tiles"]
    )


def keyboard_empty(snapshot: dict[str, Any]) -> bool:
    return all(value == "empty" for value in snapshot["keyboard"].values())


def presentation_keyboard_empty(snapshot: dict[str, Any]) -> bool:
    return all(
        value == "empty"
        for value in snapshot["presentation"]["keyboard"].values()
    )


def guidance_empty(snapshot: dict[str, Any]) -> bool:
    hard = snapshot["hardMode"]
    return not hard["minimum"] and all(value is None for value in hard["exact"])


def row_statuses(snapshot: dict[str, Any], row: int) -> list[str]:
    return [tile["status"] for tile in snapshot["rows"][row]["tiles"]]


def presentation_row(snapshot: dict[str, Any], row: int) -> list[dict[str, Any]]:
    return [
        tile
        for tile in snapshot["presentation"]["tiles"]
        if tile["row"] == row
    ]


def pixel_at(image: Image.Image, tile: dict[str, Any]) -> list[int]:
    rect = tile["motionRect"]
    x = max(0, min(image.width - 1, round(rect["x"] + rect["width"] * 0.22)))
    y = max(0, min(image.height - 1, round(rect["y"] + rect["height"] * 0.22)))
    value = image.getpixel((x, y))
    if isinstance(value, int):
        return [value, value, value]
    return list(value[:3])


def save_checkpoint(
    page: Page,
    evidence_dir: Path,
    records: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    page.evaluate(
        """
        () => {
          window.__verifierPausedAnimations = document
            .getAnimations()
            .filter((animation) => animation.playState === "running");
          window.__verifierPausedAnimations.forEach((animation) => animation.pause());
        }
        """
    )
    try:
        snapshot = game_state(page)
        screenshot = evidence_dir / f"{name}.png"
        page.screenshot(
            path=str(screenshot),
            full_page=False,
            animations="allow",
            caret="hide",
        )
        with Image.open(screenshot) as image_source:
            image = image_source.convert("RGB")
            snapshot["pixelSamples"] = {
                f'{tile["row"]}:{tile["column"]}': pixel_at(image, tile)
                for tile in snapshot["presentation"]["tiles"]
            }
        snapshot["screenshotPath"] = str(screenshot.resolve())
    finally:
        page.evaluate(
            """
            () => {
              (window.__verifierPausedAnimations || [])
                .forEach((animation) => animation.play());
              delete window.__verifierPausedAnimations;
            }
            """
        )
    records[name] = snapshot
    return snapshot


def assert_fresh(
    snapshot: dict[str, Any],
    failures: list[str],
    label: str,
) -> None:
    if not model_board_empty(snapshot):
        failures.append(f"{label}: model board was not fresh")
    if not presentation_board_empty(snapshot):
        failures.append(f"{label}: rendered board was not fresh")
    if not keyboard_empty(snapshot):
        failures.append(f"{label}: model keyboard was not fresh")
    if not presentation_keyboard_empty(snapshot):
        failures.append(f"{label}: rendered keyboard was not fresh")
    if not guidance_empty(snapshot):
        failures.append(f"{label}: hard guidance was not fresh")
    if snapshot["presentation"]["guidance"]:
        failures.append(f"{label}: rendered hard guidance was not fresh")
    if snapshot["presentation"]["resultVisible"]:
        failures.append(f"{label}: completion result remained visible")


def assert_exact_winning_model(
    snapshot: dict[str, Any],
    answer: str,
    failures: list[str],
    label: str,
) -> None:
    if row_statuses(snapshot, 0) != ["exact"] * 5:
        failures.append(f"{label}: winning model row was not exact")
    rendered = presentation_row(snapshot, 0)
    if [tile["status"] for tile in rendered] != ["exact"] * 5:
        failures.append(f"{label}: winning rendered status projection was not exact")
    for letter in set(answer):
        if snapshot["keyboard"].get(letter) != "exact":
            failures.append(f"{label}: winning model keyboard lost exact precedence")
        if snapshot["presentation"]["keyboard"].get(letter) != "exact":
            failures.append(f"{label}: winning rendered keyboard lost exact precedence")


def assert_settled_faces(
    snapshot: dict[str, Any],
    failures: list[str],
    label: str,
) -> None:
    for tile in presentation_row(snapshot, 0):
        if tile["face"] != "back":
            failures.append(
                f'{label}: tile {tile["column"]} did not show its evaluated face'
            )


def pixel_distance(left: list[int], right: list[int]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def screenshot_pixel(snapshot: dict[str, Any], x: float, y: float) -> list[int]:
    with Image.open(snapshot["screenshotPath"]) as image_source:
        image = image_source.convert("RGB")
        px = max(0, min(image.width - 1, round(x)))
        py = max(0, min(image.height - 1, round(y)))
        return list(image.getpixel((px, py))[:3])


def active_columns(
    snapshot: dict[str, Any],
    replay: bool = False,
) -> list[int]:
    columns: list[int] = []
    motion = snapshot["presentation"]["motion"]
    entries = motion["replay"]["activeTiles"] if replay else motion["activeTiles"]
    for entry in entries:
        try:
            columns.append(int(entry["id"].split(":")[-1]))
        except (KeyError, TypeError, ValueError):
            continue
    return columns


def assert_active_visual_continuity(
    snapshot: dict[str, Any],
    reference: dict[str, Any],
    expected: dict[str, Any],
    failures: list[str],
    label: str,
    replay: bool = False,
) -> None:
    columns = active_columns(snapshot, replay=replay)
    if not columns:
        failures.append(f"{label}: no result tile was visibly in motion")
        return

    current_tiles = {
        tile["column"]: tile for tile in presentation_row(snapshot, 0)
    }
    reference_tiles = {
        tile["column"]: tile for tile in presentation_row(reference, 0)
    }
    upward = []
    for column in columns:
        tile = current_tiles[column]
        before = reference_tiles[column]
        if tile["face"] != "back":
            failures.append(
                f"{label}: moving tile {column} exposed its unevaluated face"
            )
        if abs(tile["motionRect"]["x"] - before["motionRect"]["x"]) > 2:
            failures.append(
                f"{label}: moving tile {column} drifted horizontally"
            )
        if abs(tile["motionRect"]["width"] - before["motionRect"]["width"]) > 3:
            failures.append(
                f"{label}: moving tile {column} changed coordinate scale"
            )
        displacement = before["motionRect"]["y"] - tile["motionRect"]["y"]
        upward.append(displacement)
        current_pixel = snapshot["pixelSamples"][f"0:{column}"]
        reference_pixel = reference["pixelSamples"][f"0:{column}"]
        distance = pixel_distance(current_pixel, reference_pixel)
        if distance > expected["maximumReferencePixelDistance"]:
            failures.append(
                f"{label}: moving tile {column} changed evaluated-face pixels "
                f"(distance {distance:.1f})"
            )
        if displacement >= expected["minimumUpwardDisplacementPx"]:
            slot_delta = abs(tile["slotRect"]["y"] - tile["motionRect"]["y"])
            if slot_delta > 2:
                failures.append(
                    f"{label}: moving tile {column} detached from its board frame"
                )
            origin = before["slotRect"]
            anchor_x = origin["x"] + origin["width"] * 0.5
            vacated_y = origin["y"] + origin["height"] - 3
            gap_y = origin["y"] + origin["height"] + 2
            vacated_pixel = screenshot_pixel(snapshot, anchor_x, vacated_y)
            gap_pixel = screenshot_pixel(reference, anchor_x, gap_y)
            vacancy_distance = pixel_distance(vacated_pixel, gap_pixel)
            if vacancy_distance > expected["maximumVacatedPixelDistance"]:
                failures.append(
                    f"{label}: moving tile {column} left a visible board-frame "
                    f"duplicate (distance {vacancy_distance:.1f})"
                )
    if max(upward, default=0) < expected["minimumUpwardDisplacementPx"]:
        failures.append(f"{label}: result motion did not lift a winning tile")


def assert_native_motion_present(
    snapshot: dict[str, Any],
    reference: dict[str, Any],
    expected: dict[str, Any],
    failures: list[str],
    label: str,
) -> None:
    columns = active_columns(snapshot)
    if not columns:
        failures.append(f"{label}: native finish had no active tile")
        return
    current = {
        tile["column"]: tile for tile in presentation_row(snapshot, 0)
    }
    before = {
        tile["column"]: tile for tile in presentation_row(reference, 0)
    }
    displacement = max(
        (
            before[column]["motionRect"]["y"]
            - current[column]["motionRect"]["y"]
            for column in columns
        ),
        default=0,
    )
    if displacement < expected["minimumUpwardDisplacementPx"]:
        failures.append(f"{label}: native finish did not visibly move a tile")


def assert_replay_controls(
    snapshot: dict[str, Any],
    failures: list[str],
    label: str,
    *,
    continue_visible: bool,
) -> None:
    replay = snapshot["presentation"]["motion"]["replay"]
    if not replay["replayControlVisible"]:
        failures.append(f"{label}: Replay finish control was not visible")
    if replay["continueControlVisible"] != continue_visible:
        state = "visible" if continue_visible else "hidden"
        failures.append(f"{label}: Continue control was not {state}")


def assert_replay_completion(
    snapshot: dict[str, Any],
    expected: dict[str, Any],
    failures: list[str],
    label: str,
    replay_number: int,
) -> None:
    replay = snapshot["presentation"]["motion"]["replay"]
    count = expected["expectedTileCount"]
    if replay["count"] != replay_number:
        failures.append(f"{label}: replay count was not {replay_number}")
    if replay["phase"] != "complete":
        failures.append(f"{label}: replay did not reach its completed state")
    if replay["startedCount"] != count or replay["finishedCount"] != count:
        failures.append(f"{label}: replay did not preserve all five tile events")
    if (
        replay["animationEndCount"] != expected["expectedNativeEndCount"]
        or replay["fallbackCount"] != expected["expectedFallbackCount"]
    ):
        failures.append(
            f"{label}: replay completion was not owned by five native animation boundaries"
        )
    if replay["missingAnimationCount"] != 0:
        failures.append(f"{label}: replay could not find every native tile animation")
    if not snapshot["terminal"]["success"]:
        failures.append(f"{label}: terminal success was lost during replay")
    if not snapshot["presentation"]["resultVisible"]:
        failures.append(f"{label}: terminal result was hidden after replay")


def bounded_wait(
    page: Page,
    expression: str,
    timeout_ms: int,
    failures: list[str],
    failure: str,
) -> bool:
    try:
        page.wait_for_function(expression, timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        failures.append(failure)
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=os.environ.get(
            "CUA_SWE_WEB_URL",
            "http://127.0.0.1:52000/?mode=daily",
        ),
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(
            os.environ.get("CUA_SWE_VERIFIER_ARTIFACTS", "verifier-artifacts")
        ),
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    replay = fixture["replay"]
    expected = fixture["expectations"]
    daily = fixture["challenges"]["daily"]
    practice = fixture["challenges"]["practice"]
    failures: list[str] = []
    records: dict[str, Any] = {}
    page_errors: list[str] = []
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1100, "height": 900},
            device_scale_factor=1,
            reduced_motion="no-preference",
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: (
                console_errors.append(message.text)
                if message.type == "error"
                else None
            ),
        )
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_function(
            "window.gameAPI && "
            "window.gameAPI.getState().challenge?.mode === 'daily'"
        )
        page.evaluate("window.gameAPI.reset({mode: 'daily'})")

        initial = save_checkpoint(
            page, args.evidence_dir, records, "01-initial-daily"
        )
        assert_fresh(initial, failures, "initial daily")
        if initial["challenge"]["id"] != daily["id"]:
            failures.append("initial daily challenge identity was incorrect")
        if not initial["is_actionable"]:
            failures.append("initial daily challenge was not actionable")

        type_guess(page, replay["firstGuess"])
        page.wait_for_function(
            "window.gameAPI.getState().reveal.active && "
            "window.gameAPI.getState().reveal.revealedTiles >= 2 && "
            "window.gameAPI.getState().reveal.revealedTiles < 5"
        )
        repeated_mid = save_checkpoint(
            page, args.evidence_dir, records, "02-repeated-letter-mid-reveal"
        )
        count = repeated_mid["reveal"]["revealedTiles"]
        wanted_prefix = expected["firstRowStates"][:count]
        actual_prefix = row_statuses(repeated_mid, 0)[:count]
        if actual_prefix != wanted_prefix:
            failures.append("staggered repeated-letter prefix was incorrect")
        if any(
            status != "empty"
            for status in row_statuses(repeated_mid, 0)[count:]
        ):
            failures.append("staggered reveal colored future tiles early")

        page.wait_for_function(
            "!window.gameAPI.getState().reveal.active && "
            "window.gameAPI.getState().currentRow === 1"
        )
        page.wait_for_timeout(380)
        repeated_settled = save_checkpoint(
            page, args.evidence_dir, records, "03-repeated-letter-settled"
        )
        if row_statuses(repeated_settled, 0) != expected["firstRowStates"]:
            failures.append("settled repeated-letter semantics were incorrect")
        for letter, wanted in expected["firstRowKeyboard"].items():
            if repeated_settled["keyboard"].get(letter) != wanted:
                failures.append(f"model keyboard precedence was wrong for {letter}")
            if repeated_settled["presentation"]["keyboard"].get(letter) != wanted:
                failures.append(
                    f"rendered keyboard precedence was wrong for {letter}"
                )
        for letter, wanted in expected["minimumCounts"].items():
            if repeated_settled["hardMode"]["minimum"].get(letter) != wanted:
                failures.append("hard guidance lost repeated-letter multiplicity")
        for position, wanted in expected["exactPositions"].items():
            if repeated_settled["hardMode"]["exact"][int(position)] != wanted:
                failures.append("hard guidance lost an exact position")
        assert_settled_faces(
            repeated_settled, failures, "settled repeated-letter row"
        )

        type_guess(page, replay["hardViolation"])
        page.wait_for_function(
            "window.gameAPI.getState().validation.hardRejected === 1"
        )
        hard_rejected = save_checkpoint(
            page, args.evidence_dir, records, "04-hard-guidance-rejection"
        )
        if hard_rejected["currentRow"] != 1:
            failures.append("hard-guidance rejection consumed a row")
        if hard_rejected["messageKind"] != "error":
            failures.append("hard-guidance rejection was not player-visible")
        page.wait_for_function("window.gameAPI.getState().input === ''")

        type_guess(page, replay["invalidWord"])
        page.wait_for_function(
            "window.gameAPI.getState().validation.rejected === 1"
        )
        invalid_rejected = save_checkpoint(
            page, args.evidence_dir, records, "05-invalid-entry-rejection"
        )
        if invalid_rejected["currentRow"] != 1:
            failures.append("invalid entry rejection consumed a row")
        page.wait_for_function("window.gameAPI.getState().input === ''")

        prior_round = invalid_rejected["round"]
        page.click("#restart")
        page.wait_for_function(
            f"window.gameAPI.getState().round > {prior_round} && "
            "window.gameAPI.getState().is_actionable"
        )
        restarted = save_checkpoint(
            page, args.evidence_dir, records, "06-daily-restart-fresh"
        )
        assert_fresh(restarted, failures, "daily restart")

        page.click('[data-mode="practice"]')
        page.wait_for_function(
            "window.gameAPI.getState().challenge?.mode === 'practice'"
        )
        practice_fresh = save_checkpoint(
            page, args.evidence_dir, records, "07-practice-mode-fresh"
        )
        assert_fresh(practice_fresh, failures, "practice mode")
        if practice_fresh["challenge"]["id"] != practice["id"]:
            failures.append("practice mode loaded the wrong deterministic challenge")

        page.click('[data-mode="daily"]')
        page.wait_for_function(
            "window.gameAPI.getState().challenge?.mode === 'daily'"
        )
        daily_restored = save_checkpoint(
            page, args.evidence_dir, records, "08-daily-mode-restored"
        )
        assert_fresh(daily_restored, failures, "restored daily mode")
        if daily_restored["challenge"]["id"] != daily["id"]:
            failures.append("daily mode did not restore its deterministic challenge")

        type_guess(page, replay["answer"])
        page.wait_for_function(
            "window.gameAPI.getState().reveal.active && "
            "window.gameAPI.getState().reveal.revealedTiles >= 2 && "
            "window.gameAPI.getState().reveal.revealedTiles < 5"
        )
        winning_mid = save_checkpoint(
            page, args.evidence_dir, records, "09-winning-row-mid-reveal"
        )
        winning_count = winning_mid["reveal"]["revealedTiles"]
        if row_statuses(winning_mid, 0)[:winning_count] != ["exact"] * winning_count:
            failures.append("winning staggered reveal produced a non-exact tile")
        if any(
            status != "empty"
            for status in row_statuses(winning_mid, 0)[winning_count:]
        ):
            failures.append("winning reveal colored future tiles early")

        page.wait_for_function(
            "window.gameAPI.getState().terminal.success && "
            "!window.gameAPI.getState().reveal.active"
        )
        page.wait_for_timeout(360)
        pre_motion = save_checkpoint(
            page, args.evidence_dir, records, "10-winning-row-pre-motion"
        )
        assert_exact_winning_model(
            pre_motion, replay["answer"], failures, "pre-result frame"
        )
        assert_settled_faces(pre_motion, failures, "pre-result frame")
        if pre_motion["presentation"]["motion"]["startedCount"] != 0:
            failures.append("result motion began before the pre-result checkpoint")

        timeout_ms = expected["result"]["activeCheckpointTimeoutMs"]
        bounded_wait(
            page,
            "window.gameAPI.getState().presentation.motion.startedCount >= 1 && "
            "window.gameAPI.getState().presentation.motion.activeTiles.length >= 1",
            timeout_ms,
            failures,
            "result motion never activated its first tile",
        )
        page.wait_for_timeout(55)
        first_motion = save_checkpoint(
            page, args.evidence_dir, records, "11-first-native-finish"
        )
        assert_exact_winning_model(
            first_motion, replay["answer"], failures, "first native finish"
        )
        assert_native_motion_present(
            first_motion,
            pre_motion,
            expected["result"],
            failures,
            "first native finish",
        )

        bounded_wait(
            page,
            "window.gameAPI.getState().presentation.motion.complete && "
            "window.gameAPI.getState().presentation.motion.activeTiles.length === 0",
            4000,
            failures,
            "result motion did not terminate",
        )
        page.wait_for_timeout(380)
        native_terminal = save_checkpoint(
            page, args.evidence_dir, records, "12-native-terminal-result"
        )
        assert_exact_winning_model(
            native_terminal, replay["answer"], failures, "native terminal result"
        )
        assert_settled_faces(
            native_terminal, failures, "native terminal result"
        )
        if not native_terminal["terminal"]["success"]:
            failures.append("deterministic daily challenge did not complete")
        motion = native_terminal["presentation"]["motion"]
        if motion["startedCount"] != 5 or motion["finishedCount"] != 5:
            failures.append("result motion did not preserve all five tile events")
        if motion["animationEndCount"] != 5 or motion["fallbackCount"] != 0:
            failures.append(
                "result completion was not owned by the five visible animations"
            )
        if not native_terminal["presentation"]["resultVisible"]:
            failures.append("terminal result did not become visible")

        replay_ready = save_checkpoint(
            page, args.evidence_dir, records, "13-replay-control-visible"
        )
        assert_replay_controls(
            replay_ready,
            failures,
            "terminal replay affordance",
            continue_visible=False,
        )
        if not replay_ready["presentation"]["motion"]["replay"][
            "replayControlEnabled"
        ]:
            failures.append("terminal Replay finish control was not enabled")

        replay_expected = expected["replayInspection"]
        page.get_by_role("button", name="Replay finish").click()
        replay_started = save_checkpoint(
            page, args.evidence_dir, records, "14-replay-started-by-click"
        )
        started_state = replay_started["presentation"]["motion"]["replay"]
        if started_state["count"] != 1:
            failures.append("ordinary Replay finish click did not start replay one")
        if started_state["phase"] not in {"starting", "paused"}:
            failures.append("ordinary Replay finish click did not enter playback")

        replay_one_paused_ok = bounded_wait(
            page,
            "window.gameAPI.getState().presentation.motion.replay.phase === 'paused'",
            replay_expected["pauseTimeoutMs"],
            failures,
            "first replay did not reach a stable paused mid-motion frame",
        )
        replay_one_paused = save_checkpoint(
            page, args.evidence_dir, records, "15-first-replay-paused-mid-motion"
        )
        paused_one = replay_one_paused["presentation"]["motion"]["replay"]
        if paused_one["startedCount"] != replay_expected["expectedTileCount"]:
            failures.append("first replay did not start all five tiles")
        if paused_one["pausedCount"] != replay_expected["expectedTileCount"]:
            failures.append("first replay did not pause all five tiles")
        if not all(entry["paused"] for entry in paused_one["activeTiles"]):
            failures.append("first replay did not hold every active tile still")
        assert_replay_controls(
            replay_one_paused,
            failures,
            "first replay pause",
            continue_visible=True,
        )
        assert_active_visual_continuity(
            replay_one_paused,
            pre_motion,
            expected["result"],
            failures,
            "first replay pause",
            replay=True,
        )

        if replay_one_paused_ok:
            page.get_by_role("button", name="Continue").click()
            page.wait_for_function(
                "window.gameAPI.getState().presentation.motion.replay.phase === 'playing'"
            )
        else:
            failures.append("first replay could not be continued through its visible control")
        replay_one_continued = save_checkpoint(
            page, args.evidence_dir, records, "16-first-replay-continued"
        )
        if replay_one_paused_ok:
            continued_one = replay_one_continued["presentation"]["motion"]["replay"]
            if continued_one["continueCount"] != 1:
                failures.append("first replay Continue click was not recorded")

        bounded_wait(
            page,
            "window.gameAPI.getState().presentation.motion.replay.phase === 'complete'",
            replay_expected["completionTimeoutMs"],
            failures,
            "first replay did not complete",
        )
        replay_one_complete = save_checkpoint(
            page, args.evidence_dir, records, "17-first-replay-native-completion"
        )
        assert_exact_winning_model(
            replay_one_complete,
            replay["answer"],
            failures,
            "first replay completion",
        )
        assert_settled_faces(
            replay_one_complete, failures, "first replay completion"
        )
        assert_replay_completion(
            replay_one_complete,
            replay_expected,
            failures,
            "first replay completion",
            1,
        )

        page.get_by_role("button", name="Replay finish").click()
        replay_two_paused_ok = bounded_wait(
            page,
            "window.gameAPI.getState().presentation.motion.replay.phase === 'paused'",
            replay_expected["pauseTimeoutMs"],
            failures,
            "second replay did not reach a stable paused mid-motion frame",
        )
        replay_two_paused = save_checkpoint(
            page, args.evidence_dir, records, "18-second-replay-paused-mid-motion"
        )
        paused_two = replay_two_paused["presentation"]["motion"]["replay"]
        if paused_two["count"] != 2:
            failures.append("second visible Replay finish click was not recorded")
        if paused_two["pausedCount"] != replay_expected["expectedTileCount"]:
            failures.append("second replay did not pause all five tiles")
        assert_replay_controls(
            replay_two_paused,
            failures,
            "second replay pause",
            continue_visible=True,
        )
        assert_active_visual_continuity(
            replay_two_paused,
            pre_motion,
            expected["result"],
            failures,
            "second replay pause",
            replay=True,
        )
        if replay_two_paused_ok:
            page.get_by_role("button", name="Continue").click()
        else:
            failures.append("second replay could not be continued through its visible control")
        bounded_wait(
            page,
            "window.gameAPI.getState().presentation.motion.replay.phase === 'complete'",
            replay_expected["completionTimeoutMs"],
            failures,
            "second replay did not complete",
        )
        replay_two_complete = save_checkpoint(
            page, args.evidence_dir, records, "19-second-replay-native-completion"
        )
        assert_replay_completion(
            replay_two_complete,
            replay_expected,
            failures,
            "second replay completion",
            2,
        )

        replay_round = replay_two_complete["round"]
        page.click("#restart")
        page.wait_for_function(
            f"window.gameAPI.getState().round > {replay_round} && "
            "window.gameAPI.getState().is_actionable"
        )
        replay_restart = save_checkpoint(
            page, args.evidence_dir, records, "20-restart-after-replay"
        )
        assert_fresh(replay_restart, failures, "restart after replay")
        if replay_restart["presentation"]["motion"]["replay"]["count"] != 0:
            failures.append("restart retained prior replay counters")

        page.click('[data-mode="practice"]')
        page.wait_for_function(
            "window.gameAPI.getState().challenge?.mode === 'practice'"
        )
        replay_practice = save_checkpoint(
            page, args.evidence_dir, records, "21-practice-after-replay"
        )
        assert_fresh(replay_practice, failures, "practice after replay")
        if replay_practice["challenge"]["id"] != practice["id"]:
            failures.append("practice mode failed after replay")

        page.click('[data-mode="daily"]')
        page.wait_for_function(
            "window.gameAPI.getState().challenge?.mode === 'daily'"
        )
        replay_daily = save_checkpoint(
            page, args.evidence_dir, records, "22-daily-restored-after-replay"
        )
        assert_fresh(replay_daily, failures, "daily restored after replay")
        if replay_daily["challenge"]["id"] != daily["id"]:
            failures.append("daily mode failed to restore after replay")

        reduced_page = browser.new_page(
            viewport={"width": 1100, "height": 900},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        reduced_page.on("pageerror", lambda error: page_errors.append(str(error)))
        reduced_page.on(
            "console",
            lambda message: (
                console_errors.append(message.text)
                if message.type == "error"
                else None
            ),
        )
        reduced_page.goto(args.url, wait_until="networkidle")
        reduced_page.wait_for_function(
            "window.gameAPI && "
            "window.gameAPI.getState().challenge?.mode === 'daily'"
        )
        reduced_page.evaluate("window.gameAPI.reset({mode: 'daily'})")
        type_guess(reduced_page, replay["answer"])
        bounded_wait(
            reduced_page,
            "window.gameAPI.getState().presentation.motion.complete && "
            "window.gameAPI.getState().presentation.resultVisible",
            5000,
            failures,
            "reduced-motion native completion did not terminate",
        )
        reduced_terminal = save_checkpoint(
            reduced_page,
            args.evidence_dir,
            records,
            "23-reduced-motion-terminal",
        )
        reduced_native = reduced_terminal["presentation"]["motion"]
        if (
            reduced_native["animationEndCount"]
            != replay_expected["expectedNativeEndCount"]
            or reduced_native["fallbackCount"]
            != replay_expected["expectedFallbackCount"]
        ):
            failures.append(
                "reduced-motion finish did not retain native completion ownership"
            )
        reduced_page.get_by_role("button", name="Replay finish").click()
        bounded_wait(
            reduced_page,
            "window.gameAPI.getState().presentation.motion.replay.phase === 'complete'",
            replay_expected["reducedMotionTimeoutMs"],
            failures,
            "reduced-motion replay did not complete promptly",
        )
        reduced_replay = save_checkpoint(
            reduced_page,
            args.evidence_dir,
            records,
            "24-reduced-motion-replay-complete",
        )
        assert_replay_completion(
            reduced_replay,
            replay_expected,
            failures,
            "reduced-motion replay",
            1,
        )
        reduced_state = reduced_replay["presentation"]["motion"]["replay"]
        if reduced_state["pausedCount"] != 0:
            failures.append("reduced-motion replay introduced an inspection pause")
        if reduced_state["continueControlVisible"]:
            failures.append("reduced-motion replay exposed an unnecessary Continue control")
        reduced_page.close()
        browser.close()

    if page_errors:
        failures.append(f"browser page errors: {page_errors}")
    if console_errors:
        failures.append(f"browser console errors: {console_errors}")

    report = {
        "url": args.url,
        "fixture_ids": {
            mode: challenge["id"]
            for mode, challenge in fixture["challenges"].items()
        },
        "checkpoints": records,
        "failures": failures,
        "page_errors": page_errors,
        "console_errors": console_errors,
        "screenshots": [f"{name}.png" for name in records],
    }
    (args.evidence_dir / "state-records.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        print(json.dumps({"status": "fail", "failures": failures}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": "pass",
                "checkpoints": len(records),
                "terminal": records["19-second-replay-native-completion"]["terminal"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
