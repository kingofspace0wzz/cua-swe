#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from playwright.sync_api import Page, sync_playwright


LANE_Y = {"u": 215, "v": 300, "w": 385}
KEYS = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "a", "d", "w", "s"]


def state(page: Page) -> dict:
    return page.evaluate("window.gameAPI.getState()")


def release_all(page: Page) -> None:
    for key in KEYS:
        page.keyboard.up(key)


def wait_for(page: Page, predicate, label: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    last = state(page)
    while time.monotonic() < deadline:
        page.wait_for_timeout(20)
        last = state(page)
        if predicate(last):
            return last
    raise AssertionError(f"timed out while {label}: {json.dumps(last, sort_keys=True)}")


def hold_until(
    page: Page,
    key: str,
    predicate,
    label: str,
    timeout: float = 10.0,
) -> dict:
    page.keyboard.down(key)
    deadline = time.monotonic() + timeout
    last = state(page)
    try:
        while time.monotonic() < deadline:
            page.wait_for_timeout(20)
            last = state(page)
            if predicate(last):
                return last
            if last["terminal"]["isTerminal"]:
                break
    finally:
        page.keyboard.up(key)
    raise AssertionError(f"timed out while {label}: {json.dumps(last, sort_keys=True)}")


def move_x(page: Page, target: float, tolerance: float = 5.0) -> dict:
    current = state(page)
    x = current["game_state"]["player"]["x"]
    if abs(x - target) <= tolerance:
        return current
    right = x < target
    return hold_until(
        page,
        "ArrowRight" if right else "ArrowLeft",
        lambda sample: (
            sample["game_state"]["player"]["x"] >= target
            if right
            else sample["game_state"]["player"]["x"] <= target
        ),
        f"moving horizontally to {target}",
    )


def move_y(page: Page, target: float, tolerance: float = 5.0) -> dict:
    current = state(page)
    y = current["game_state"]["player"]["y"]
    if abs(y - target) <= tolerance:
        return current
    down = y < target
    return hold_until(
        page,
        "ArrowDown" if down else "ArrowUp",
        lambda sample: (
            sample["game_state"]["player"]["y"] >= target
            if down
            else sample["game_state"]["player"]["y"] <= target
        ),
        f"moving vertically to {target}",
    )


def screenshot(page: Page, root: Path, name: str) -> None:
    page.screenshot(path=str(root / name))


def canvas_sample(page: Page) -> dict:
    return page.evaluate(
        """
        () => {
          const canvas = document.querySelector("#game");
          const context = canvas?.getContext("2d");
          if (!canvas || !context) return {present: false, opaque: 0, colored: 0};
          const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
          let opaque = 0;
          let colored = 0;
          for (let index = 0; index < pixels.length; index += 64) {
            if (pixels[index + 3] > 0) opaque += 1;
            if (pixels[index] || pixels[index + 1] || pixels[index + 2]) colored += 1;
          }
          return {present: true, opaque, colored};
        }
        """
    )


def stable_record(record: dict) -> dict:
    return {
        "clock": record["clock"],
        "pulses": record["pulses"],
        "active": record["active"],
        "generation": record["generation"],
        "assignment": record["assignment"],
        "route": record["route"],
        "trail": record["trail"],
        "capsules": record["capsules"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:51000/")
    parser.add_argument("--evidence-dir", type=Path, default=Path("verifier-artifacts"))
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    evidence: dict = {"url": args.url, "states": {}, "startup": {}}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        browser_requests: list[str] = []
        page.on("request", lambda request: browser_requests.append(request.url))
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_selector("#game")
        page.wait_for_function(
            """
            () => {
              const canvas = document.querySelector("#game");
              const context = canvas?.getContext("2d");
              if (!canvas || !context) return false;
              const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
              let opaque = 0;
              for (let index = 3; index < pixels.length; index += 64) {
                if (pixels[index] > 0) opaque += 1;
                if (opaque > 1000) return true;
              }
              return false;
            }
            """,
            timeout=3000,
        )
        evidence["startup"]["first_canvas"] = canvas_sample(page)
        screenshot(page, args.evidence_dir, "00-boot.png")
        page.wait_for_function("window.gameAPI && window.gameAPI.getState")
        page.wait_for_function("window.gameBoot && window.gameBoot.status === 'ready'")
        page.evaluate("window.gameAPI.reset({seed: 2903, level: 1})")
        page.wait_for_function("window.gameAPI.getState().is_actionable")
        initial = state(page)
        evidence["states"]["initial"] = initial
        evidence["startup"]["ready_canvas"] = canvas_sample(page)
        evidence["startup"]["boot"] = page.evaluate("window.gameBoot")
        evidence["startup"]["browser_requests"] = browser_requests

        declared = urlsplit(args.url)
        declared_origin = (declared.scheme, declared.hostname, declared.port)
        foreign_requests = []
        request_paths = []
        for request_url in browser_requests:
            parsed = urlsplit(request_url)
            if parsed.scheme not in {"http", "https"}:
                continue
            request_paths.append(parsed.path)
            if (parsed.scheme, parsed.hostname, parsed.port) != declared_origin:
                foreign_requests.append(request_url)
        if foreign_requests:
            failures.append(
                f"browser contacted an origin other than the declared app: {foreign_requests}"
            )
        for required_path in ("/runtime/ticket", "/runtime/route-card.png"):
            if required_path not in request_paths:
                failures.append(
                    f"game-ready startup did not use same-origin proxy path {required_path}"
                )
        if evidence["startup"]["first_canvas"]["opaque"] <= 1000:
            failures.append("the initial canvas remained blank during asynchronous startup")
        if evidence["startup"]["ready_canvas"]["colored"] <= 1000:
            failures.append("the game-ready canvas did not render a visible initial frame")
        screenshot(page, args.evidence_dir, "00-initial.png")

        move_x(page, 310)
        first_token = state(page)
        if first_token["metrics"]["tokens"] != 1:
            failures.append("the first prism was not collected by keyboard play")

        # Capture the state at the activation edge. The checkpoint snapshot is
        # saved as soon as the player enters the shelter, before reaching its
        # visual center.
        move_x(page, 407)
        checkpoint = wait_for(
            page,
            lambda sample: sample["game_state"]["checkpoint"]["active"],
            "activating the midpoint shelter",
        )
        evidence["states"]["checkpoint"] = checkpoint
        screenshot(page, args.evidence_dir, "01-checkpoint-card.png")
        triad = checkpoint["game_state"]["triad"]
        if not triad["field_complete"] or not triad["panel_complete"]:
            failures.append("checkpoint records were not complete and internally consistent")
        if triad["field"] != triad["panel"]:
            failures.append("field and panel differed before the return-only ownership trigger")

        move_x(page, 530)
        ready = wait_for(
            page,
            lambda sample: (
                sample["game_state"]["triad"]["field_open"]
                == sample["game_state"]["triad"]["panel_open"]
                and sample["game_state"]["triad"]["panel"]["clock"] <= 20
            ),
            "waiting for a bounded pre-trigger opening",
            timeout=8.0,
        )
        move_y(page, LANE_Y[ready["game_state"]["triad"]["panel_open"]])
        deaths_before = state(page)["metrics"]["deaths"]
        move_x(page, 710)
        first_cross = state(page)
        evidence["states"]["pre_trigger_cross"] = first_cross
        screenshot(page, args.evidence_dir, "02-pre-trigger-crossing.png")
        if first_cross["metrics"]["deaths"] != deaths_before:
            failures.append("the pre-trigger OPEN lane was not traversable")

        move_y(page, LANE_Y["u"])
        move_x(page, 835)
        second_token = state(page)
        evidence["states"]["second_token_before_collision"] = second_token
        if second_token["metrics"]["tokens"] != 2:
            failures.append("the second prism was not collected before the collision")

        open_slot = second_token["game_state"]["triad"]["field_open"]
        closed_slot = next(slot for slot in ("u", "v", "w") if slot != open_slot)
        move_y(page, LANE_Y[closed_slot])
        start_deaths = state(page)["metrics"]["deaths"]
        try:
            hold_until(
                page,
                "ArrowLeft",
                lambda sample: sample["metrics"]["deaths"] > start_deaths,
                "causing the deliberate post-checkpoint collision",
                timeout=4.0,
            )
        finally:
            release_all(page)
        collision = state(page)
        evidence["states"]["collision"] = collision
        screenshot(page, args.evidence_dir, "03-collision.png")

        returned = wait_for(
            page,
            lambda sample: (
                sample["is_actionable"]
                and sample["game_state"]["checkpoint"]["returns"] == 1
            ),
            "waiting for checkpoint return with released input",
        )
        evidence["states"]["returned"] = returned
        screenshot(page, args.evidence_dir, "04-returned-held.png")
        if returned["metrics"] != {"tokens": 1, "remaining_tokens": 1, "deaths": 1}:
            failures.append(f"checkpoint carry/rollback was wrong: {returned['metrics']}")
        if not returned["game_state"]["safe_zone"]["occupied"]:
            failures.append("checkpoint return did not land in the visible shelter")
        if returned["game_state"]["triad"]["return_committed"]:
            failures.append("return ownership committed before leaving the shelter")
        saved = returned["game_state"]["checkpoint"]["saved"]
        if not saved:
            failures.append("the checkpoint did not expose its protected saved records")
        for name in ("field", "panel"):
            if saved and stable_record(returned["game_state"]["triad"][name]) != (
                stable_record(saved[name]) | {"active": False}
            ):
                failures.append(f"{name} did not restore the complete saved record")

        held_clock = returned["game_state"]["triad"]["panel"]["clock"]
        held_trail = returned["game_state"]["triad"]["panel"]["trail"]
        page.wait_for_timeout(1200)
        held = state(page)
        evidence["states"]["shelter_hold"] = held
        if held["game_state"]["triad"]["panel"]["clock"] != held_clock:
            failures.append("the visible handoff advanced while the player waited in the shelter")
        if held["game_state"]["triad"]["panel"]["trail"] != held_trail:
            failures.append("the visible handoff trail changed inside the shelter")

        move_x(page, 520)
        committed = wait_for(
            page,
            lambda sample: sample["game_state"]["triad"]["return_committed"],
            "leaving the shelter and committing the handoff",
        )
        evidence["states"]["committed"] = committed
        screenshot(page, args.evidence_dir, "05-departure.png")
        if committed["game_state"]["triad"]["field_open"] != committed["game_state"]["triad"]["panel_open"]:
            failures.append("field and panel did not agree at the released departure instant")

        first_pulse = committed["game_state"]["triad"]["panel"]["pulses"] + 1
        pulse_one = wait_for(
            page,
            lambda sample: sample["game_state"]["triad"]["panel"]["pulses"] >= first_pulse,
            "waiting for the first post-return handoff pulse",
            timeout=6.0,
        )
        evidence["states"]["pulse_one"] = pulse_one
        screenshot(page, args.evidence_dir, "06-first-pulse.png")
        if pulse_one["game_state"]["triad"]["field_open"] != pulse_one["game_state"]["triad"]["panel_open"]:
            failures.append("the first visible handoff pulse marked a physically closed lane")

        second_pulse = wait_for(
            page,
            lambda sample: sample["game_state"]["triad"]["panel"]["pulses"] >= first_pulse + 1,
            "waiting for the second post-return handoff pulse",
            timeout=6.0,
        )
        evidence["states"]["pulse_two"] = second_pulse
        screenshot(page, args.evidence_dir, "07-second-pulse.png")
        if second_pulse["game_state"]["triad"]["field_open"] != second_pulse["game_state"]["triad"]["panel_open"]:
            failures.append("the second visible handoff pulse marked a physically closed lane")
        if second_pulse["game_state"]["triad"]["panel"]["trail"] != ["u", "v", "w"]:
            failures.append("the visible handoff trail repeated, skipped, or reversed an owner")

        move_y(page, LANE_Y[second_pulse["game_state"]["triad"]["panel_open"]])
        replay_deaths = state(page)["metrics"]["deaths"]
        try:
            move_x(page, 710)
        except AssertionError:
            pass
        replay_cross = state(page)
        evidence["states"]["replay_cross"] = replay_cross
        screenshot(page, args.evidence_dir, "08-replayed-opening.png")
        replay_hit = replay_cross["metrics"]["deaths"] != replay_deaths
        if replay_hit:
            failures.append("the marked post-return opening caused another hit")

        if not replay_hit:
            move_y(page, LANE_Y["u"])
            move_x(page, 835)
            recollected = state(page)
            evidence["states"]["recollected"] = recollected
            if recollected["metrics"]["tokens"] != 2:
                failures.append("the rolled-back prism was not recollected")
            completed = hold_until(
                page,
                "ArrowRight",
                lambda sample: sample["terminal"]["isTerminal"],
                "reaching the exit",
            )
            evidence["states"]["completed"] = completed
            screenshot(page, args.evidence_dir, "09-complete.png")
            if completed["terminal"]["outcome"] != "success":
                failures.append("the course did not complete")

            page.keyboard.press("r")
            restarted = wait_for(
                page,
                lambda sample: (
                    sample["is_actionable"]
                    and not sample["game_state"]["checkpoint"]["active"]
                ),
                "performing an ordinary R restart",
            )
            evidence["states"]["restarted"] = restarted
            screenshot(page, args.evidence_dir, "10-restarted.png")
            if restarted["metrics"] != {"tokens": 0, "remaining_tokens": 2, "deaths": 0}:
                failures.append(f"ordinary restart retained episode state: {restarted['metrics']}")
            if restarted["game_state"]["triad"]["return_armed"]:
                failures.append("ordinary restart retained a return transaction")
            if restarted["game_state"]["triad"]["field"] != restarted["game_state"]["triad"]["panel"]:
                failures.append("ordinary restart did not restore the neutral triad")

        (args.evidence_dir / "state-replay.json").write_text(
            json.dumps(evidence | {"failures": failures}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        browser.close()

    if failures:
        raise AssertionError("; ".join(failures))
    print(json.dumps({"status": "pass", "deaths": 1, "tokens": 2, "completed": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
