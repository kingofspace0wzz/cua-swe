#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


def snapshot(page: Page) -> dict:
    return page.evaluate("window.gameAPI.getState()")


def wait_state(page: Page, expression: str, timeout_ms: int = 12000) -> dict:
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
        failures.append(f"{route}: the final visible return did not clear the relay")
    if state["score"] != 500 or relay["contacts"] != 2:
        failures.append(f"{route}: completion was not credited exactly once: {state}")
    if relay["commits"] != 2 or relay["pending"] != 0:
        failures.append(f"{route}: delayed settlement did not finish exactly once: {state}")
    if relay["dropped"] != 0:
        failures.append(f"{route}: a reached relay settlement was discarded: {state}")
    if relay.get("withdrawn") != 1:
        failures.append(f"{route}: the recalled pass was not retired exactly once: {state}")


def replay_instructed_route(page: Page, evidence_dir: Path) -> tuple[dict, list[str]]:
    failures: list[str] = []
    page.evaluate("window.gameAPI.reset({seed: 73, level: 3})")
    initial = snapshot(page)
    capture(page, evidence_dir, "primed-00-initial", initial)
    if (
        initial["relay"]["phase"] != "armed"
        or initial["relay"]["contacts"] != 1
        or initial["relay"]["commits"] != 1
        or initial["score"] != 0
        or initial["lives"] != 3
        or not initial["orb"]["attached"]
    ):
        failures.append(f"selective: invalid initial state: {initial}")

    page.keyboard.press("Space")
    recalled_bounce = wait_state(
        page,
        "window.gameAPI.getState().metrics.bounces >= 1 && "
        "window.gameAPI.getState().relay.pending === 1 && "
        "!window.gameAPI.getState().orb.attached",
    )
    capture(page, evidence_dir, "primed-01-recall-reached", recalled_bounce)
    if (
        recalled_bounce["relay"]["phase"] != "armed"
        or recalled_bounce["metrics"]["launches"] != 1
        or recalled_bounce["relay"]["contacts"] != 1
        or recalled_bounce["relay"]["commits"] != 1
    ):
        failures.append(
            f"selective: first launch did not reach one pending return: "
            f"{recalled_bounce}"
        )

    recall_due = recalled_bounce["relay"]["nextDue"]
    page.keyboard.press("KeyR")
    recalled_dock = wait_state(
        page,
        "window.gameAPI.getState().orb.attached && "
        "window.gameAPI.getState().orb.attachReason === 'manual-redock'",
    )
    capture(page, evidence_dir, "primed-02-recalled-dock", recalled_dock)
    if recalled_dock["lives"] != 3 or recalled_dock["relay"]["phase"] != "armed":
        failures.append(f"selective: R did not visibly recall the pass: {recalled_dock}")

    recall_settled = wait_state(
        page,
        f"window.gameAPI.getState().metrics.elapsed >= {recall_due + 0.2} || "
        "window.gameAPI.getState().terminal.isTerminal",
    )
    recall_settled = snapshot(page)
    capture(page, evidence_dir, "primed-03-recall-settlement", recall_settled)
    if recall_settled["terminal"]["isTerminal"]:
        failures.append(
            f"selective: the explicitly recalled pass completed the relay: {recall_settled}"
        )
        return recall_settled, failures
    if (
        recall_settled["relay"]["phase"] != "armed"
        or recall_settled["score"] != 0
        or recall_settled["relay"]["pending"] != 0
    ):
        failures.append(
            f"selective: the relay did not remain armed after recall: {recall_settled}"
        )
    if recall_settled["relay"]["dropped"] != 0:
        failures.append(
            f"selective: the recalled pass aged into a dropped delivery: {recall_settled}"
        )

    page.keyboard.press("Space")
    kept_bounce = wait_state(
        page,
        "window.gameAPI.getState().metrics.bounces >= 2 && "
        "window.gameAPI.getState().relay.pending === 1 && "
        "!window.gameAPI.getState().orb.attached",
    )
    capture(page, evidence_dir, "primed-04-kept-reached", kept_bounce)
    if kept_bounce["metrics"]["launches"] != 2:
        failures.append(f"selective: second launch count was not exact: {kept_bounce}")

    final_replacement = wait_state(
        page,
        "window.gameAPI.getState().orb.attached && "
        "window.gameAPI.getState().metrics.losses === 1",
    )
    capture(page, evidence_dir, "primed-05-natural-replacement", final_replacement)
    if (
        final_replacement["orb"]["attachReason"] != "life-replacement"
        or final_replacement["lives"] != 2
        or final_replacement["relay"]["pending"] != 1
        or final_replacement["ownership"]["port"] != "receiver"
    ):
        failures.append(
            f"selective: the kept pass missed its replacement checkpoint: "
            f"{final_replacement}"
        )

    before_tap_x = final_replacement["orb"]["x"]
    page.keyboard.press("ArrowLeft")
    shifted = wait_state(
        page,
        "window.gameAPI.getState().ownership.port === 'west' && "
        "window.gameAPI.getState().orb.attached",
    )
    capture(page, evidence_dir, "primed-06-one-left-tap", shifted)
    if shifted["relay"]["pending"] != 1 or shifted["orb"]["x"] >= before_tap_x:
        failures.append(
            f"selective: one Left tap missed the pending dock shift: {shifted}"
        )

    final = wait_state(
        page,
        "window.gameAPI.getState().relay.pending === 0 || "
        "window.gameAPI.getState().terminal.isTerminal",
    )
    page.wait_for_timeout(120)
    final = snapshot(page)
    capture(page, evidence_dir, "primed-07-settled", final)
    if final["ownership"]["port"] != "west":
        failures.append(f"selective: the instructed dock shift was not retained: {final}")
    assert_completed(final, "selective", failures)
    return final, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:52840/?challenge=relay-circuit",
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

        final, route_failures = replay_instructed_route(page, args.evidence_dir)
        evidence["instructed_route_final"] = final
        failures.extend(route_failures)
        browser.close()

    evidence["failures"] = failures
    evidence["status"] = "pass" if not failures else "fail"
    (args.evidence_dir / "replay-summary.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        raise AssertionError("; ".join(failures))
    print(json.dumps({
        "status": "pass",
        "score": 500,
        "routes": 1,
        "browser_actions": 4,
        "recalls": 1,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
