#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import traceback
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Page, sync_playwright


CARD_ASSET = Path("img/panel_17.png")
CARD_ASSET_SHA256 = "285ecb89624163a8021e24b62110394141554edf3c6e8d3c14c9337f52466c69"
CARD_GEOMETRY = {"x": 20, "y": 68, "width": 320, "height": 176}
AGENT_TEXT_SUFFIXES = {
    "",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".svg",
    ".txt",
}
FORBIDDEN_CARD_LINE_HASHES = {
    "2767efa3d4db06aa1bd0019fbec262370f298b8b8dc568088e00481fce4f3d88",
    "bbd6e6866c813ba03235239e072887ec845dc4bdd991623edeb576f9a7abce7c",
    "9072f8c69aee769ea6845af24572fd146e6d88c1b6971c9f5335355f6b6fed7e",
    "0b6c5a0b8d11d2cc5ee50ec3a8d9608727e159d1b3b34e29cd90354dfa8ff0c7",
    "c9d5cba94a3c9fa96187719ebe6fbe9ac3491f1c038a99fa176be877553ed904",
    "b9185f268764e419139b2b380bf8d8cb588ba70a42c13cd5ec7844951d838517",
    "8573504bfd1da111ff9fa9f9b86ce5af7cb00923780b7932eacc6e23ba20ae24",
    "0b7c89c8955e0dca9b3e5050769a8dd56c663e2bbb740917690e97d2ed18f155",
    "532289f1f3bff255b8493ccd976f8e07ed7400d17603d5f23e052a1876c3d8eb",
    "4685ef3d4142afe8f1812bae1e49314e2c6c58147298c6439a6907d235edf1f6",
    "e0d4306b7dc52c554943fd860a3712dc6d53231003d332f4fc1f15bd83b81b23",
    "02ec5afd20b670bae75574d2d8ad85cc85ba1b467111e4dad75e3b25cea856e6",
    "5ae9c6facdc90db12aee61e1ab8a58c3bc1420416a0e6efa2fbbbde409b685bb",
    "b5f28d3b193ba7be51ee23fd5b88f28060b17d6795eab04e96dcb0413c7498f7",
    "33c83b2042a5e777083620b69e288515db5497cd5a32afcff2e34af594d6cf2e",
    "aad2b541e262ad48cd8a6a278d3dee1734de355b93b25e2db9884a536f23ed9e",
    "a72ce2b6eb644479daad86f9e39d90caccea760ed099c488a80b13aeb04779be",
    "12063551dc0733afe711376f014cbaf3a77b01e9b15fc676e205660bee46e82c",
    "205adfa23817b9e920a860bb5d502c907124c0993251fa1f24787ed3bf8951ab",
    "2486d09119ba8bde4120e10d351d4ca9cd170ce9a25a511b3c7490e002d636b9",
    "319a7a8dbdd05e225e8477960d692995499282215565022fee36a79bff20a92a",
    "3d7fed3416b2ea505c49feb56c45642e034cf56e742dad894b883034bd323dbe",
    "5595158628dbe140278d836109b53e67e7f97691f07ecf7d9e6b7e344e14b9b1",
    "5a346b4d79ce766765a664e7730c3b77a0a2cee4ff8efe7aef453e56876f11ee",
    "602d681c18d1d41c52a8271b0653447a07b9bc9300b9282e89a6b818bfcf192a",
    "6beb3bdcf8aab5858ddb322a534ab894e96a98968dd873f5954748fcc3203122",
    "75e4be8fb06a4db6db6e8dde900e00ae93c8f871d66963ef504513cb7fc395db",
    "9ae813772b4238d7675647e33540243e56738870964a8311495dcab665129f4c",
    "a2285c9235c3f3f01380bca97294d1a1855a8e3c8e72600cf647f24e9f75488c",
    "bb9d7266fb0c341e0e9ebad123ce93ecd3390d6d51bc1b1c30ff1570a898fc52",
    "c019c368d8eeb4af35192c1b9ad095239c8481bff89437a9c57638b5dc64035b",
    "c3ea2820591b71bc27faf379ac11108303be784868a425d2d5168946de530205",
    "c8e8caa4be106b474fc2fb68fd0218b16d9e3b7d88628367fc0f490b56324d67",
    "d30b952627bbbb5a9121805356304ef95a74722f9044d183a8e9cf7b30d157bd",
    "dce0252bc9fb8afe1aaf693cacc7e92ec9f9028ee55eb09da298364d60e72239",
    "dd591f32ab93155eecbf79248fe3aa6f8bacb4e7d5215af419e2aa092360d0f4",
    "f69be911c8dc35b0d667ed5c9563941e6af759e5c9ea14cba9425ed69f5eb2c6",
    "09d58b45331b6b0df0544c00307a669a39e38364b4ff6bebc75480b53c5d3cd7",
    "0fb85dcedc49df9ec282e43212c540134767f818dda92f18eba3f53807807408",
    "2184a1e918b53ffbe77788b38d9d0f6e79858469d28c7fd5d432ec8962c7ad1f",
    "3c7353db1f19bb923bf5fd362bc01b9f75565147ad81edc26b93de94df8fe674",
    "3dad8a59e97757582e389944d992e999e763357b0893d256c6cf4ee5fcf6c0c9",
    "49b54f12bd55c46e55e7fd03f2521e04dcd5c035c065c5fa6903058fe2abb73c",
    "4a5c7ab432a9f07ea70bbe8ce3c136f28997076e76fe1c28053fcf03e5292301",
    "503d505d2a24c7f5c2d886b35804314e438965c1e99175bb2d087796752d4d66",
    "52169bd8cc11e3cd49f72e6fa1d19fbb90cf1624103d57bdda19904b69ffdd7a",
    "5256324a627e7f9624d7d7a99b273d38cb31c126c5906bc9478bc2eb9bfcdd85",
    "556a1fae3cea7754d9385c09cb41e8440e366697112335e7b50e354ac2d06f9f",
    "6c0ebd4a12eccfc3d86ba9c2974bd3f3883acd3971d76476b4b86b4b2f33131e",
    "7b788e538868e3b90e10a60f11f453c0b721a6a19a40f1931a2d2ec1365d8efa",
    "783713d40718d7b916c712cd592fbe5b20ab31b63415d1feceaf49a50f8af2aa",
    "8e3ec8f307cfef8f9353a6148084ad425c940f4adb86ae1683eac5c4bb698294",
    "b77d7670f021f314670671c912298e87a702d6477e08dcea69d5d258ef085989",
    "d1910f744a56f1a468dc3ca0b64591db8758906acfd622814fcc6389010be7d6",
    "d54fcb27bf62a27d24733f2ccbb0847e27eed57796400b6252fc7d766d3ff1b1",
    "df5b32e08ba3eb22c3eb406cce6055733ad350fc6bb67ae147fb13126faac163",
    "dd15e54e9648b3107bdd82ef565e0ff236cf8aa40cd7384ae9c0ff653f2c246a",
    "e876438d66430e432a9ca8f166e77c2299b6e5d9f30ace3ea5281ef1ebbfbce7",
    "f450e02ff626042265d66c6c19d0d0d4058d79349bb4deaf619c9e2e147c77c9",
    "f88326204906c095adea1b2f40c5a0e2bad3d2758f4c2e14a0c0079cff1d8065",
    "f984850023683af8afa57e3844f51eae93549bc50c22d79b0f3fcdf59ac6b1be",
}


