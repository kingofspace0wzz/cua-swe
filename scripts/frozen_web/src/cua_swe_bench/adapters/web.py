from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cua_swe_bench.adapters.base import MAX_DRAG_STEPS, GuiAction, GuiObservation


MAX_VIEWPORT_WIDTH = 3_840
MAX_VIEWPORT_HEIGHT = 2_160

CHROMIUM_NETWORK_HARDENING_ARGS = [
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-features=MediaRouter,OptimizationHints,Translate",
    "--disable-sync",
    "--disable-quic",
    "--dns-prefetch-disable",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    "--metrics-recording-only",
    "--no-first-run",
    "--safebrowsing-disable-auto-update",
]


class WebFrontendAdapter:
    def __init__(
        self,
        start_url: str,
        artifacts_dir: Path,
        page: Any | None = None,
        viewport: dict[str, int] | None = None,
    ) -> None:
        self.start_url = start_url
        self.artifacts_dir = Path(artifacts_dir)
        self.page = page
        self.viewport = viewport or {"width": 1280, "height": 720}
        self._validate_viewport(self.viewport)
        self._playwright = None
        self._browser = None
        self._context = None
        self._screenshot_index = 0
        self._drag_active = False

    def start(self, workspace: Path) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            if self.page is None:
                from playwright.sync_api import sync_playwright

                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    headless=True,
                    args=CHROMIUM_NETWORK_HARDENING_ARGS,
                )
                self._context = self._browser.new_context(
                    viewport=self.viewport,
                    service_workers="block",
                )
                self._context.route("**/*", self._route_request)
                route_web_socket = getattr(self._context, "route_web_socket", None)
                if not callable(route_web_socket):
                    raise RuntimeError(
                        "Playwright runtime lacks required WebSocket routing enforcement"
                    )
                route_web_socket("**/*", self._route_web_socket)
                self.page = self._context.new_page()
            self.page.goto(self.start_url)
        except Exception:
            self.stop()
            raise

    def observe(self) -> GuiObservation:
        if self.page is None:
            raise RuntimeError("web adapter has not been started")
        self._screenshot_index += 1
        screenshot_path = self.artifacts_dir / f"screenshot-{self._screenshot_index:04d}.png"
        self.page.screenshot(path=str(screenshot_path))
        text = self.page.locator("body").inner_text()
        return GuiObservation(
            url=self.page.url,
            screenshot_path=str(screenshot_path),
            text=text,
            metadata={
                "adapter": "playwright_web",
                "viewport": self._viewport_metadata(),
                "document": self._document_metadata(),
                "drag_active": self._drag_active,
                "elements": self._interactive_elements(),
            },
        )

    def act(self, action: GuiAction) -> GuiObservation:
        if self.page is None:
            raise RuntimeError("web adapter has not been started")
        try:
            self._assert_drag_sequence(action)
            if action.kind == "click":
                self._validate_point(action.x, action.y, "click")
                if action.modifiers:
                    self._click_with_modifiers(action.x, action.y, action.modifiers)
                else:
                    self.page.mouse.click(action.x, action.y)
            elif action.kind == "type":
                self.page.keyboard.type(action.text)
            elif action.kind == "press":
                key = action.text.lower().replace("ctrl+", "control+")
                if key in {
                    "f5", "control+r", "control+shift+r",
                    "meta+r", "meta+shift+r",
                }:
                    # Headless Chromium does not implement browser-toolbar
                    # shortcuts through keyboard events. Perform the browser
                    # action explicitly so edits become visible on refresh.
                    self.page.reload(wait_until="domcontentloaded")
                else:
                    self.page.keyboard.press(action.text)
            elif action.kind == "key_hold":
                self._hold_keys(action.text, action.duration_ms)
            elif action.kind == "scroll":
                self._validate_point(action.x, action.y, "scroll")
                self.page.mouse.move(action.x, action.y)
                self.page.mouse.wheel(action.delta_x or 0, action.delta_y or 0)
                self.page.wait_for_timeout(100)
            elif action.kind == "drag":
                self._validate_point(action.x, action.y, "drag start")
                self._validate_point(action.end_x, action.end_y, "drag end")
                steps = action.steps if action.steps is not None else 10
                self.page.mouse.move(action.x, action.y)
                self.page.mouse.down()
                try:
                    self.page.mouse.move(action.end_x, action.end_y, steps=steps)
                finally:
                    self.page.mouse.up()
                self.page.wait_for_timeout(100)
            elif action.kind == "drag_start":
                self._validate_point(action.x, action.y, "drag_start")
                self.page.mouse.move(action.x, action.y)
                self._drag_active = True
                self.page.mouse.down()
            elif action.kind == "drag_move":
                self._validate_point(action.x, action.y, "drag_move")
                steps = action.steps if action.steps is not None else 10
                self.page.mouse.move(action.x, action.y, steps=steps)
            elif action.kind == "drag_end":
                try:
                    if action.x is not None:
                        self._validate_point(action.x, action.y, "drag_end")
                        steps = action.steps if action.steps is not None else 10
                        self.page.mouse.move(action.x, action.y, steps=steps)
                finally:
                    self._release_drag()
                self.page.wait_for_timeout(100)
            elif action.kind == "back":
                self.page.go_back()
            elif action.kind == "forward":
                self.page.go_forward()
            elif action.kind == "resize":
                assert action.width is not None and action.height is not None
                viewport = {"width": action.width, "height": action.height}
                self._validate_viewport(viewport)
                self.page.set_viewport_size(viewport)
                self.viewport = viewport
                self.page.wait_for_timeout(100)
            elif action.kind == "wait":
                self.page.wait_for_timeout(action.duration_ms or 250)
            return self.observe()
        except Exception:
            self._release_drag_safely()
            raise

    def stop(self) -> None:
        self._release_drag_safely()
        context = self._context
        browser = self._browser
        playwright = self._playwright
        self._context = None
        self._browser = None
        self._playwright = None
        self.page = None
        if context is not None:
            context.close()
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()

    def cancel_active_drag(self) -> bool:
        """Release an in-progress staged drag after protocol or transport failure."""
        was_active = self._drag_active
        self._release_drag_safely()
        return was_active

    def _assert_drag_sequence(self, action: GuiAction) -> None:
        if self._drag_active and action.kind not in {"drag_move", "drag_end"}:
            raise ValueError("an active staged drag must be moved or ended before another action")
        if not self._drag_active and action.kind in {"drag_move", "drag_end"}:
            raise ValueError(f"{action.kind} action requires an active staged drag")

    def _release_drag(self) -> None:
        if not self._drag_active:
            return
        try:
            if self.page is not None:
                self.page.mouse.up()
        finally:
            self._drag_active = False

    def _release_drag_safely(self) -> None:
        try:
            self._release_drag()
        except Exception:
            self._drag_active = False

    def _click_with_modifiers(self, x: int, y: int, modifiers: list[str]) -> None:
        """Keep modifiers within this coordinate click, including on failure."""
        attempted: list[str] = []
        primary_error: BaseException | None = None
        try:
            for key in modifiers:
                # A transport error may arrive after keydown took effect.
                attempted.append(key)
                self.page.keyboard.down(key)
            self.page.mouse.click(x, y)
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            release_errors: list[BaseException] = []
            for key in reversed(attempted):
                try:
                    self.page.keyboard.up(key)
                except BaseException as exc:
                    # Still attempt every other release if one fails.
                    release_errors.append(exc)
            if release_errors:
                error = primary_error if primary_error is not None else release_errors[0]
                for release_error in release_errors:
                    if release_error is not error:
                        error.add_note(f"Modifier release also failed: {release_error}")
                if primary_error is None:
                    raise error

    def _hold_keys(self, text: str | None, duration_ms: int | None) -> None:
        if self.page is None:
            raise RuntimeError("web adapter has not been started")
        keys = [key.strip() for key in (text or "").split("+") if key.strip()]
        pressed: list[str] = []
        try:
            for key in keys:
                self.page.keyboard.down(key)
                pressed.append(key)
            self.page.wait_for_timeout(duration_ms or 400)
        finally:
            for key in reversed(pressed):
                self.page.keyboard.up(key)

    def _interactive_elements(self) -> list[dict[str, object]]:
        if self.page is None:
            return []
        try:
            return self.page.locator("button, [role=button], a[href], input, textarea, select").evaluate_all(
                """
                (nodes) => nodes
                  .filter((node) => {
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return rect.width > 0
                      && rect.height > 0
                      && style.visibility !== "hidden"
                      && style.display !== "none";
                  })
                  .map((node, index) => {
                    const rect = node.getBoundingClientRect();
                    const label = node.innerText
                      || node.getAttribute("aria-label")
                      || node.getAttribute("title")
                      || Array.from(node.labels || []).map((item) => item.innerText).join(" ")
                      || node.getAttribute("placeholder")
                      || node.value
                      || "";
                    return {
                      index,
                      tag: node.tagName.toLowerCase(),
                      text: label.trim(),
                      role: node.getAttribute("role"),
                      aria_label: node.getAttribute("aria-label"),
                      id: node.getAttribute("id"),
                      aria_controls: node.getAttribute("aria-controls"),
                      title: node.getAttribute("title"),
                      test_id: node.getAttribute("data-testid"),
                      data_tag: node.getAttribute("data-tag"),
                      checked: typeof node.checked === "boolean" ? node.checked : null,
                      x: Math.round(rect.x),
                      y: Math.round(rect.y),
                      width: Math.round(rect.width),
                      height: Math.round(rect.height),
                      center_x: Math.round(rect.x + rect.width / 2),
                      center_y: Math.round(rect.y + rect.height / 2)
                    };
                  })
                """
            )
        except Exception:
            return []

    def _viewport_metadata(self) -> dict[str, int] | None:
        if self.page is None:
            return None
        page_viewport = getattr(self.page, "viewport_size", None)
        if page_viewport is not None:
            return page_viewport
        return self.viewport

    def _document_metadata(self) -> dict[str, object] | None:
        if self.page is None:
            return None
        try:
            return self.page.evaluate(
                """
                () => ({
                  time_origin: performance.timeOrigin,
                  navigation_type: performance.getEntriesByType('navigation')[0]?.type || null,
                  navigation_entries: performance.getEntriesByType('navigation').length
                })
                """
            )
        except Exception:
            return None

    @staticmethod
    def _effective_port(parts: Any) -> int | None:
        if parts.port is not None:
            return parts.port
        return {"http": 80, "https": 443, "ws": 80, "wss": 443}.get(parts.scheme)

    def _url_is_allowed(self, value: str) -> bool:
        candidate = urlsplit(value)
        if candidate.scheme in {"about", "blob", "data"}:
            return True
        expected = urlsplit(self.start_url)
        candidate_scheme = {"ws": "http", "wss": "https"}.get(
            candidate.scheme,
            candidate.scheme,
        )
        return (
            candidate_scheme == expected.scheme
            and candidate.hostname == expected.hostname
            and self._effective_port(candidate) == self._effective_port(expected)
        )

    def _route_request(self, route: Any) -> None:
        if self._url_is_allowed(str(route.request.url)):
            route.continue_()
        else:
            route.abort("blockedbyclient")

    def _route_web_socket(self, route: Any) -> None:
        if self._url_is_allowed(str(route.url)):
            route.connect_to_server()
        else:
            route.close(code=1008, reason="cross-origin websocket blocked")

    def _validate_point(self, x: int | None, y: int | None, label: str) -> None:
        if x is None or y is None:
            raise ValueError(f"{label} requires x and y")
        viewport = self._viewport_metadata() or self.viewport
        width = viewport["width"]
        height = viewport["height"]
        if x < 0 or x >= width or y < 0 or y >= height:
            raise ValueError(f"{label} coordinates must be inside the {width}x{height} viewport")

    @staticmethod
    def _validate_viewport(viewport: dict[str, int]) -> None:
        width = viewport.get("width")
        height = viewport.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise ValueError("viewport width and height must be positive integers")
        if width > MAX_VIEWPORT_WIDTH or height > MAX_VIEWPORT_HEIGHT:
            raise ValueError(
                f"viewport must not exceed {MAX_VIEWPORT_WIDTH}x{MAX_VIEWPORT_HEIGHT}"
            )
