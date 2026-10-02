#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


def snapshot(page: Page) -> dict:
    return page.evaluate("window.gameAPI.getState()")


def wait_state(page: Page, expression: str, timeout_ms: int = 9000) -> dict:
    page.wait_for_function(expression, timeout=timeout_ms)
    return snapshot(page)


def capture(page: Page, evidence_dir: Path, name: str, state: dict) -> None:
    (evidence_dir / f"{name}.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    page.screenshot(path=str(evidence_dir / f"{name}.png"))


def assert_completed(state: dict, route: str, failures: list[str]) -> None:
    relay = state["relay"]
    if state["terminal"]["outcome"] != "success" or relay["phase"] != "cleared":
        failures.append(f"{route}: the visible return bounce did not clear the relay")
    if state["score"] != 500 or relay["contacts"] != 2:
        failures.append(f"{route}: completion was not credited exactly once: {state}")
    if relay["commits"] != 2 or relay["pending"] != 0:
        failures.append(f"{route}: delayed settlement did not finish exactly once: {state}")
    if relay["dropped"] != 0:
        failures.append(f"{route}: a reached relay settlement was discarded: {state}")


def reach_return_bounce(
    page: Page,
    evidence_dir: Path,
    prefix: str,
    failures: list[str],
) -> dict:
    page.evaluate("window.gameAPI.reset({seed: 73, level: 3})")
    initial = snapshot(page)
    capture(page, evidence_dir, f"{prefix}-00-initial", initial)
    if initial["relay"]["phase"] != "idle" or initial["score"] != 0 or initial["lives"] != 3:
        failures.append(f"{prefix}: invalid initial state: {initial}")

    page.keyboard.press("Space")
    armed = wait_state(page, "window.gameAPI.getState().relay.phase === 'armed'")
    capture(page, evidence_dir, f"{prefix}-01-armed", armed)
    if (
        armed["relay"]["contacts"] != 1
        or armed["relay"]["commits"] != 1
        or armed["relay"]["pending"] != 0
    ):
        failures.append(f"{prefix}: first contact was not one settled arm: {armed}")

    replacement = wait_state(
        page,
        "window.gameAPI.getState().orb.attached && "
        "window.gameAPI.getState().metrics.losses === 1",
    )
    capture(page, evidence_dir, f"{prefix}-02-first-replacement", replacement)
    if (
        replacement["relay"]["phase"] != "armed"
        or replacement["orb"]["attachReason"] != "life-replacement"
        or replacement["lives"] != 2
    ):
        failures.append(f"{prefix}: first replacement did not preserve the armed relay: {replacement}")

    page.keyboard.press("Space")
    bounced = wait_state(
        page,
        "window.gameAPI.getState().metrics.bounces >= 2 && "
        "window.gameAPI.getState().relay.phase === 'armed'",
    )
    capture(page, evidence_dir, f"{prefix}-03-return-bounce", bounced)
    if bounced["relay"]["pending"] != 1:
        failures.append(f"{prefix}: return bounce did not reach delayed settlement: {bounced}")
    return bounced


def replay_plain_route(page: Page, evidence_dir: Path) -> tuple[dict, list[str]]:
    failures: list[str] = []
    reach_return_bounce(page, evidence_dir, "plain", failures)
    docked = wait_state(
        page,
        "window.gameAPI.getState().orb.attached && "
        "window.gameAPI.getState().metrics.losses === 2",
    )
    capture(page, evidence_dir, "plain-04-second-replacement", docked)
    if docked["orb"]["attachReason"] != "life-replacement" or docked["lives"] != 1:
        failures.append(f"plain: second replacement did not dock normally: {docked}")

    final = wait_state(
        page,
        "window.gameAPI.getState().relay.pending === 0 || "
        "window.gameAPI.getState().terminal.isTerminal",
    )
    page.wait_for_timeout(120)
    final = snapshot(page)
    capture(page, evidence_dir, "plain-05-settled", final)
    assert_completed(final, "plain", failures)
    return final, failures


def replay_shift_route(page: Page, evidence_dir: Path) -> tuple[dict, list[str]]:
    failures: list[str] = []
    reach_return_bounce(page, evidence_dir, "shift", failures)
    wait_state(
        page,
        "window.gameAPI.getState().orb.attached && "
        "window.gameAPI.getState().metrics.losses === 2",
    )
    page.keyboard.down("ArrowLeft")
    shifted = wait_state(page, "window.gameAPI.getState().ownership.port === 'west'")
    page.keyboard.up("ArrowLeft")
    capture(page, evidence_dir, "shift-04-docked-west", shifted)
    if shifted["relay"]["pending"] != 1 or shifted["orb"]["attachReason"] != "life-replacement":
        failures.append(f"shift: receiver moved outside the pending replacement window: {shifted}")

    final = wait_state(
        page,
        "window.gameAPI.getState().relay.pending === 0 || "
        "window.gameAPI.getState().terminal.isTerminal",
    )
    page.wait_for_timeout(120)
    final = snapshot(page)
    capture(page, evidence_dir, "shift-05-settled", final)
    if final["ownership"]["port"] != "west":
        failures.append(f"shift: protected receiver movement was not retained: {final}")
    assert_completed(final, "shift", failures)
    return final, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:51320/?challenge=relay-circuit",
    )
    parser.add_argument("--evidence-dir", type=Path, default=Path("verifier-artifacts"))
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    evidence: dict[str, object] = {"url": args.url}
    failures: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.gameAPI && window.gameAPI.getState")

        plain_final, plain_failures = replay_plain_route(page, args.evidence_dir)
        shift_final, shift_failures = replay_shift_route(page, args.evidence_dir)
        evidence["plain_route_final"] = plain_final
        evidence["shift_route_final"] = shift_final
        failures.extend(plain_failures)
        failures.extend(shift_failures)
        browser.close()

    evidence["failures"] = failures
    evidence["status"] = "pass" if not failures else "fail"
    (args.evidence_dir / "replay-summary.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        raise AssertionError("; ".join(failures))
    print(json.dumps({"status": "pass", "score": 500, "routes": 2}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
