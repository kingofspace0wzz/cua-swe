#!/usr/bin/env python3
"""Deterministic non-model CUA replay for the Storybook resize task."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Replay:
    def __init__(self, launcher: Path, url: str, rollout: Path) -> None:
        self.launcher = launcher
        self.url = url
        self.rollout = rollout
        self.commands: list[dict[str, Any]] = []

    def command(self, *arguments: str) -> dict[str, Any]:
        argv = [str(self.launcher), *arguments]
        completed = subprocess.run(
            argv,
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        record = {
            "argv": argv,
            "exit_code": completed.returncode,
            "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
            "stderr": completed.stderr,
        }
        self.commands.append(record)
        if completed.returncode != 0:
            raise RuntimeError(
                f"CUA command failed ({completed.returncode}): {completed.stderr.strip()}"
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CUA command returned non-JSON output") from exc

    def start(self, name: str) -> Path:
        session = self.rollout / f"{name}-session.json"
        self.command(
            "start",
            "--url",
            self.url,
            "--artifacts-dir",
            str(self.rollout / name),
            "--session-file",
            str(session),
            "--viewport",
            "1440x1000",
        )
        return session

    def observe(self, session: Path) -> dict[str, Any]:
        return self.command("observe", "--session-file", str(session))["observation"]

    def act(self, session: Path, kind: str, **options: int | str) -> dict[str, Any]:
        arguments = ["act", "--session-file", str(session), "--kind", kind]
        for name, value in options.items():
            arguments.extend([f"--{name.replace('_', '-')}", str(value)])
        return self.command(*arguments)["observation"]

    def stop(self, session: Path) -> None:
        self.command("stop", "--session-file", str(session))


def _elements(observation: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = observation.get("metadata")
    elements = metadata.get("elements") if isinstance(metadata, dict) else None
    if not isinstance(elements, list):
        raise RuntimeError("CUA observation lacks interactive element metadata")
    return [element for element in elements if isinstance(element, dict)]


def _find_element(
    observation: dict[str, Any],
    *,
    text: str | None = None,
    data_tag: str | None = None,
    aria_label: str | None = None,
) -> dict[str, Any]:
    matches = []
    for element in _elements(observation):
        if text is not None and str(element.get("text") or "").strip() != text:
            continue
        if data_tag is not None and element.get("data_tag") != data_tag:
            continue
        if aria_label is not None and element.get("aria_label") != aria_label:
            continue
        matches.append(element)
    if not matches:
        target = f"text={text!r}, data_tag={data_tag!r}, aria_label={aria_label!r}"
        raise RuntimeError(f"CUA observation lacks required element: {target}")
    return matches[0]


def _click(replay: Replay, session: Path, observation: dict[str, Any], **target: str) -> dict[str, Any]:
    element = _find_element(observation, **target)
    return replay.act(
        session,
        "click",
        x=int(element["center_x"]),
        y=int(element["center_y"]),
    )


def _settle(
    replay: Replay,
    session: Path,
    observation: dict[str, Any],
    steps: int = 2,
) -> dict[str, Any]:
    settled = observation
    for _ in range(steps):
        settled = replay.act(session, "wait")
    return settled


def _document_signature(observation: dict[str, Any]) -> dict[str, Any]:
    metadata = observation.get("metadata")
    document = metadata.get("document") if isinstance(metadata, dict) else None
    if not isinstance(document, dict) or not isinstance(document.get("time_origin"), (int, float)):
        raise RuntimeError("CUA observation lacks document identity metadata")
    return document


def _viewport(observation: dict[str, Any]) -> dict[str, int]:
    metadata = observation.get("metadata")
    viewport = metadata.get("viewport") if isinstance(metadata, dict) else None
    if not isinstance(viewport, dict):
        raise RuntimeError("CUA observation lacks viewport metadata")
    return {"width": int(viewport["width"]), "height": int(viewport["height"])}


def _assert_retained(
    observation: dict[str, Any],
    *,
    url: str,
    document: dict[str, Any],
    viewport: dict[str, int],
) -> None:
    if observation.get("url") != url:
        raise RuntimeError("same-page resize changed the page URL")
    if _document_signature(observation) != document:
        raise RuntimeError("same-page resize changed the document identity")
    if _viewport(observation) != viewport:
        raise RuntimeError(f"resize produced the wrong viewport: {_viewport(observation)}")


def _assert_component_two_selected(observation: dict[str, Any]) -> None:
    checkbox = _find_element(observation, data_tag="component-two")
    if checkbox.get("checked") is not True:
        raise RuntimeError("component-two filter selection was not retained")


def _visible_explorer_ids(observation: dict[str, Any]) -> list[str]:
    return [
        str(element["id"])
        for element in _elements(observation)
        if element.get("tag") == "button"
        and element.get("id")
        and element.get("aria_controls")
    ]


def _assert_exact_component_two_list(observation: dict[str, Any], label: str) -> None:
    expected = ["core-tags-config"]
    actual = _visible_explorer_ids(observation)
    if actual != expected:
        raise RuntimeError(f"{label}: expected explorer entries {expected}, found {actual}")


def run_replay(
    launcher: Path,
    url: str,
    rollout: Path,
    *,
    expected_outcome: str = "repaired",
) -> dict[str, Any]:
    rollout.mkdir(parents=True, exist_ok=False)
    replay = Replay(launcher, url, rollout)
    evidence: dict[str, Any] = {
        "kind": "non_model_storybook_retained_page_resize_capability",
        "started_at": _now(),
        "model_invoked": False,
        "scored_evaluation": False,
        "url": url,
        "expected_outcome": expected_outcome,
    }
    filtered_session: Path | None = None
    control_session: Path | None = None
    current_step = "start"
    try:
        filtered_session = replay.start("filtered")
        wide = replay.observe(filtered_session)
        document = _document_signature(wide)
        _assert_retained(
            wide,
            url=str(wide["url"]),
            document=document,
            viewport={"width": 1440, "height": 1000},
        )

        opened_filters = _click(replay, filtered_session, wide, text="Tag filters")
        selected = _click(
            replay,
            filtered_session,
            opened_filters,
            data_tag="component-two",
        )
        _assert_component_two_selected(selected)
        dismissed = _click(replay, filtered_session, selected, text="Tag filters")
        current_step = "wide_exact_filtered_list"
        _assert_exact_component_two_list(dismissed, "wide filtered state")
        page_url = str(dismissed["url"])
        if _document_signature(dismissed) != document:
            raise RuntimeError("filter interaction unexpectedly replaced the document")

        narrow = replay.act(filtered_session, "resize", width=500, height=900)
        narrow = _settle(replay, filtered_session, narrow)
        _assert_retained(
            narrow,
            url=page_url,
            document=document,
            viewport={"width": 500, "height": 900},
        )
        current_step = "first_narrow_open"
        mobile_open = _click(
            replay,
            filtered_session,
            narrow,
            aria_label="Open navigation menu",
        )
        mobile_open = _settle(replay, filtered_session, mobile_open, steps=4)
        current_step = "first_narrow_exact_filtered_list"
        _assert_exact_component_two_list(
            mobile_open,
            "first filtered mobile transition",
        )
        mobile_filters = _click(
            replay,
            filtered_session,
            mobile_open,
            text="Tag filters",
        )
        mobile_filters = _settle(replay, filtered_session, mobile_filters)
        _assert_component_two_selected(mobile_filters)
        mobile_filters_closed = _click(
            replay,
            filtered_session,
            mobile_filters,
            text="Tag filters",
        )
        mobile_filters_closed = _settle(replay, filtered_session, mobile_filters_closed)
        mobile_closed = _click(
            replay,
            filtered_session,
            mobile_filters_closed,
            aria_label="Close menu",
        )
        mobile_closed = _settle(replay, filtered_session, mobile_closed)

        wide_again = replay.act(filtered_session, "resize", width=1440, height=1000)
        wide_again = _settle(replay, filtered_session, wide_again)
        _assert_retained(
            wide_again,
            url=page_url,
            document=document,
            viewport={"width": 1440, "height": 1000},
        )
        current_step = "wide_round_trip_exact_filtered_list"
        _assert_exact_component_two_list(wide_again, "wide round trip")
        wide_filters = _click(replay, filtered_session, wide_again, text="Tag filters")
        _assert_component_two_selected(wide_filters)
        wide_filters_closed = _click(
            replay,
            filtered_session,
            wide_filters,
            text="Tag filters",
        )

        narrow_repeat = replay.act(filtered_session, "resize", width=500, height=900)
        narrow_repeat = _settle(replay, filtered_session, narrow_repeat)
        _assert_retained(
            narrow_repeat,
            url=page_url,
            document=document,
            viewport={"width": 500, "height": 900},
        )
        mobile_repeat = _click(
            replay,
            filtered_session,
            narrow_repeat,
            aria_label="Open navigation menu",
        )
        mobile_repeat = _settle(replay, filtered_session, mobile_repeat, steps=4)
        current_step = "repeat_narrow_exact_filtered_list"
        _assert_exact_component_two_list(
            mobile_repeat,
            "repeated filtered mobile transition",
        )
        repeat_filters = _click(
            replay,
            filtered_session,
            mobile_repeat,
            text="Tag filters",
        )
        repeat_filters = _settle(replay, filtered_session, repeat_filters)
        _assert_component_two_selected(repeat_filters)
        replay.stop(filtered_session)
        filtered_session = None

        control_session = replay.start("unfiltered-control")
        control_wide = replay.observe(control_session)
        control_wide = _settle(replay, control_session, control_wide, steps=4)
        control_url = str(control_wide["url"])
        control_document = _document_signature(control_wide)
        control_narrow = replay.act(control_session, "resize", width=500, height=900)
        control_narrow = _settle(replay, control_session, control_narrow)
        _assert_retained(
            control_narrow,
            url=control_url,
            document=control_document,
            viewport={"width": 500, "height": 900},
        )
        control_open = _click(
            replay,
            control_session,
            control_narrow,
            aria_label="Open navigation menu",
        )
        control_open = _settle(replay, control_session, control_open, steps=4)
        current_step = "unfiltered_control_list"
        unfiltered_ids = _visible_explorer_ids(control_open)
        if len(unfiltered_ids) < 40:
            raise RuntimeError(
                "unfiltered mobile control has only "
                f"{len(unfiltered_ids)} explorer entries"
            )
        replay.stop(control_session)
        control_session = None

        evidence.update(
            {
                "observed_outcome": "repaired",
                "filtered_session": {
                    "session_file": str(replay.rollout / "filtered-session.json"),
                    "document": document,
                    "url": page_url,
                    "resize_sequence": ["1440x1000", "500x900", "1440x1000", "500x900"],
                    "component_two_retained": True,
                },
                "unfiltered_control": {
                    "session_file": str(replay.rollout / "unfiltered-control-session.json"),
                    "document": control_document,
                    "url": control_url,
                    "resize_sequence": ["1440x1000", "500x900"],
                    "healthy": True,
                },
            }
        )
        if expected_outcome == "broken-baseline":
            evidence.update(
                {
                    "status": "fail",
                    "expectation_met": False,
                    "error": "broken baseline unexpectedly completed the repaired replay",
                }
            )
        else:
            evidence.update({"status": "pass", "expectation_met": True})
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        missing_first_narrow_menu = (
            current_step == "first_narrow_open"
            and "aria_label='Open navigation menu'" in error
        )
        empty_first_narrow_filtered_list = (
            current_step == "first_narrow_exact_filtered_list"
            and "expected explorer entries ['core-tags-config'], found []" in error
        )
        expected_baseline_failure = expected_outcome == "broken-baseline" and (
            missing_first_narrow_menu or empty_first_narrow_filtered_list
        )
        evidence.update(
            {
                "status": "pass" if expected_baseline_failure else "fail",
                "expectation_met": expected_baseline_failure,
                "observed_outcome": "broken",
                "failure_step": current_step,
                "observed_error": error,
            }
        )
        if not expected_baseline_failure:
            evidence["error"] = error
    finally:
        for session in (filtered_session, control_session):
            if session is not None:
                try:
                    replay.stop(session)
                except Exception:
                    pass
        evidence["commands"] = replay.commands
        evidence["finished_at"] = _now()
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument(
        "--expected-outcome",
        choices=("repaired", "broken-baseline"),
        default="repaired",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence = run_replay(
        args.launcher,
        args.url,
        args.rollout,
        expected_outcome=args.expected_outcome,
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
