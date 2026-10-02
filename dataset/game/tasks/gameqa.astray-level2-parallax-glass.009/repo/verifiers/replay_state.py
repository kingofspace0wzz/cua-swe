#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import struct
import zlib
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from playwright.sync_api import Page
else:
    Page = Any

PixelPredicate = Callable[[int, int, int, int], bool]


def state(page: Page) -> dict:
    return page.evaluate("window.gameAPI.getState()")


def player(snapshot: dict) -> dict:
    current = snapshot["game_state"]["player"]
    if current is None:
        raise AssertionError(f"player snapshot unavailable: {snapshot}")
    return current


def speed(snapshot: dict) -> float:
    current = player(snapshot)
    return math.hypot(current["vx"] or 0.0, current["vy"] or 0.0)


def wait_for_level(page: Page, level: int, *, samples: int = 240) -> dict:
    observed = state(page)
    for _ in range(samples):
        if (
            observed["status"] == "playing"
            and observed["game_state"]["level"] == level
            and not observed["terminal"]["isTerminal"]
        ):
            return observed
        page.wait_for_timeout(25)
        observed = state(page)
    raise AssertionError(f"Level {level} did not settle: {observed}")


def wait_for_keyboard_restart(
    page: Page, previous_restart_count: int, *, samples: int = 240
) -> dict:
    observed = state(page)
    for _ in range(samples):
        restart_count = observed["debug"]["native_restart_count"]
        current = player(observed)
        if (
            observed["status"] == "playing"
            and observed["game_state"]["level"] == 2
            and restart_count is not None
            and restart_count > previous_restart_count
            and math.hypot(current["x"] - 1.0, current["y"] - 1.0) < 0.14
        ):
            return observed
        page.wait_for_timeout(25)
        observed = state(page)
    raise AssertionError(f"ordinary R restart did not restore Level 2: {observed}")


def pulse(page: Page, key: str, duration_ms: int = 100) -> None:
    page.keyboard.down(key)
    page.wait_for_timeout(duration_ms)
    page.keyboard.up(key)
    page.wait_for_timeout(100)


def paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    return min(
        (
            (abs(estimate - left), left),
            (abs(estimate - up), up),
            (abs(estimate - upper_left), upper_left),
        ),
        key=lambda item: item[0],
    )[1]


