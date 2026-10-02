from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:4173"
ARTIFACTS = ROOT / "verifier-artifacts"


def fail(message: str) -> None:
    raise SystemExit(f"responsive masonry verifier failed: {message}")


def server_ready() -> bool:
    try:
        with urlopen(URL, timeout=0.4) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status == 200 and "<title>Operations dashboard</title>" in body
    except (URLError, TimeoutError):
        return False


def start_server_if_needed() -> subprocess.Popen[str] | None:
    if server_ready():
        return None
    process = subprocess.Popen(
        ["npm", "run", "preview"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            fail(f"preview exited before verification\n{output}")
        if server_ready():
            return process
        time.sleep(0.1)
    process.terminate()
    fail("preview did not become ready")


def state(page, label: str) -> dict[str, object]:
    return page.evaluate(
        """label => {
          const rect = element => {
            const value = element.getBoundingClientRect();
            return {left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height};
          };
          const root = document.querySelector('[aria-label="Operations groups"]');
          const elements = [...root.querySelectorAll('[data-dashboard-group]')];
          const groups = Object.fromEntries(elements.map(element => [element.dataset.groupId, rect(element)]));
          const parseColor = value => {
            if (!value || value.trim().toLowerCase() === 'transparent') {
              return {r: 0, g: 0, b: 0, a: 0};
            }
            const parts = value.match(/[\d.]+/g)?.map(Number) || [];
            return {
              r: parts[0] || 0,
              g: parts[1] || 0,
              b: parts[2] || 0,
              a: parts.length > 3 ? parts[3] : 1,
            };
          };
          const luminance = color => {
            const channels = [color.r, color.g, color.b].map(value => {
              const normalized = value / 255;
              return normalized <= 0.03928
                ? normalized / 12.92
                : Math.pow((normalized + 0.055) / 1.055, 2.4);
            });
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
          };
          const contrast = (foreground, background) => {
            const blended = {
              r: foreground.r * foreground.a + background.r * (1 - foreground.a),
              g: foreground.g * foreground.a + background.g * (1 - foreground.a),
              b: foreground.b * foreground.a + background.b * (1 - foreground.a),
            };
            const first = luminance(blended);
            const second = luminance(background);
            return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
          };
          const backgroundFor = element => {
            for (let current = element; current; current = current.parentElement) {
              const color = parseColor(getComputedStyle(current).backgroundColor);
              if (color.a >= 0.95) return color;
            }
            return {r: 255, g: 255, b: 255, a: 1};
          };
          const textGeometry = element => {
            const rectangles = [];
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            for (let node = walker.nextNode(); node; node = walker.nextNode()) {
              if (!node.textContent?.trim()) continue;
              const range = document.createRange();
              range.selectNodeContents(node);
              rectangles.push(...[...range.getClientRects()]
                .map(value => ({left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height}))
                .filter(value => value.width > 0.5 && value.height > 0.5));
            }
            const bounds = rect(element);
            return {
              count: rectangles.length,
              within_element: rectangles.length > 0 && rectangles.every(value =>
                value.left >= bounds.left - 2
                && value.right <= bounds.right + 2
                && value.top >= bounds.top - 2
                && value.bottom <= bounds.bottom + 2
              ),
            };
          };
          const paintHit = (element, center, centerInViewport) => {
            if (!centerInViewport) return false;
            const probe = document.createElement('style');
            probe.textContent = '*,*::before,*::after{pointer-events:auto!important}';
            document.head.append(probe);
            const hit = document.elementFromPoint(center.x, center.y);
            probe.remove();
            return Boolean(hit && (hit === element || element.contains(hit)));
          };
          const pseudoCoversContent = element => {
            const bounds = rect(element);
            return ['::before', '::after'].some(selector => {
              const style = getComputedStyle(element, selector);
              if (
                !style
                || style.content === 'none'
                || style.content === 'normal'
                || style.display === 'none'
                || style.visibility !== 'visible'
              ) return false;
              const opacity = Number(style.opacity);
              const background = parseColor(style.backgroundColor);
              const hasOpaquePaint = background.a * (Number.isFinite(opacity) ? opacity : 1) >= 0.8;
              const hasImagePaint = style.backgroundImage !== 'none' && opacity >= 0.8;
              const hasShadowPaint = style.boxShadow !== 'none' && opacity >= 0.8;
              if (!hasOpaquePaint && !hasImagePaint && !hasShadowPaint) return false;
              if (!['absolute', 'fixed'].includes(style.position)) return false;
              if (Number.parseFloat(style.zIndex) < 0) return false;
              const inset = [style.top, style.right, style.bottom, style.left].map(Number.parseFloat);
              const coversByInset = inset.every(value => Number.isFinite(value) && Math.abs(value) <= 2);
              const width = Number.parseFloat(style.width);
              const height = Number.parseFloat(style.height);
              const coversBySize = Number.isFinite(width) && Number.isFinite(height)
                && width >= bounds.width - 4 && height >= bounds.height - 4;
              return coversByInset || coversBySize;
            });
          };
          const feature = element => {
            if (!element) return null;
            let effectiveOpacity = 1;
            let hiddenByDisplay = false;
            let hiddenByVisibility = false;
            let renderSuppressed = false;
            for (let current = element; current; current = current.parentElement) {
              const style = getComputedStyle(current);
              effectiveOpacity *= Number(style.opacity);
              for (const match of style.filter.matchAll(/opacity\(([^)]+)\)/g)) {
                const raw = match[1].trim();
                const value = raw.endsWith('%') ? Number.parseFloat(raw) / 100 : Number.parseFloat(raw);
                if (Number.isFinite(value)) effectiveOpacity *= value;
              }
              hiddenByDisplay ||= style.display === 'none';
              hiddenByVisibility ||= style.visibility !== 'visible';
              renderSuppressed ||= style.contentVisibility === 'hidden';
              renderSuppressed ||= style.clipPath !== 'none';
              renderSuppressed ||= style.maskImage !== 'none';
            }
            const bounds = rect(element);
            const center = {x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2};
            const centerInViewport = center.x >= 0 && center.x < innerWidth && center.y >= 0 && center.y < innerHeight;
            const hit = centerInViewport ? document.elementFromPoint(center.x, center.y) : null;
            const ownStyle = getComputedStyle(element);
            const foreground = parseColor(ownStyle.color);
            const textFill = parseColor(ownStyle.webkitTextFillColor || ownStyle.color);
            const background = backgroundFor(element);
            return {
              rect: bounds,
              text: element.innerText?.trim() || '',
              id: element.id || null,
              effective_opacity: effectiveOpacity,
              hidden_by_display: hiddenByDisplay,
              hidden_by_visibility: hiddenByVisibility,
              render_suppressed: renderSuppressed,
              center_in_viewport: centerInViewport,
              center_hit_matches: Boolean(hit && (hit === element || element.contains(hit))),
              paint_hit_matches: paintHit(element, center, centerInViewport),
              pseudo_covers_content: pseudoCoversContent(element),
              text_geometry: textGeometry(element),
              text_color_alpha: foreground.a,
              text_contrast: contrast(foreground, background),
              text_fill_alpha: textFill.a,
              text_fill_contrast: contrast(textFill, background),
              font_size: Number.parseFloat(ownStyle.fontSize) || 0,
            };
          };
          const featureSelectors = {
            lamps: {
              contents: ['.lamp-control'],
              controls: ['.lamp-control button'],
            },
            freezer: {
              contents: ['.mode-row', '.temperature-card'],
              controls: ['.mode-row button', '.temperature-card button'],
            },
            system: {
              contents: ['.system-status', '.chart-surface', '.system-action'],
              controls: ['.system-action'],
            },
          };
          const features = Object.fromEntries(elements.map(element => {
            const groupId = element.dataset.groupId;
            const selectors = featureSelectors[groupId];
            return [groupId, {
              labelled_by: element.getAttribute('aria-labelledby'),
              heading: feature(element.querySelector('h2')),
              contents: selectors.contents.map(selector => feature(element.querySelector(selector))),
              controls: selectors.controls.map(selector => feature(element.querySelector(selector))),
              labels: groupId === 'lamps'
                ? [feature(element.querySelector('.lamp-control span'))]
                : groupId === 'freezer'
                  ? [
                      feature(element.querySelector('.mode-row span')),
                      feature(element.querySelector('.temperature-card > span')),
                      feature(element.querySelector('[data-testid="temperature-target"]')),
                    ]
                  : [
                      feature(element.querySelector('.system-status span')),
                      feature(element.querySelector('.system-status strong')),
                      feature(element.querySelector('.chart-surface > span')),
                    ],
            }];
          }));
          const groupStyles = Object.fromEntries(elements.map(element => {
            const style = getComputedStyle(element);
            return [element.dataset.groupId, {
              display: style.display,
              visibility: style.visibility,
              opacity: Number(style.opacity),
            }];
          }));
          const overlaps = [];
          for (let first = 0; first < elements.length; first += 1) {
            for (let second = first + 1; second < elements.length; second += 1) {
              const a = groups[elements[first].dataset.groupId];
              const b = groups[elements[second].dataset.groupId];
              if (a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top) {
                overlaps.push([elements[first].dataset.groupId, elements[second].dataset.groupId]);
              }
            }
          }
          const temperature = document.querySelector('[data-testid="temperature-card"]');
          const t = rect(temperature);
          const top = document.elementFromPoint(t.left + t.width / 2, t.top + t.height / 2);
          return {
            label,
            viewport: {width: innerWidth, height: innerHeight},
            order: elements.map(element => element.dataset.groupId),
            count: elements.length,
            root: rect(root),
            groups,
            features,
            group_styles: groupStyles,
            overlaps,
            temperature_top_group: top?.closest('[data-dashboard-group]')?.dataset.groupId || null,
            document_overflow: document.documentElement.scrollWidth > innerWidth,
            document_height: document.documentElement.scrollHeight,
            controls: {
              lamp: root.querySelector('[data-group-id="lamps"] .lamp-control')?.innerText || null,
              lamp_button: root.querySelector('[data-group-id="lamps"] .lamp-control button')?.getAttribute('aria-label') || null,
              freezer: root.querySelector('[data-group-id="freezer"] .mode-row')?.innerText || null,
              temperature: root.querySelector('[data-testid="temperature-target"]')?.innerText || null,
              system: root.querySelector('[data-group-id="system"] .system-action')?.innerText || null,
            },
            layout_revision: Number(root.dataset.layoutRevision || 0),
          };
        }""",
        label,
    )


def resize(page, width: int, label: str) -> dict[str, object]:
    prior = page.evaluate("Number(document.querySelector('[aria-label=\"Operations groups\"]')?.dataset.layoutRevision || 0)")
    page.set_viewport_size({"width": width, "height": 760})
    page.wait_for_function(
        "prior => Number(document.querySelector('[aria-label=\"Operations groups\"]').dataset.layoutRevision || 0) > prior",
        arg=prior,
    )
    page.wait_for_timeout(80)
    return state(page, label)


def assert_actionable(locator, label: str) -> None:
    result = locator.evaluate(
        """element => {
          const rect = element.getBoundingClientRect();
          let opacity = 1;
          let visible = true;
          for (let current = element; current; current = current.parentElement) {
            const style = getComputedStyle(current);
            opacity *= Number(style.opacity);
            for (const match of style.filter.matchAll(/opacity\(([^)]+)\)/g)) {
              const raw = match[1].trim();
              const value = raw.endsWith('%') ? Number.parseFloat(raw) / 100 : Number.parseFloat(raw);
              if (Number.isFinite(value)) opacity *= value;
            }
            visible &&= style.display !== 'none' && style.visibility === 'visible';
            visible &&= style.contentVisibility !== 'hidden';
            visible &&= style.clipPath === 'none' && style.maskImage === 'none';
          }
          const x = rect.left + rect.width / 2;
          const y = rect.top + rect.height / 2;
          const hit = document.elementFromPoint(x, y);
          const style = getComputedStyle(element);
          const parseColor = value => {
            if (!value || value.trim().toLowerCase() === 'transparent') return {a: 0};
            const parts = value.match(/[\d.]+/g)?.map(Number) || [];
            return {a: parts.length > 3 ? parts[3] : 1};
          };
          const pseudoCoversContent = ['::before', '::after'].some(selector => {
            const pseudo = getComputedStyle(element, selector);
            if (
              !pseudo
              || pseudo.content === 'none'
              || pseudo.content === 'normal'
              || pseudo.display === 'none'
              || pseudo.visibility !== 'visible'
            ) return false;
            const pseudoOpacity = Number(pseudo.opacity);
            const backgroundAlpha = parseColor(pseudo.backgroundColor).a;
            const hasOpaquePaint = backgroundAlpha * (Number.isFinite(pseudoOpacity) ? pseudoOpacity : 1) >= 0.8;
            const hasImagePaint = pseudo.backgroundImage !== 'none' && pseudoOpacity >= 0.8;
            const hasShadowPaint = pseudo.boxShadow !== 'none' && pseudoOpacity >= 0.8;
            if (!hasOpaquePaint && !hasImagePaint && !hasShadowPaint) return false;
            if (!['absolute', 'fixed'].includes(pseudo.position)) return false;
            if (Number.parseFloat(pseudo.zIndex) < 0) return false;
            const inset = [pseudo.top, pseudo.right, pseudo.bottom, pseudo.left].map(Number.parseFloat);
            const coversByInset = inset.every(value => Number.isFinite(value) && Math.abs(value) <= 2);
            const width = Number.parseFloat(pseudo.width);
            const height = Number.parseFloat(pseudo.height);
            const coversBySize = Number.isFinite(width) && Number.isFinite(height)
              && width >= rect.width - 4 && height >= rect.height - 4;
            return coversByInset || coversBySize;
          });
          const color = parseColor(style.color);
          const textFill = parseColor(style.webkitTextFillColor || style.color);
          const range = document.createRange();
          range.selectNodeContents(element);
          const textRectangles = [...range.getClientRects()].filter(value => value.width > 0.5 && value.height > 0.5);
          return {
            opacity,
            visible,
            width: rect.width,
            height: rect.height,
            hit: Boolean(hit && (hit === element || element.contains(hit))),
            text: element.innerText?.trim() || '',
            text_color_alpha: color.a,
            text_fill_alpha: textFill.a,
            pseudo_covers_content: pseudoCoversContent,
            font_size: Number.parseFloat(style.fontSize) || 0,
            text_rectangles: textRectangles.length,
          };
        }"""
    )
    if (
        not result["visible"]
        or result["opacity"] < 0.95
        or result["width"] < 28
        or result["height"] < 24
        or not result["hit"]
        or not result["text"]
        or result["text_color_alpha"] < 0.8
        or result["text_fill_alpha"] < 0.8
        or result["pseudo_covers_content"]
        or result["font_size"] < 10
        or result["text_rectangles"] < 1
    ):
        fail(f"{label} is not visibly actionable")


def assert_layouts(states: list[dict[str, object]]) -> None:
    by_label = {item["label"]: item for item in states}
    expected_headings = {"lamps": "Lamps", "freezer": "Freezer", "system": "System"}
    height_ranges = {"lamps": (90, 180), "freezer": (230, 360), "system": (330, 480)}
    for item in states:
        if item["order"] != ["lamps", "freezer", "system"] or item["count"] != 3:
            fail(f"{item['label']}: configured group order/count changed")
        if item["overlaps"]:
            fail(f"{item['label']}: groups overlap: {item['overlaps']}")
        if item["temperature_top_group"] != "freezer":
            fail(f"{item['label']}: Temperature is not hit-testable in Freezer")
        if item["document_overflow"]:
            fail(f"{item['label']}: page has horizontal overflow")
        root = item["root"]
        if root["height"] > 900 or item["document_height"] > 1000:
            fail(f"{item['label']}: layout exceeds the bounded responsive document height")
        for group_id, group in item["groups"].items():
            if (
                group["left"] < root["left"] - 1
                or group["right"] > root["right"] + 1
                or group["top"] < root["top"] - 1
                or group["bottom"] > root["bottom"] + 1
            ):
                fail(f"{item['label']}: {group_id} is outside the layout root")
            style = item["group_styles"][group_id]
            if style["display"] == "none" or style["visibility"] != "visible" or style["opacity"] < 0.95:
                fail(f"{item['label']}: {group_id} is not visibly rendered")
            minimum, maximum = height_ranges[group_id]
            if not minimum <= group["height"] <= maximum:
                fail(f"{item['label']}: {group_id} panel height no longer preserves responsive density")
            if not 320 <= group["width"] <= 380:
                fail(f"{item['label']}: {group_id} panel width no longer preserves responsive density")

            features = item["features"][group_id]
            heading = features["heading"]
            expected_id = f"{group_id}-heading"
            if (
                heading is None
                or heading["text"] != expected_headings[group_id]
                or heading["id"] != expected_id
                or features["labelled_by"] != expected_id
            ):
                fail(f"{item['label']}: {group_id} has no valid visible section heading")
            named_features = [
                ("heading", heading),
                *((f"content-{index}", feature) for index, feature in enumerate(features["contents"])),
                *((f"control-{index}", feature) for index, feature in enumerate(features["controls"])),
                *((f"label-{index}", feature) for index, feature in enumerate(features["labels"])),
            ]
            for feature_name, feature in named_features:
                if feature is None:
                    fail(f"{item['label']}: {group_id} is missing required {feature_name}")
                bounds = feature["rect"]
                if (
                    feature["hidden_by_display"]
                    or feature["hidden_by_visibility"]
                    or feature["render_suppressed"]
                    or feature["effective_opacity"] < 0.95
                    or bounds["width"] < 1
                    or bounds["height"] < 1
                    or not feature["text"]
                    or feature["text_color_alpha"] < 0.8
                    or feature["text_contrast"] < 3
                    or feature["text_fill_alpha"] < 0.8
                    or feature["text_fill_contrast"] < 3
                    or feature["pseudo_covers_content"]
                    or feature["font_size"] < 10
                    or feature["text_geometry"]["count"] < 1
                    or not feature["text_geometry"]["within_element"]
                ):
                    fail(
                        f"{item['label']}: {group_id} contains invisible required "
                        f"{feature_name}: {json.dumps(feature, sort_keys=True)}"
                    )
                if (
                    bounds["left"] < group["left"] - 1
                    or bounds["right"] > group["right"] + 1
                    or bounds["top"] < group["top"] - 1
                    or bounds["bottom"] > group["bottom"] + 1
                ):
                    fail(f"{item['label']}: {group_id} content escapes its owning panel")
                if feature["center_in_viewport"] and (
                    not feature["center_hit_matches"] or not feature["paint_hit_matches"]
                ):
                    fail(f"{item['label']}: {group_id} required {feature_name} is visually covered")

            expected_labels = {
                "lamps": ("lounge lamp:",),
                "freezer": ("mode:", "temperature", "°c target"),
                "system": ("grid voltage", "229 v", "voltage history"),
            }[group_id]
            observed_labels = tuple(feature["text"].casefold() for feature in features["labels"])
            if any(expected not in observed for expected, observed in zip(expected_labels, observed_labels)):
                fail(f"{item['label']}: {group_id} is missing required visible product labels")

        widths = [item["groups"][group_id]["width"] for group_id in ("lamps", "freezer", "system")]
        if max(widths) - min(widths) > 2:
            fail(f"{item['label']}: dashboard panels no longer have equal responsive widths")

    for label in ("wide_initial", "wide_return", "wide_repeat"):
        groups = by_label[label]["groups"]
        tops = [groups[group]["top"] for group in ("lamps", "freezer", "system")]
        if max(tops) - min(tops) > 1:
            fail(f"{label}: wide groups are not one row")
        if not (groups["lamps"]["left"] < groups["freezer"]["left"] < groups["system"]["left"]):
            fail(f"{label}: wide group order changed")

    for label in ("medium_first", "medium_repeat"):
        groups = by_label[label]["groups"]
        if abs(groups["system"]["left"] - groups["lamps"]["left"]) > 1:
            fail(f"{label}: System did not occupy the open first column")
        if groups["system"]["top"] < groups["lamps"]["bottom"] + 5:
            fail(f"{label}: System is not below Lamps with a gap")
        if groups["system"]["top"] > groups["lamps"]["bottom"] + 40:
            fail(f"{label}: System is separated from Lamps by an excessive gap")
        if abs(groups["freezer"]["top"] - groups["lamps"]["top"]) > 1:
            fail(f"{label}: first two medium groups do not share a row")

    for label in ("narrow_first", "narrow_repeat"):
        groups = by_label[label]["groups"]
        if not (
            groups["lamps"]["bottom"] < groups["freezer"]["top"]
            and groups["freezer"]["bottom"] < groups["system"]["top"]
        ):
            fail(f"{label}: narrow groups are not an ordered vertical stack")
        if (
            groups["freezer"]["top"] > groups["lamps"]["bottom"] + 40
            or groups["system"]["top"] > groups["freezer"]["bottom"] + 40
        ):
            fail(f"{label}: narrow stack has an excessive vertical gap")

    def assert_repeat_geometry(reference_label: str, repeated_labels: tuple[str, ...]) -> None:
        reference = by_label[reference_label]["groups"]
        for repeated_label in repeated_labels:
            repeated = by_label[repeated_label]["groups"]
            for group_id in ("lamps", "freezer", "system"):
                for field in ("left", "top", "width", "height"):
                    if abs(reference[group_id][field] - repeated[group_id][field]) > 2:
                        fail(f"{repeated_label}: {group_id} {field} drifted after resize history")

    assert_repeat_geometry("wide_initial", ("wide_return", "wide_repeat"))
    assert_repeat_geometry("medium_first", ("medium_repeat",))
    assert_repeat_geometry("narrow_first", ("narrow_repeat",))

    expected_controls = {
        "wide_initial": ("Lounge lamp: On", "Turn lounge lamp off", "Mode: Run", "-18°C target", "Acknowledge alert"),
        "medium_first": ("Lounge lamp: Off", "Turn lounge lamp on", "Mode: Run", "-18°C target", "Acknowledge alert"),
        "narrow_first": ("Lounge lamp: Off", "Turn lounge lamp on", "Mode: Run", "-18°C target", "Acknowledge alert"),
        "wide_return": ("Lounge lamp: Off", "Turn lounge lamp on", "Mode: Standby", "-17°C target", "Acknowledge alert"),
        "medium_repeat": ("Lounge lamp: On", "Turn lounge lamp off", "Mode: Run", "-17°C target", "Alert acknowledged"),
        "narrow_repeat": ("Lounge lamp: On", "Turn lounge lamp off", "Mode: Run", "-17°C target", "Alert acknowledged"),
        "wide_repeat": ("Lounge lamp: On", "Turn lounge lamp off", "Mode: Run", "-17°C target", "Alert acknowledged"),
    }
    for label, expected in expected_controls.items():
        controls = by_label[label]["controls"]
        observed = (
            controls["lamp"],
            controls["lamp_button"],
            controls["freezer"],
            controls["temperature"],
            controls["system"],
        )
        for expected_text, observed_text in zip(expected, observed):
            if expected_text not in (observed_text or ""):
                fail(f"{label}: control state {expected_text!r} was not preserved")


def verify() -> None:
    process = start_server_if_needed()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1180, "height": 760})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(URL, wait_until="networkidle")
            page.wait_for_function("document.querySelector('[aria-label=\"Operations groups\"]')?.dataset.layoutReady === 'true'")

            states = [state(page, "wide_initial")]
            if page.get_by_role("button", name="Turn lounge lamp off").count() != 1:
                fail("Lamps control is missing")
            lamp_off = page.get_by_role("button", name="Turn lounge lamp off")
            assert_actionable(lamp_off, "Lamps control")
            lamp_off.click()
            if page.get_by_role("button", name="Turn lounge lamp on").count() != 1:
                fail("Lamps control did not switch off")
            states.append(resize(page, 760, "medium_first"))
            states.append(resize(page, 420, "narrow_first"))
            before = page.get_by_test_id("temperature-target").inner_text()
            temperature = page.get_by_role("button", name="Raise target temperature")
            assert_actionable(temperature, "Temperature control")
            temperature.click()
            after = page.get_by_test_id("temperature-target").inner_text()
            if page.get_by_role("button", name="Pause").count() != 1:
                fail("Freezer mode control is missing")
            freezer_pause = page.get_by_role("button", name="Pause")
            assert_actionable(freezer_pause, "Freezer mode control")
            freezer_pause.click()
            if page.get_by_role("button", name="Resume").count() != 1:
                fail("Freezer mode control did not pause")
            states.append(resize(page, 1180, "wide_return"))
            acknowledge = page.get_by_role("button", name="Acknowledge alert")
            assert_actionable(acknowledge, "System control")
            acknowledge.click()
            if page.get_by_role("button", name="Alert acknowledged").count() != 1:
                fail("System control stopped working")
            lamp_on = page.get_by_role("button", name="Turn lounge lamp on")
            assert_actionable(lamp_on, "Lamps control")
            lamp_on.click()
            if page.get_by_role("button", name="Turn lounge lamp off").count() != 1:
                fail("Lamps control did not switch back on")
            freezer_resume = page.get_by_role("button", name="Resume")
            assert_actionable(freezer_resume, "Freezer mode control")
            freezer_resume.click()
            if page.get_by_role("button", name="Pause").count() != 1:
                fail("Freezer mode control did not resume")
            states.append(resize(page, 760, "medium_repeat"))
            states.append(resize(page, 420, "narrow_repeat"))
            states.append(resize(page, 1180, "wide_repeat"))

            assert_layouts(states)
            if before != "-18°C target" or after != "-17°C target":
                fail("Temperature control stopped working")
            if errors:
                fail(f"browser errors: {errors}")
            ARTIFACTS.mkdir(exist_ok=True)
            (ARTIFACTS / "layout-states.json").write_text(
                json.dumps(states, indent=2) + "\n",
                encoding="utf-8",
            )
            page.screenshot(path=str(ARTIFACTS / "verified-wide.png"), full_page=True)
            browser.close()
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    verify()
