#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

from playwright.sync_api import Page, sync_playwright


FLIGHT_CONTROLLER = r"""
config => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const trace = {
    done: false,
    finish_reason: null,
    down: false,
    cooldown: 0,
    pulse_count: 0,
    transitions: [],
    final: null,
  };
  window.__flightLabRoute = trace;
  const startedAt = performance.now();

  const dispatchSpace = type => {
    window.dispatchEvent(new KeyboardEvent(type, {
      key: " ",
      code: "Space",
      bubbles: true,
      cancelable: true,
    }));
  };
  const pulse = state => {
    if (trace.down) return;
    trace.down = true;
    trace.pulse_count += 1;
    dispatchSpace("keydown");
    trace.transitions.push({
      kind: "press",
      game_time_ms: state.gameTimeMs,
      player_y: state.game_state.player.y,
      velocity_y: state.game_state.player.vy,
      pipe_id: state.game_state.environment.next_pipe
        ? state.game_state.environment.next_pipe.id
        : null,
    });
    setTimeout(() => {
      dispatchSpace("keyup");
      trace.down = false;
      trace.cooldown = 2;
      const released = window.gameAPI.getState();
      trace.transitions.push({
        kind: "release",
        game_time_ms: released.gameTimeMs,
        player_y: released.game_state.player.y,
        velocity_y: released.game_state.player.vy,
        pipe_id: released.game_state.environment.next_pipe
          ? released.game_state.environment.next_pipe.id
          : null,
      });
    }, config.pulse_ms);
  };
  const finish = (reason, state) => {
    if (trace.down) {
      dispatchSpace("keyup");
      trace.down = false;
    }
    trace.finish_reason = reason;
    trace.final = clone(state);
    trace.done = true;
  };

  const frame = () => {
    if (trace.done) return;
    const state = window.gameAPI.getState();
    const player = state.game_state.player;
    const pipe = state.game_state.environment.next_pipe;
    if (trace.cooldown > 0) trace.cooldown -= 1;
    if (state.terminal.isTerminal) {
      finish("terminal", state);
      return;
    }
    if (state.metrics.pipes_passed >= config.desired_score) {
      finish("score", state);
      return;
    }
    if (performance.now() - startedAt >= config.timeout_sec * 1000) {
      finish("timeout", state);
      return;
    }
    if (
      !trace.down
      && trace.cooldown === 0
      && (
        player.y > config.target_y
        || (player.y > config.target_y - 13 && player.vy > 105)
      )
      && (!pipe || pipe.x > 0)
    ) {
      pulse(state);
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}
"""


DRILLS = [
    ("tap-arc", (120, 220), "tap", "Digit1"),
    ("held-arc", (320, 220), "held", None),
    ("late-contact", (520, 220), "late", "Digit3"),
]
BACK_POINT = (532, 416)
RUN_POINT = (320, 370)


def get_state(page: Page) -> dict[str, Any]:
    return page.evaluate("window.gameAPI.getState()")