def decode_png(data: bytes) -> tuple[int, int, int, list[bytes]]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError("canvas screenshot is not a PNG")
    offset = 8
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if (
        width is None
        or height is None
        or bit_depth != 8
        or color_type not in (2, 6)
        or interlace != 0
    ):
        raise AssertionError("unsupported screenshot encoding")

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    rows: list[bytes] = []
    cursor = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scanline = raw[cursor : cursor + stride]
        cursor += stride
        reconstructed = bytearray(stride)
        for index, value in enumerate(scanline):
            left = reconstructed[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                predictor = paeth(left, up, upper_left)
            else:
                raise AssertionError(f"unsupported PNG filter {filter_type}")
            reconstructed[index] = (value + predictor) & 0xFF
        rows.append(bytes(reconstructed))
        previous = reconstructed
    return width, height, channels, rows


def components(
    data: bytes, predicate: PixelPredicate, *, minimum_pixels: int = 8
) -> list[dict]:
    width, height, channels, rows = decode_png(data)
    x0, x1 = int(width * 0.08), int(width * 0.92)
    y0, y1 = int(height * 0.06), int(height * 0.95)
    selected: set[tuple[int, int]] = set()
    for y in range(y0, y1):
        for x in range(x0, x1):
            start = x * channels
            red, green, blue = rows[y][start : start + 3]
            alpha = rows[y][start + 3] if channels == 4 else 255
            if predicate(red, green, blue, alpha):
                selected.add((x, y))

    found: list[dict] = []
    while selected:
        seed = selected.pop()
        queue = deque([seed])
        points = [seed]
        while queue:
            x, y = queue.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in selected:
                    selected.remove(neighbor)
                    queue.append(neighbor)
                    points.append(neighbor)
        if len(points) >= minimum_pixels:
            found.append(
                {
                    "pixels": len(points),
                    "x": sum(point[0] for point in points) / len(points),
                    "y": sum(point[1] for point in points) / len(points),
                }
            )
    return sorted(found, key=lambda item: item["pixels"], reverse=True)


def analyze_canvas(data: bytes) -> dict:
    predicates: dict[str, PixelPredicate] = {
        "magenta": lambda r, g, b, a: (
            a > 180 and r > 165 and g < 115 and b > 145 and abs(r - b) < 85
        ),
        "green": lambda r, g, b, a: (
            a > 180 and 50 < r < 145 and g > 140 and 65 < b < 135
            and g > r * 1.25
        ),
        "amber": lambda r, g, b, a: (
            a > 180 and r > 145 and g > 180 and 70 < b < 135
            and r > b * 1.25
            and not (r > 175 and g > 125 and b < 115 and r > b * 1.7)
        ),
        "teal": lambda r, g, b, a: (
            a > 180 and r < 130 and g > 165 and b > 135 and g > r * 1.35
        ),
        "red": lambda r, g, b, a: (
            a > 180 and r > 165 and g < 125 and b < 130 and r > g * 1.4
        ),
        "gold": lambda r, g, b, a: (
            a > 180 and r > 175 and g > 125 and b < 115 and r > b * 1.7
        ),
    }
    groups = {
        name: components(data, predicate) for name, predicate in predicates.items()
    }
    return {
        "component_counts": {name: len(items) for name, items in groups.items()},
        "pixel_counts": {
            name: sum(item["pixels"] for item in items)
            for name, items in groups.items()
        },
        "centroids": {
            name: [{"x": item["x"], "y": item["y"]} for item in items]
            for name, items in groups.items()
        },
    }


def capture(page: Page, path: Path) -> dict:
    data = page.locator("canvas").first.screenshot(path=str(path))
    return analyze_canvas(data)


def prove_idle_without_input(page: Page) -> dict:
    before = state(page)
    page.wait_for_timeout(1200)
    after = state(page)
    first = player(before)
    second = player(after)
    drift = math.hypot(second["x"] - first["x"], second["y"] - first["y"])
    if drift > 0.06 or speed(after) > 0.04:
        raise AssertionError(f"true no-input control moved the ball: {after}")
    return after


def require_opening(render: dict, run_number: int) -> None:
    counts = render["component_counts"]
    if (
        counts["magenta"] < 3
        or counts["green"] != 0
        or counts["amber"] != 0
        or counts["red"] < 1
    ):
        raise AssertionError(
            f"run {run_number}: opening glass gallery unresolved: {render}"
        )
    if counts["gold"] < 1:
        raise AssertionError(f"run {run_number}: player ball not visible: {render}")


def require_mid_run(render: dict, run_number: int) -> None:
    counts = render["component_counts"]
    if (
        counts["green"] not in (1, 2)
        or counts["amber"] not in (1, 2)
        or counts["magenta"] < 1
        or counts["red"] < 1
        or counts["teal"] != 0
    ):
        raise AssertionError(
            f"run {run_number}: progressive glass signature is wrong: {render}"
        )


def require_complete(render: dict, run_number: int) -> None:
    counts = render["component_counts"]
    pixels = render["pixel_counts"]
    if (
        counts["green"] < 4
        or counts["amber"] < 3
        or counts["magenta"] != 0
        or pixels["red"] > 1000
        or pixels["teal"] > 1000
        or counts["gold"] < 1
    ):
        raise AssertionError(
            f"run {run_number}: completed glass gallery is wrong: {render}"
        )


def prove_released_movement(page: Page, reference: dict) -> dict:
    origin = player(reference)
    observed = state(page)
    for _ in range(18):
        current = player(observed)
        if math.hypot(current["x"] - origin["x"], current["y"] - origin["y"]) > 0.30:
            return observed
        pulse(page, "ArrowUp", 60)
        observed = state(page)
    raise AssertionError(f"ordinary movement did not continue beyond the crossbar: {observed}")


def run_trial(page: Page, evidence_dir: Path, run_number: int) -> dict:
    wait_for_level(page, 2)
    idle = prove_idle_without_input(page)
    page.wait_for_timeout(800)
    opening = capture(page, evidence_dir / f"run-{run_number}-opening.png")
    require_opening(opening, run_number)

    samples: list[dict] = []
    page.keyboard.down("ArrowUp")
    try:
        mid_state = idle
        for _ in range(80):
            page.wait_for_timeout(25)
            mid_state = state(page)
            samples.append(mid_state)
            if 2.05 < player(mid_state)["y"] < 2.45:
                break
        else:
            raise AssertionError(
                f"run {run_number}: Up did not reach the mixed gallery state: {mid_state}"
            )
        page.keyboard.up("ArrowUp")
        mid = capture(page, evidence_dir / f"run-{run_number}-mid-glass.png")
        require_mid_run(mid, run_number)
        complete_state = mid_state
        for _ in range(120):
            page.wait_for_timeout(25)
            complete_state = state(page)
            samples.append(complete_state)
            if player(complete_state)["y"] > 4.58:
                break
        else:
            raise AssertionError(
                f"run {run_number}: gallery traversal did not clear the bar: {complete_state}"
            )
    finally:
        page.keyboard.up("ArrowUp")

    page.wait_for_timeout(80)
    complete = capture(page, evidence_dir / f"run-{run_number}-complete-glass.png")
    require_complete(complete, run_number)

    positions = [player(snapshot) for snapshot in samples]
    y_values = [point["y"] for point in positions]
    if max(y_values) - min(y_values) < 3.35:
        raise AssertionError(
            f"run {run_number}: Up did not drive the glass gallery: {positions}"
        )

    moved = prove_released_movement(page, complete_state)
    return {
        "idle": idle,
        "opening_render": opening,
        "mid_render": mid,
        "complete_render": complete,
        "trajectory": samples,
        "released_movement": moved,
    }


def write_evidence(path: Path, evidence: dict) -> None:
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:42833/?level=2")
    parser.add_argument(
        "--evidence-dir", type=Path, default=Path("verifier-artifacts")
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    evidence: dict[str, object] = {}
    failure: str | None = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--single-process", "--autoplay-policy=no-user-gesture-required"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        try:
            page.goto(args.url, wait_until="load")
            page.wait_for_function("window.gameAPI && window.gameAPI.getState")

            selected = page.evaluate("window.gameAPI.init({level: 3})")
            if not selected["ok"]:
                raise AssertionError(f"Level 3 selection failed: {selected}")
            evidence["level_three"] = wait_for_level(page, 3)

            # A held key across in-place selection must be neutralized.
            page.keyboard.down("ArrowLeft")
            selected = page.evaluate("window.gameAPI.reset({level: 2})")
            page.keyboard.up("ArrowLeft")
            if not selected["ok"]:
                raise AssertionError(f"Level 2 selection failed: {selected}")

            first_run = run_trial(page, args.evidence_dir, 1)
            evidence["run_1"] = first_run
            restart_count = first_run["released_movement"]["debug"][
                "native_restart_count"
            ]
            if restart_count is None:
                raise AssertionError("restart counter unavailable")

            page.keyboard.press("r")
            evidence["keyboard_restart"] = wait_for_keyboard_restart(
                page, restart_count
            )
            evidence["run_2"] = run_trial(page, args.evidence_dir, 2)
        except Exception as error:
            failure = str(error)
        finally:
            for key in ("ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"):
                try:
                    page.keyboard.up(key)
                except Exception:
                    pass
            browser.close()

    evidence["failure"] = failure
    write_evidence(args.evidence_dir / "level2-parallax-glass.json", evidence)
    if failure is not None:
        raise AssertionError(failure)
    print(
        json.dumps(
            {
                "status": "pass",
                "selected_levels": [3, 2],
                "runs": 2,
                "retained_screenshots": 6,
                "visual_sequence": "three_glass_signatures",
                "green_cores": 3,
                "amber_crowns": 3,
                "ordinary_restart": "pass",
                "idle_no_input": "pass",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