def game_state(page: Page) -> dict:
    return page.evaluate("window.gameAPI.getState()")


def verify_card_static_contract() -> dict:
    asset_digest = hashlib.sha256(CARD_ASSET.read_bytes()).hexdigest()
    if asset_digest != CARD_ASSET_SHA256:
        raise AssertionError(
            f"Level 50 card asset digest changed: expected {CARD_ASSET_SHA256}, "
            f"got {asset_digest}"
        )

    scanned: list[str] = []
    leaked: list[dict[str, str]] = []
    for path in sorted(Path(".").rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(Path("."))
        if ".git" in relative.parts or "verifiers" in relative.parts:
            continue
        if path.suffix.lower() not in AGENT_TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scanned.append(str(relative))
        normalized_lines = [
            " ".join(line.strip().lower().split())
            for line in text.splitlines()
            if line.strip()
        ]
        candidates = list(normalized_lines)
        candidates.extend(
            " ".join(normalized_lines[index : index + width])
            for width in (2, 3)
            for index in range(max(0, len(normalized_lines) - width + 1))
        )
        for candidate in candidates:
            digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
            if digest in FORBIDDEN_CARD_LINE_HASHES:
                leaked.append({"path": str(relative), "line_sha256": digest})
    if leaked:
        raise AssertionError(
            "player-facing card copy leaked into agent-visible plaintext: "
            + json.dumps(leaked, sort_keys=True)
        )

    manifest = json.loads(Path("assets.json").read_text(encoding="utf-8"))
    card_entries = [
        item
        for item in manifest.get("manifest", [])
        if item.get("id") == "panel 17" or item.get("src") == str(CARD_ASSET)
    ]
    if card_entries != [{"id": "panel 17", "src": str(CARD_ASSET)}]:
        raise AssertionError(
            "neutral card manifest entry changed: "
            + json.dumps(card_entries, sort_keys=True)
        )

    return {
        "asset_path": str(CARD_ASSET),
        "asset_sha256": asset_digest,
        "geometry": CARD_GEOMETRY,
        "agent_visible_plaintext_scanned": scanned,
        "forbidden_copy_hashes_found": leaked,
    }


def level_card_state(page: Page) -> dict:
    return page.evaluate(
        """
        () => {
          const game = window.Game;
          const card = game == null ? null : game.levelCard;
          return {
            exists: card != null,
            attached: card != null && card.parent === game.stage,
            x: card == null ? null : card.x,
            y: card == null ? null : card.y,
            width: card == null || card.image == null ? null : card.image.naturalWidth,
            height: card == null || card.image == null ? null : card.image.naturalHeight
          };
        }
        """
    )


def assert_level_card_absent(page: Page, label: str) -> dict:
    state = level_card_state(page)
    if state["attached"]:
        raise AssertionError(
            f"{label} unexpectedly rendered the Level 50 card: "
            + json.dumps(state, sort_keys=True)
        )
    return state


def verify_level_card_render(page: Page, label: str) -> dict:
    render = page.evaluate(
        """
        async () => {
          const game = window.Game;
          const card = game.levelCard;
          const canvas = document.getElementById("gameCanvas");
          if (card == null || card.image == null || canvas == null) {
            return {present: false};
          }
          const width = card.image.naturalWidth;
          const height = card.image.naturalHeight;
          const sourceCanvas = document.createElement("canvas");
          sourceCanvas.width = width;
          sourceCanvas.height = height;
          const sourceContext = sourceCanvas.getContext("2d", {willReadFrequently: true});
          sourceContext.drawImage(card.image, 0, 0);
          const source = sourceContext.getImageData(0, 0, width, height).data;
          const rendered = canvas.getContext("2d", {willReadFrequently: true})
            .getImageData(card.x, card.y, width, height).data;
          const sourceOpaque = [];
          const renderedOpaque = [];
          let opaquePixels = 0;
          let opaqueMismatches = 0;
          for (let index = 0; index < source.length; index += 4) {
            if (source[index + 3] !== 255) continue;
            opaquePixels += 1;
            for (let channel = 0; channel < 4; channel += 1) {
              sourceOpaque.push(source[index + channel]);
              renderedOpaque.push(rendered[index + channel]);
            }
            if (
              source[index] !== rendered[index] ||
              source[index + 1] !== rendered[index + 1] ||
              source[index + 2] !== rendered[index + 2] ||
              source[index + 3] !== rendered[index + 3]
            ) {
              opaqueMismatches += 1;
            }
          }
          const digest = async (values) => {
            const bytes = new Uint8Array(values);
            const hash = await crypto.subtle.digest("SHA-256", bytes);
            return Array.from(new Uint8Array(hash))
              .map((value) => value.toString(16).padStart(2, "0"))
              .join("");
          };
          const stageChildren = game.stage.children;
          const cardIndex = stageChildren.indexOf(card);
          return {
            present: true,
            attached: card.parent === game.stage,
            visible: card.visible,
            alpha: card.alpha,
            mouse_enabled: card.mouseEnabled,
            x: card.x,
            y: card.y,
            width: width,
            height: height,
            viewport: {width: window.innerWidth, height: window.innerHeight},
            canvas_internal: {width: canvas.width, height: canvas.height},
            canvas_screen: canvas.getBoundingClientRect().toJSON(),
            stage_order: {
              artboard: stageChildren.indexOf(game.artboard),
              card: cardIndex,
              interface: stageChildren.indexOf(game.interface),
              dialog: stageChildren.indexOf(game.dialog)
            },
            opaque_pixels_checked: opaquePixels,
            opaque_mismatches: opaqueMismatches,
            source_opaque_sha256: await digest(sourceOpaque),
            rendered_opaque_sha256: await digest(renderedOpaque)
          };
        }
        """
    )
    if not render.get("present"):
        raise AssertionError(f"{label} did not create the Level 50 card")
    expected = CARD_GEOMETRY
    for key in ("x", "y", "width", "height"):
        if render[key] != expected[key]:
            raise AssertionError(
                f"{label} card {key} changed: expected {expected[key]}, "
                f"got {render[key]}"
            )
    if render["viewport"] != {"width": 1280, "height": 720}:
        raise AssertionError(
            f"{label} viewport changed: " + json.dumps(render["viewport"], sort_keys=True)
        )
    if (
        not render["attached"]
        or not render["visible"]
        or render["alpha"] != 1
        or render["mouse_enabled"]
    ):
        raise AssertionError(
            f"{label} card display state is invalid: "
            + json.dumps(render, sort_keys=True)
        )
    order = render["stage_order"]
    if not (
        0 <= order["artboard"] < order["card"] < order["interface"] < order["dialog"]
    ):
        raise AssertionError(
            f"{label} card is not ordinary gameplay UI below native controls: "
            + json.dumps(order, sort_keys=True)
        )
    if (
        render["opaque_pixels_checked"] < 1000
        or render["opaque_mismatches"] != 0
        or render["source_opaque_sha256"] != render["rendered_opaque_sha256"]
    ):
        raise AssertionError(
            f"{label} card pixels were not rendered intact: "
            + json.dumps(render, sort_keys=True)
        )
    return render


def install_verifier_probe(page: Page) -> None:
    page.evaluate(
        """
        () => {
          const map = window.Game.levelMap;
          const original = map.captureGuide.bind(map);
          let saved = null;
          let boundary = null;
          const laterCaptures = [];

          const numberOrNull = (value) =>
            typeof value === "number" && Number.isFinite(value) ? value : null;
          const idOrNull = (value) => value == null ? null : String(value);
          const copyGuide = (frame) => frame == null ? null : {
            id: idOrNull(frame.id),
            x: numberOrNull(frame.x),
            y: numberOrNull(frame.y),
            tiles: numberOrNull(frame.tiles)
          };
          const detached = (value) => value == null
            ? null : JSON.parse(JSON.stringify(value));
          const deepFreeze = (value) => {
            if (value == null || typeof value !== "object" || Object.isFrozen(value)) {
              return value;
            }
            Object.freeze(value);
            Object.keys(value).forEach((key) => deepFreeze(value[key]));
            return value;
          };

          map.captureGuide = function (support) {
            const frame = original(support);
            const player = window.Game.player;
            const capture = {
              motion_time_ms: numberOrNull(this.motionTime),
              support_id: support == null ? null : idOrNull(support.id),
              support_top: support == null ? null : numberOrNull(support.top),
              frame_keys: frame == null ? [] : Object.keys(frame).sort(),
              guide: copyGuide(frame),
              guide_top: frame == null ? null : numberOrNull(frame.y + this.y),
              checkpoint_x: player == null ? null : numberOrNull(player.spawnX),
              checkpoint_spawn_y: player == null ? null : numberOrNull(player.spawnY),
              checkpoint_support_id:
                player == null ? null : idOrNull(player.spawnSupportId),
              rider_offset:
                player == null ? null : numberOrNull(player.spawnSupportOffset),
              rider_y:
                support == null || player == null
                  ? null
                  : numberOrNull(support.top + player.spawnSupportOffset),
              camera_course_x:
                player == null ? null : numberOrNull(player.spawnX),
              observed_camera_progress: numberOrNull(this.cameraProgress),
              observed_camera_offset_x: numberOrNull(this.x)
            };
            const qualifying =
              saved == null &&
              support != null &&
              frame != null &&
              support.checkpointCol >= 0 &&
              player != null &&
              idOrNull(player.spawnSupportId) === idOrNull(support.id);
            if (qualifying) {
              saved = deepFreeze(detached(capture));
            } else if (saved != null) {
              laterCaptures.push(detached(capture));
            }
            return frame;
          };

          window.addEventListener("boxel-restart", () => {
            const game = window.Game;
            const map = game.levelMap;
            const player = game.player;
            const guide = map.guideView;
            const savedSupport = saved == null
              ? null : map.getSupport(saved.support_id);
            const checkpointSupport = map.getSupport(player.spawnSupportId);
            boundary = {
              immutable_saved: detached(saved),
              later_capture_count: laterCaptures.length,
              later_captures: detached(laterCaptures),
              player_x: player.xPos,
              player_y: player.y,
              jump_ready: player.jumpReady,
              support_id: idOrNull(player.supportId),
              support_offset: numberOrNull(player.supportOffset),
              checkpoint_fields: {
                spawn_x: numberOrNull(player.spawnX),
                spawn_y: numberOrNull(player.spawnY),
                spawn_support_id: idOrNull(player.spawnSupportId),
                spawn_support_offset: numberOrNull(player.spawnSupportOffset),
                spawn_guide_keys:
                  player.spawnGuide == null
                    ? []
                    : Object.keys(player.spawnGuide).sort(),
                spawn_guide: copyGuide(player.spawnGuide)
              },
              saved_support: savedSupport == null ? null : {
                id: idOrNull(savedSupport.id),
                top: numberOrNull(savedSupport.top)
              },
              checkpoint_support: checkpointSupport == null ? null : {
                id: idOrNull(checkpointSupport.id),
                top: numberOrNull(checkpointSupport.top)
              },
              motion_time_ms: map.motionTime,
              camera_progress: map.cameraProgress,
              camera_offset_x: map.x,
              guide_present: guide != null && guide.parent != null,
              guide_top: guide == null ? null : guide.y + map.y,
              guide_x: guide == null ? null : guide.x + map.x,
              guide_alpha: guide == null ? null : guide.alpha,
              guide_remaining_ms: map.guideRemaining,
              level_card: {
                attached:
                  game.levelCard != null && game.levelCard.parent === game.stage,
                x: game.levelCard == null ? null : game.levelCard.x,
                y: game.levelCard == null ? null : game.levelCard.y,
                width:
                  game.levelCard == null || game.levelCard.image == null
                    ? null : game.levelCard.image.naturalWidth,
                height:
                  game.levelCard == null || game.levelCard.image == null
                    ? null : game.levelCard.image.naturalHeight
              }
            };
          }, {once: true});

          Object.defineProperty(window, "__boxelVerifier005", {
            configurable: false,
            enumerable: false,
            writable: false,
            value: () => detached({
              saved: saved,
              boundary: boundary,
              capture_attempts: laterCaptures
            })
          });
        }
        """
    )


def assert_close(actual: float | None, expected: float, tolerance: float, label: str) -> None:
    if actual is None or abs(actual - expected) > tolerance:
        raise AssertionError(
            f"{label}: expected {expected:.3f} +/- {tolerance:.3f}, got {actual}"
        )


def assert_guide_equal(actual: dict | None, expected: dict, label: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{label}: expected {json.dumps(expected, sort_keys=True)}, "
            f"got {json.dumps(actual, sort_keys=True)}"
        )


def app_url(url: str, query: str = "") -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", query, ""))


def verify_route_source_contract() -> dict:
    source_paths = [
        Path("js/Game.js"),
        Path("js/Home.js"),
        Path("game_api.js"),
        Path("index.html"),
    ]
    sources = {
        str(path): path.read_text(encoding="utf-8")
        for path in source_paths
    }
    combined = "\n".join(sources.values())
    forbidden_literals = [
        "gameqa.boxel-rebound-restart-camera-envelope",
        "benchmark_level",
        "benchmarkLevel",
        "evaluator_flag",
        "evaluatorFlag",
    ]
    leaked = [literal for literal in forbidden_literals if literal in combined]
    if leaked:
        raise AssertionError(f"benchmark-only startup branch leaked into source: {leaked}")

    query_keys: set[str] = set()
    for text in (sources["js/Game.js"], sources["game_api.js"]):
        query_keys.update(
            re.findall(r"\bparams\.get\(\s*['\"]([^'\"]+)['\"]", text)
        )
        query_keys.update(
            re.findall(
                r"URLSearchParams\([^;\n]*\)\.get\(\s*['\"]([^'\"]+)['\"]",
                text,
            )
        )
    if query_keys != {"level"}:
        raise AssertionError(
            f"startup query contract must contain only generic level, got {query_keys}"
        )
    if "window.Game.startLevel(this.selectedLevel);" not in sources["js/Home.js"]:
        raise AssertionError("selector play does not use the native Game.startLevel path")
    if "this.startLevel(this.requestedLevel)" not in sources["js/Game.js"]:
        raise AssertionError("deep-link startup does not use the native Game.startLevel path")

    return {
        "query_keys": sorted(query_keys),
        "shared_native_start_path": "Game.startLevel",
        "scanned_files": [str(path) for path in source_paths],
        "forbidden_literals_found": leaked,
    }


def verify_route_accessibility(page: Page, url: str, evidence_dir: Path) -> dict:
    source_contract = verify_route_source_contract()
    cases: dict[str, dict] = {}

    other_valid_levels: list[dict] = []
    for level in range(1, 50):
        page.goto(app_url(url, f"level={level}"), wait_until="load")
        page.wait_for_function(
            f"""
            () => window.Game && window.Game.ready === true &&
              window.Game.view === 2 &&
              window.Game.home.selectedLevel === {level}
            """,
            timeout=5000,
        )
        card_state = assert_level_card_absent(page, f"valid Level {level}")
        other_valid_levels.append(
            {
                "level": level,
                "view": page.evaluate("window.Game.view"),
                "card": card_state,
            }
        )
        if level == 2:
            page.wait_for_timeout(120)
            valid_state = game_state(page)
            if (
                valid_state["status"] != "playing"
                or valid_state["game_state"]["level"] != 2
                or not valid_state["is_actionable"]
            ):
                raise AssertionError(
                    "generic valid-level deep link did not enter native gameplay: "
                    + json.dumps(valid_state, sort_keys=True)
                )
            page.screenshot(path=str(evidence_dir / "route-valid-level-2.png"))
            cases["valid_level_2"] = {
                "url": app_url(url, "level=2"),
                "status": valid_state["status"],
                "level": valid_state["game_state"]["level"],
                "view": valid_state["debug"]["view"],
                "card": card_state,
            }
    cases["other_valid_levels"] = other_valid_levels

    selector_cases = {
        "absent": "",
        "invalid_text": "level=abc",
        "invalid_fraction": "level=2.5",
        "invalid_zero": "level=0",
        "invalid_negative": "level=-2",
        "invalid_unavailable": "level=51",
    }
    for name, query in selector_cases.items():
        page.goto(app_url(url, query), wait_until="load")
        page.wait_for_function(
            "window.Game && window.Game.ready === true",
            timeout=5000,
        )
        page.wait_for_timeout(120)
        state = game_state(page)
        if state["status"] != "menu" or state["debug"]["view"] != 1:
            raise AssertionError(
                f"{name} level route did not retain the selector: "
                + json.dumps(state, sort_keys=True)
            )
        card_state = assert_level_card_absent(page, f"{name} route")
        cases[name] = {
            "url": app_url(url, query),
            "status": state["status"],
            "view": state["debug"]["view"],
            "card": card_state,
        }
        if name == "absent":
            page.screenshot(path=str(evidence_dir / "route-selector-absent.png"))
        elif name == "invalid_unavailable":
            page.screenshot(path=str(evidence_dir / "route-selector-invalid.png"))

    return {
        "status": "pass",
        "source_contract": source_contract,
        "cases": cases,
    }


def replay(page: Page, url: str, evidence_dir: Path) -> dict:
    page.goto(url, wait_until="load")
    page.wait_for_function(
        """
        () => window.gameAPI && window.Game && window.Game.ready === true &&
          window.Game.view === 2 &&
          window.Game.home.selectedLevel === 50
        """,
        timeout=5000,
    )
    install_verifier_probe(page)
    page.wait_for_timeout(120)
    startup = game_state(page)
    if (
        startup["status"] != "playing"
        or startup["game_state"]["level"] != 50
        or not startup["is_actionable"]
        or startup["debug"]["view"] != 2
    ):
        raise AssertionError(
            "task URL did not land in native Level 50 gameplay: "
            + json.dumps(startup, sort_keys=True)
        )
    initial_card = verify_level_card_render(page, "initial Level 50")
    page.screenshot(path=str(evidence_dir / "00-initial-level-50-from-url.png"))

    page.wait_for_function(
        """
        () => {
          const game = window.Game;
          const player = game.player;
          const frame = player.spawnGuide;
          const support = game.levelMap.getSupport(player.spawnSupportId);
          const probe = window.__boxelVerifier005();
          return player.newSpawn === true &&
            probe.saved != null &&
            frame != null &&
            support != null &&
            player.supportId === player.spawnSupportId &&
            player.jumpReady === true;
        }
        """,
        timeout=5000,
    )
    checkpoint = game_state(page)
    checkpoint_probe = page.evaluate("window.__boxelVerifier005()")
    checkpoint_capture = checkpoint_probe["saved"]
    if checkpoint_capture["frame_keys"] != ["id", "tiles", "x", "y"]:
        raise AssertionError(
            "checkpoint guide snapshot was not geometry-only: "
            + json.dumps(checkpoint_capture, sort_keys=True)
        )

    page.wait_for_timeout(40)
    before_restart = game_state(page)
    pre_boundary = page.evaluate(
        """
        () => {
          const game = window.Game;
          const map = game.levelMap;
          const player = game.player;
          const frame = player.spawnGuide;
          const probe = window.__boxelVerifier005();
          const saved = probe.saved;
          const support = saved == null ? null : map.getSupport(saved.support_id);
          return {
            player_x: player.xPos,
            player_y: player.y,
            support_id: player.supportId == null ? null : String(player.supportId),
            checkpoint_support_id:
              player.spawnSupportId == null ? null : String(player.spawnSupportId),
            support_top: support == null ? null : support.top,
            immutable_saved_support_top:
              saved == null ? null : saved.support_top,
            live_saved_gap: support == null || saved == null
              ? null : support.top - saved.support_top,
            motion_time_ms: map.motionTime,
            immutable_saved_motion_time_ms:
              saved == null ? null : saved.motion_time_ms,
            guide_frame_keys: frame == null ? [] : Object.keys(frame).sort(),
            guide: frame == null ? null : {
              id: frame.id == null ? null : String(frame.id),
              x: frame.x,
              y: frame.y,
              tiles: frame.tiles
            },
            later_capture_count: probe.capture_attempts.length
          };
        }
        """
    )
    if pre_boundary["support_id"] != pre_boundary["checkpoint_support_id"]:
        raise AssertionError(
            "moving checkpoint ownership was lost before restart: "
            + json.dumps(pre_boundary, sort_keys=True)
        )
    if pre_boundary["guide_frame_keys"] != ["id", "tiles", "x", "y"]:
        raise AssertionError(
            "checkpoint guide acquired a clock-equivalent field: "
            + json.dumps(pre_boundary, sort_keys=True)
        )
    assert_guide_equal(
        pre_boundary["guide"],
        checkpoint_capture["guide"],
        "checkpoint guide changed before restart",
    )
    if pre_boundary["later_capture_count"] != 0:
        raise AssertionError(
            "checkpoint evidence was recaptured before restart: "
            + json.dumps(pre_boundary, sort_keys=True)
        )
    if pre_boundary["live_saved_gap"] is None or abs(pre_boundary["live_saved_gap"]) < 1:
        raise AssertionError(
            "restart was not triggered after visible lift displacement: "
            + json.dumps(pre_boundary, sort_keys=True)
        )
    page.screenshot(path=str(evidence_dir / "01-lift-displaced-before-restart.png"))

    page.keyboard.press("r")
    page.wait_for_function(
        "window.__boxelVerifier005().boundary !== null",
        timeout=2000,
    )
    boundary_probe = page.evaluate("window.__boxelVerifier005()")
    boundary = boundary_probe["boundary"]
    if boundary["level_card"] != {
        "attached": True,
        "x": CARD_GEOMETRY["x"],
        "y": CARD_GEOMETRY["y"],
        "width": CARD_GEOMETRY["width"],
        "height": CARD_GEOMETRY["height"],
    }:
        raise AssertionError(
            "Level 50 card was not preserved at the synchronous restart boundary: "
            + json.dumps(boundary["level_card"], sort_keys=True)
        )
    page.wait_for_timeout(100)
    after_restart = game_state(page)
    post_restart_card = verify_level_card_render(page, "post-restart Level 50")
    page.screenshot(path=str(evidence_dir / "02-restart-guide-comparison.png"))

    if (
        not boundary["guide_present"]
        or boundary["guide_alpha"] is None
        or boundary["guide_alpha"] <= 0
        or boundary["guide_remaining_ms"] < 3500
    ):
        raise AssertionError(
            "transient checkpoint guide was not visible after normal restart: "
            + json.dumps(boundary, sort_keys=True)
        )
    if boundary["checkpoint_fields"]["spawn_guide_keys"] != ["id", "tiles", "x", "y"]:
        raise AssertionError(
            "restart guide snapshot was not geometry-only: "
            + json.dumps(boundary, sort_keys=True)
        )
    if boundary["immutable_saved"] != checkpoint_capture:
        raise AssertionError(
            "evaluator-owned checkpoint snapshot changed across restart: "
            + json.dumps(boundary, sort_keys=True)
        )
    if boundary["later_capture_count"] != 0:
        raise AssertionError(
            "application rewrote saved checkpoint evidence by recapturing the "
            "moving support at its live frame: "
            + json.dumps(boundary["later_captures"], sort_keys=True)
        )
    assert_guide_equal(
        boundary["checkpoint_fields"]["spawn_guide"],
        checkpoint_capture["guide"],
        "application rewrote player.spawnGuide after checkpoint capture",
    )
    spawn_y = boundary["checkpoint_fields"]["spawn_y"]
    live_frame_rider_y = (
        None
        if boundary["saved_support"] is None
        else boundary["saved_support"]["top"] + checkpoint_capture["rider_offset"]
    )
    if (
        spawn_y is not None
        and live_frame_rider_y is not None
        and abs(spawn_y - checkpoint_capture["checkpoint_spawn_y"]) > 0.25
        and abs(spawn_y - live_frame_rider_y) <= 0.25
    ):
        raise AssertionError(
            "application rewrote player.spawnY to the moving support's live "
            "current frame: "
            + json.dumps(boundary, sort_keys=True)
        )
    assert_close(
        boundary["checkpoint_fields"]["spawn_support_offset"],
        checkpoint_capture["rider_offset"],
        0.25,
        "application rewrote checkpoint rider offset",
    )
    assert_close(
        boundary["checkpoint_fields"]["spawn_x"],
        checkpoint_capture["checkpoint_x"],
        0.25,
        "application rewrote checkpoint course coordinate",
    )
    if (
        boundary["checkpoint_fields"]["spawn_support_id"]
        != checkpoint_capture["support_id"]
    ):
        raise AssertionError(
            "application rewrote checkpoint support identity: "
            + json.dumps(boundary, sort_keys=True)
        )
    assert_close(
        boundary["guide_top"],
        checkpoint_capture["guide_top"],
        0.25,
        "checkpoint guide position",
    )
    assert_close(
        boundary["guide_x"],
        checkpoint_capture["guide"]["x"] - checkpoint_capture["camera_course_x"],
        0.25,
        "checkpoint guide course position",
    )
    if boundary["support_id"] != checkpoint_capture["support_id"]:
        raise AssertionError(
            "restart lost moving-support ownership: "
            + json.dumps(boundary, sort_keys=True)
        )
    if (
        boundary["saved_support"] is None
        or boundary["saved_support"]["id"] != checkpoint_capture["support_id"]
    ):
        raise AssertionError(
            "saved moving-support identity was not restored: "
            + json.dumps(boundary, sort_keys=True)
        )
    assert_close(
        boundary["saved_support"]["top"],
        checkpoint_capture["support_top"],
        1.0,
        "moving-support checkpoint position at restart",
    )
    assert_close(
        boundary["motion_time_ms"],
        checkpoint_capture["motion_time_ms"],
        1.0,
        "moving-support checkpoint clock at restart",
    )
    assert_close(
        boundary["player_y"],
        checkpoint_capture["support_top"] + checkpoint_capture["rider_offset"],
        1.0,
        "rider/support relationship at restart",
    )
    assert_close(
        boundary["support_offset"],
        checkpoint_capture["rider_offset"],
        0.25,
        "rider offset at restart",
    )
    assert_close(
        boundary["player_x"],
        checkpoint_capture["checkpoint_x"],
        0.25,
        "checkpoint course coordinate at restart",
    )
    assert_close(
        boundary["camera_progress"],
        checkpoint_capture["camera_course_x"],
        1.0,
        "camera/course frame at restart",
    )
    assert_close(
        boundary["camera_offset_x"],
        -boundary["camera_progress"],
        1.0,
        "camera transform at restart",
    )
    if not boundary["jump_ready"]:
        raise AssertionError(
            "ordinary restart did not preserve a grounded continuation: "
            + json.dumps(boundary, sort_keys=True)
        )

    restarted_player = after_restart["game_state"]["player"]
    restarted_support = after_restart["game_state"]["environment"]["moving_supports"][0]
    if (
        after_restart["debug"]["native_restart_count"] != 1
        or not restarted_player["jump_ready"]
        or restarted_player["props"]["support_id"] != restarted_support["id"]
    ):
        raise AssertionError(
            "rider/support relationship drifted immediately after restart: "
            + json.dumps(after_restart, sort_keys=True)
        )
    assert_close(
        restarted_player["y"],
        restarted_support["top"] + checkpoint_capture["rider_offset"],
        2.0,
        "rider/support relationship after restart",
    )
    if abs(
        after_restart["game_state"]["environment"]["camera_progress"]
        - restarted_player["x"]
    ) > 35:
        raise AssertionError(
            "course framing drifted after restart: "
            + json.dumps(after_restart, sort_keys=True)
        )

    page.wait_for_function(
        """
        () => {
          const player = window.gameAPI.getState().game_state.player;
          return player.x > 500 && player.props.support_id !== null;
        }
        """,
        timeout=5000,
    )
    ready_to_continue = game_state(page)
    page.screenshot(path=str(evidence_dir / "03-ready-to-continue.png"))
    ready_player = ready_to_continue["game_state"]["player"]

    page.keyboard.press("Space")
    page.wait_for_timeout(120)
    continued = game_state(page)
    page.screenshot(path=str(evidence_dir / "04-continuation-jump.png"))
    continued_player = continued["game_state"]["player"]
    if (
        continued_player["jump_ready"]
        or continued_player["props"]["support_id"] is not None
        or continued_player["y"] >= ready_player["y"] - 10
    ):
        raise AssertionError(
            "ordinary continuation jump did not launch normally: "
            + json.dumps(continued, sort_keys=True)
        )

    page.wait_for_function(
        "window.gameAPI.getState().terminal.isTerminal === true",
        timeout=6000,
    )
    final = game_state(page)
    page.screenshot(path=str(evidence_dir / "05-level-complete.png"))
    if (
        final["terminal"]["outcome"] != "success"
        or final["game_state"]["completion_progress"] != 1
        or final["game_state"]["player"]["state"] != "alive"
    ):
        raise AssertionError(f"level did not complete normally: {final}")

    return {
        "status": "pass",
        "card_static_contract": verify_card_static_contract(),
        "initial_card": initial_card,
        "startup": startup,
        "checkpoint": checkpoint,
        "checkpoint_capture": checkpoint_capture,
        "before_restart": before_restart,
        "pre_boundary": pre_boundary,
        "boundary_probe": boundary_probe,
        "restart_boundary": boundary,
        "after_restart": after_restart,
        "post_restart_card": post_restart_card,
        "ready_to_continue": ready_to_continue,
        "continued": continued,
        "final": final,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:51700/?level=50",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("verifier-artifacts"),
    )
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    evidence: dict
    card_static_contract: dict | None = None
    route_accessibility: dict | None = None
    exit_code = 0
    try:
        card_static_contract = verify_card_static_contract()
        with sync_playwright() as playwright:
            launch_options = {"headless": True}
            executable = os.environ.get("CUA_SWE_CHROMIUM_EXECUTABLE")
            if executable:
                launch_options["executable_path"] = executable
            browser = playwright.chromium.launch(**launch_options)
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            route_page = context.new_page()
            page = context.new_page()
            try:
                route_accessibility = verify_route_accessibility(
                    route_page,
                    args.url,
                    args.evidence_dir,
                )
                evidence = replay(page, args.url, args.evidence_dir)
                evidence["card_static_contract"] = card_static_contract
                evidence["route_accessibility"] = route_accessibility
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        exit_code = 1
        evidence = {
            "status": "fail",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "card_static_contract": card_static_contract,
            "route_accessibility": route_accessibility,
        }

    (args.evidence_dir / "state-replay.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "evidence": str(args.evidence_dir / "state-replay.json"),
                "error": evidence.get("error"),
            },
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