def wait_until(page: Page, predicate, timeout_sec: float, label: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last = get_state(page)
    while time.monotonic() < deadline:
      last = get_state(page)
      if predicate(last):
          return last
      page.wait_for_timeout(10)
    raise AssertionError(f"timed out waiting for {label}: {last}")


def click_canvas(page: Page, point: tuple[int, int]) -> None:
    box = page.locator("#game").bounding_box()
    if not box:
        raise AssertionError("canvas has no bounding box")
    page.mouse.click(
        box["x"] + point[0] * box["width"] / 640,
        box["y"] + point[1] * box["height"] / 480,
    )


def release_inputs(page: Page) -> None:
    try:
        page.keyboard.up("Space")
    except Exception:
        pass
    try:
        page.mouse.up()
    except Exception:
        pass


def reset_lab(page: Page) -> dict[str, Any]:
    release_inputs(page)
    page.evaluate("window.gameAPI.reset({seed: 42, level: 1})")
    return wait_until(
        page,
        lambda sample: sample["game_state"]["environment"]["phase"] == "lab",
        3,
        "stable Flight Lab",
    )


def frozen_signature(state: dict[str, Any]) -> dict[str, Any]:
    lab = state["game_state"]["environment"]["flight_lab"]
    player = state["game_state"]["player"]
    pipe = state["game_state"]["environment"]["next_pipe"]
    return {
        "phase": state["game_state"]["environment"]["phase"],
        "selected": lab["selected"],
        "outcome": lab["outcome"],
        "score": lab["score"],
        "viewed": lab["viewed"],
        "visual_audit": lab["visual_audit"],
        "input_receipt": lab["input_receipt"],
        "actual_impulse": lab["actual_impulse"],
        "target_impulse": lab["target_impulse"],
        "player_y": player["y"],
        "player_vy": player["vy"],
        "pipe_x": pipe["x"] if pipe else None,
        "terminal": state["terminal"],
    }


def run_drill(
    page: Page,
    *,
    label: str,
    point: tuple[int, int],
    slug: str,
    key: str | None,
    evidence_dir: Path,
) -> dict[str, Any]:
    before = get_state(page)
    page.screenshot(path=str(evidence_dir / f"{label}-menu.png"))
    if key:
        page.keyboard.press(key)
    else:
        click_canvas(page, point)
    final = wait_until(
        page,
        lambda sample: (
            sample["game_state"]["environment"]["phase"] == "drill_result"
            and sample["game_state"]["environment"]["flight_lab"]["selected"] == slug
        ),
        4,
        f"{label} frozen result",
    )
    page.screenshot(path=str(evidence_dir / f"{label}-frozen.png"))
    signature = frozen_signature(final)
    page.wait_for_timeout(900)
    stable = get_state(page)
    page.screenshot(path=str(evidence_dir / f"{label}-stable.png"))
    return {
        "label": label,
        "before": before,
        "final": final,
        "frozen_signature": signature,
        "stable_signature": frozen_signature(stable),
    }


def return_to_lab(page: Page) -> dict[str, Any]:
    click_canvas(page, BACK_POINT)
    return wait_until(
        page,
        lambda sample: sample["game_state"]["environment"]["phase"] == "lab",
        3,
        "Flight Lab menu",
    )


def run_lab(page: Page, evidence_dir: Path) -> list[dict[str, Any]]:
    reset_lab(page)
    page.screenshot(path=str(evidence_dir / "flight-lab-menu.png"))
    runs = []
    for index, (label, point, slug, key) in enumerate(DRILLS):
        runs.append(
            run_drill(
                page,
                label=label,
                point=point,
                slug=slug,
                key=key,
                evidence_dir=evidence_dir,
            )
        )
        if index < len(DRILLS) - 1:
            return_to_lab(page)
    return runs


def start_normal(page: Page) -> dict[str, Any]:
    if get_state(page)["game_state"]["environment"]["phase"] == "drill_result":
        return_to_lab(page)
    click_canvas(page, RUN_POINT)
    return wait_until(
        page,
        lambda sample: sample["game_state"]["environment"]["phase"] == "playing",
        3,
        "normal run",
    )


def run_normal_route(page: Page, evidence_dir: Path) -> dict[str, Any]:
    start_normal(page)
    page.evaluate(
        FLIGHT_CONTROLLER,
        {
            "target_y": 228,
            "pulse_ms": 36,
            "desired_score": 3,
            "timeout_sec": 14,
        },
    )
    page.wait_for_function(
        "window.__flightLabRoute && window.__flightLabRoute.done",
        timeout=17000,
    )
    route = page.evaluate("window.__flightLabRoute")
    page.screenshot(path=str(evidence_dir / "normal-scoring-final.png"))
    return {
        "finish_reason": route["finish_reason"],
        "pulse_count": route["pulse_count"],
        "control_trace": route["transitions"],
        "final": route["final"],
        "score_events": [
            event
            for event in route["final"]["debug"]["recent_events"]
            if event["type"] == "score"
        ],
    }


def score_pipe_ids(run: dict[str, Any]) -> list[int]:
    return [event["details"]["pipe_id"] for event in run["score_events"]]


def trajectory_profile(
    state: dict[str, Any],
    checkpoints: list[int],
) -> dict[str, Any]:
    lab = state["game_state"]["environment"]["flight_lab"]
    actual = {round(point["pipe_x"]): point["y"] for point in lab["trail"]}
    target = {round(point["pipe_x"]): point["y"] for point in lab["target"]}
    samples = []
    for pipe_x in checkpoints:
        actual_y = actual.get(pipe_x)
        target_y = target.get(pipe_x)
        samples.append(
            {
                "pipe_x": pipe_x,
                "actual_y": actual_y,
                "target_y": target_y,
                "error": (
                    abs(actual_y - target_y)
                    if actual_y is not None and target_y is not None
                    else None
                ),
            }
        )
    errors = [sample["error"] for sample in samples if sample["error"] is not None]
    return {
        "sample_count": len(lab["trail"]),
        "target_count": len(lab["target"]),
        "checkpoints": samples,
        "all_present": len(errors) == len(samples),
        "max_error": max(errors) if len(errors) == len(samples) else None,
    }


def same_tick_edges(state: dict[str, Any], source: str) -> list[dict[str, Any]]:
    return [
        edge
        for edge in state["control_trace"]
        if edge["phase"] == "playing" and edge["source"] == source
    ][-2:]


def check_restart_and_controls(page: Page, evidence_dir: Path) -> dict[str, Any]:
    reset_lab(page)
    entry = start_normal(page)
    attempts_before = entry["metrics"]["attempts"]

    page.keyboard.down("Space")
    page.keyboard.up("Space")
    keyboard_flap = wait_until(
        page,
        lambda sample: (
            len(same_tick_edges(sample, "keyboard")) == 2
            and sample["game_state"]["environment"]["flight_lab"]["actual_impulse"] >= 210
            and sample["game_state"]["player"]["vy"] < -180
        ),
        2,
        "same-tick keyboard flap",
    )
    dead = wait_until(
        page,
        lambda sample: sample["terminal"]["isTerminal"],
        7,
        "ordinary death",
    )
    page.screenshot(path=str(evidence_dir / "restart-dead.png"))

    page.keyboard.press("Space")
    restarted = wait_until(
        page,
        lambda sample: (
            sample["game_state"]["environment"]["phase"] == "playing"
            and sample["metrics"]["attempts"] >= attempts_before + 1
        ),
        3,
        "keyboard restart",
    )
    box = page.locator("#game").bounding_box()
    if not box:
        raise AssertionError("canvas has no bounding box after restart")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    pointer_flap = wait_until(
        page,
        lambda sample: (
            len(same_tick_edges(sample, "pointer")) == 2
            and sample["game_state"]["environment"]["flight_lab"]["actual_impulse"] >= 210
            and sample["game_state"]["player"]["vy"] < -180
        ),
        2,
        "same-tick pointer flap",
    )
    pointer_dead = wait_until(
        page,
        lambda sample: sample["terminal"]["isTerminal"],
        7,
        "ordinary death before pointer restart",
    )
    pointer_attempts_before = pointer_dead["metrics"]["attempts"]
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    pointer_restarted = wait_until(
        page,
        lambda sample: (
            sample["game_state"]["environment"]["phase"] == "playing"
            and sample["metrics"]["attempts"] >= pointer_attempts_before + 1
        ),
        3,
        "pointer restart",
    )
    page.screenshot(path=str(evidence_dir / "restart-playing.png"))
    return {
        "entry": entry,
        "keyboard_flap": keyboard_flap,
        "dead": dead,
        "restarted": restarted,
        "pointer_flap": pointer_flap,
        "pointer_dead": pointer_dead,
        "pointer_restarted": pointer_restarted,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:4477/")
    parser.add_argument("--evidence-dir", type=Path, default=Path("verifier-artifacts"))
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    evidence: dict[str, Any] = {"url": args.url}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 960, "height": 720})
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.gameAPI && window.gameAPI.getState")
        page.evaluate("window.gameAPI.init({seed: 42, level: 1})")

        try:
            lab = run_lab(page, args.evidence_dir)
            evidence["flight_lab"] = lab
            outcomes = [
                run["final"]["game_state"]["environment"]["flight_lab"]["outcome"]
                for run in lab
            ]
            contacts = [
                run["final"]["game_state"]["environment"]["flight_lab"]["visual_audit"][
                    "contact_visible"
                ]
                for run in lab
            ]
            if outcomes != ["clear", "clear", "bump"]:
                failures.append(f"drill outcomes were {outcomes}")
            if contacts != [False, False, True]:
                failures.append(f"visible contact markers were {contacts}")
            for run in lab:
                if run["frozen_signature"] != run["stable_signature"]:
                    failures.append(f"{run['label']} result did not remain frozen")

            final_lab = lab[-1]["final"]["game_state"]["environment"]["flight_lab"]
            if final_lab["score"] != 2 or final_lab["viewed"] != 3:
                failures.append(
                    f"lab ledger was score={final_lab['score']} viewed={final_lab['viewed']}"
                )
            if lab[0]["final"]["debug"]["collision"] is not None:
                failures.append("tap drill retained a collision")
            tap_lab = lab[0]["final"]["game_state"]["environment"]["flight_lab"]
            held_lab = lab[1]["final"]["game_state"]["environment"]["flight_lab"]
            tap_receipt = [
                [edge["kind"], edge["step"]]
                for edge in tap_lab["input_receipt"]
            ]
            held_receipt = [
                [edge["kind"], edge["step"]]
                for edge in held_lab["input_receipt"]
            ]
            if tap_receipt != [["press", 0], ["release", 0]]:
                failures.append(f"tap receipt was {tap_receipt}")
            if held_receipt != [["press", 0], ["release", 3]]:
                failures.append(f"held receipt was {held_receipt}")
            if (
                tap_lab["target_impulse"] != 220
                or held_lab["target_impulse"] != 250
                or tap_lab["target_impulse"] == held_lab["target_impulse"]
            ):
                failures.append("tap and held target impulses were not distinct")
            if (
                abs(tap_lab["actual_impulse"] - tap_lab["target_impulse"]) > 0.1
                or abs(held_lab["actual_impulse"] - held_lab["target_impulse"]) > 0.1
            ):
                failures.append(
                    "actual impulses missed targets: "
                    f"tap={tap_lab['actual_impulse']}/{tap_lab['target_impulse']} "
                    f"held={held_lab['actual_impulse']}/{held_lab['target_impulse']}"
                )
            late_collision = lab[2]["final"]["debug"]["collision"]
            late_lab = lab[2]["final"]["game_state"]["environment"]["flight_lab"]
            late_audit = late_lab["visual_audit"]
            if (
                not late_collision
                or late_collision["kind"] != "pipe"
                or late_collision.get("interval_start") is None
                or late_collision.get("interval_end") is None
                or not late_collision.get("motion_segment")
            ):
                failures.append("late drill did not retain swept pipe contact")
            if (
                not late_audit.get("contact_interval")
                or not late_audit.get("motion_segment")
                or late_audit["contact_interval"]["end"]
                    <= late_audit["contact_interval"]["start"]
            ):
                failures.append("late contact interval telemetry was absent")
            if any(
                event["type"] == "score"
                for event in lab[2]["final"]["debug"]["recent_events"]
            ):
                failures.append("late ledger credit committed before collision")

            trajectories = {
                "tap": trajectory_profile(
                    lab[0]["final"],
                    [185, 150, 115, 85],
                ),
                "held": trajectory_profile(
                    lab[1]["final"],
                    [195, 170, 140, 110, 85],
                ),
            }
            evidence["trajectory_profiles"] = trajectories
            for name, profile in trajectories.items():
                if (
                    not profile["all_present"]
                    or profile["sample_count"] < 27
                    or profile["max_error"] is None
                    or profile["max_error"] > 1.6
                ):
                    failures.append(
                        f"{name} trajectory missed its target envelope: {profile}"
                    )

            normal = run_normal_route(page, args.evidence_dir)
            evidence["normal_scoring"] = normal
            if normal["finish_reason"] != "score":
                failures.append(f"normal route ended with {normal['finish_reason']}")
            if normal["final"]["terminal"]["isTerminal"]:
                failures.append("normal scoring route ended in collision")
            if normal["final"]["metrics"]["pipes_passed"] < 3:
                failures.append("normal route did not score three pipes")
            if score_pipe_ids(normal)[:3] != [1, 2, 3]:
                failures.append(f"normal route credited {score_pipe_ids(normal)}")

            restart = check_restart_and_controls(page, args.evidence_dir)
            evidence["restart_and_controls"] = restart
            if restart["dead"]["terminal"]["reason"] != "ground":
                failures.append("ordinary continuation did not end at the ground")
            if restart["pointer_flap"]["game_state"]["player"]["vy"] >= -180:
                failures.append("pointer flap was not applied after restart")
            for source, sample in [
                ("keyboard", restart["keyboard_flap"]),
                ("pointer", restart["pointer_flap"]),
            ]:
                edges = same_tick_edges(sample, source)
                if (
                    [[edge["kind"], edge["source"]] for edge in edges]
                    != [["press", source], ["release", source]]
                    or edges[0]["elapsed"] != edges[1]["elapsed"]
                ):
                    failures.append(f"{source} same-tick receipt was {edges}")
            if restart["pointer_dead"]["terminal"]["reason"] != "ground":
                failures.append("pointer restart path did not first reach death")
            if (
                restart["pointer_restarted"]["metrics"]["attempts"]
                != restart["pointer_dead"]["metrics"]["attempts"] + 1
            ):
                failures.append("pointer restart did not restore a new run")
        except Exception as exc:
            failures.append(f"browser replay error: {type(exc).__name__}: {exc}")
            evidence["replay_exception"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
        finally:
            release_inputs(page)
            page.screenshot(path=str(args.evidence_dir / "final.png"))
            browser.close()

    evidence["failures"] = failures
    (args.evidence_dir / "state-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        raise AssertionError("; ".join(failures))
    print(json.dumps({"status": "pass", "drills": ["clear", "clear", "bump"], "score": 3}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
