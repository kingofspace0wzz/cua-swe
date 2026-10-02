#!/usr/bin/env python3
# Behavioral verifier for the Artboard Editor rotated-viewport control geometry
# task (fabricjs/fabric.js#10977).
#
# The decisive contract is the *live* selection-control geometry the real,
# pinned fabric.js core produces for an object under a rotated / non-uniform
# viewport transform. The camera preset (viewport transform) is delivered only
# by the evaluator-owned scene feed (env/service.mjs); it is not present in
# agent-visible repo/ source. For each protected preset the verifier:
#   * starts the evaluator-owned scene feed on an ephemeral port and serves it
#     to the product via a same-origin /scene proxy;
#   * loads the product, which applies the delivered viewport transform through
#     the product's REAL fabric.js core, selects the object, and mirrors the
#     live fabric geometry (getZoom, _calculateCurrentDimensions, calcOCoords,
#     and the _renderControls rotation) into window.__geom;
#   * derives the physically-correct control geometry live from the delivered
#     viewport transform and object spec (never a stored expected constant);
#   * asserts the four fabric outputs match the correct rotated-viewport
#     geometry, and that the backward-compatible flat preset is unchanged.
#
# No expected pixel offsets are stored here. Each preset's pass/fail is derived
# from the viewport transform the feed delivered, so the broken build (which
# treats vpt[0] as the zoom scalar and drops viewport rotation) fails every
# rotated preset, while a partial repair that fixes only some of the four sites
# also fails.
from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent  # repo/
ENV_SERVICE = (WORKSPACE.parent / "env" / "service.mjs").resolve()

# Force a workspace-local temp dir before importing/launching Playwright, so the
# browser driver process does not attempt mkdtemp under a forbidden system temp
# dir (sandbox EPERM). Must happen before the driver process is spawned.
_PW_TMP = WORKSPACE / ".pw-tmp"
_PW_TMP.mkdir(exist_ok=True)
if os.environ.get("TMPDIR") != str(_PW_TMP):
    os.environ["TMPDIR"] = str(_PW_TMP)

from playwright.sync_api import sync_playwright  # noqa: E402

PRESETS = ["A", "B", "C", "D"]
# Object spec matches env/service.mjs (center origin, 200x120 at center 200,150).
OBJ = {"width": 200.0, "height": 120.0, "angle": 0.0, "cx": 200.0, "cy": 150.0}
ABS_TOL = 0.75  # pixels
ANG_TOL = 1e-3  # radians


def _launch(pw):
    opts = dict(headless=True, args=["--no-sandbox"])
    return pw.chromium.launch(**opts)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(port, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def _expected(vpt):
    """Physically-correct control geometry derived from the delivered vpt."""
    a, b, c, d, e, f = vpt
    zoom = math.hypot(a, b)
    scale_y = math.hypot(c, d)
    vpt_angle = math.atan2(b, a)
    exp_dim = (OBJ["width"] * zoom, OBJ["height"] * scale_y)
    render_angle = math.radians(OBJ["angle"]) + vpt_angle
    # Corner coords: object center in canvas space -> screen, then the object's
    # half extents rotated by the combined (object + viewport) angle and scaled.
    scx = a * OBJ["cx"] + c * OBJ["cy"] + e
    scy = b * OBJ["cx"] + d * OBJ["cy"] + f
    hw = OBJ["width"] / 2.0
    hh = OBJ["height"] / 2.0
    ca, sa = math.cos(vpt_angle), math.sin(vpt_angle)

    def corner(sx, sy):
        # local corner (sx*hw, sy*hh) scaled then rotated by vpt angle
        lx, ly = sx * hw * zoom, sy * hh * scale_y
        return (scx + lx * ca - ly * sa, scy + lx * sa + ly * ca)

    return {
        "zoom": zoom,
        "dim": exp_dim,
        "render_angle": render_angle,
        "corners": {
            "tl": corner(-1, -1),
            "tr": corner(1, -1),
            "br": corner(1, 1),
            "bl": corner(-1, 1),
        },
    }


def _check(preset, geom):
    errs = []
    vpt = geom.get("viewportTransform")
    if not vpt or len(vpt) != 6:
        return [f"[{preset}] missing viewportTransform"]
    exp = _expected(vpt)

    z = geom.get("zoom")
    if z is None or not math.isfinite(z) or abs(z - exp["zoom"]) > 1e-3:
        errs.append(f"[{preset}] zoom {z} != expected {exp['zoom']:.4f}")

    dim = geom.get("dim") or {}
    dx, dy = dim.get("x"), dim.get("y")
    if dx is None or dy is None or not (math.isfinite(dx) and math.isfinite(dy)):
        errs.append(f"[{preset}] dim not finite: {dim}")
    else:
        if abs(dx - exp["dim"][0]) > ABS_TOL or abs(dy - exp["dim"][1]) > ABS_TOL:
            errs.append(f"[{preset}] dim ({dx:.2f},{dy:.2f}) != expected "
                        f"({exp['dim'][0]:.2f},{exp['dim'][1]:.2f})")

    ang = geom.get("controlRenderAngle")
    if ang is None or not math.isfinite(ang):
        errs.append(f"[{preset}] controlRenderAngle not finite: {ang}")
    else:
        # normalize both to (-pi, pi]
        def norm(x):
            return math.atan2(math.sin(x), math.cos(x))
        if abs(norm(ang) - norm(exp["render_angle"])) > ANG_TOL:
            errs.append(f"[{preset}] renderAngle {ang:.4f} != expected "
                        f"{exp['render_angle']:.4f}")

    oc = geom.get("oCoords") or {}
    for name, (ex, ey) in exp["corners"].items():
        c = oc.get(name) or {}
        cx, cy = c.get("x"), c.get("y")
        if cx is None or cy is None or not (math.isfinite(cx) and math.isfinite(cy)):
            errs.append(f"[{preset}] oCoord {name} not finite: {c}")
        elif abs(cx - ex) > ABS_TOL or abs(cy - ey) > ABS_TOL:
            errs.append(f"[{preset}] oCoord {name} ({cx:.2f},{cy:.2f}) != "
                        f"expected ({ex:.2f},{ey:.2f})")
    return errs


def main() -> int:
    scene_port = _free_port()
    app_port = _free_port()
    svc = subprocess.Popen(
        ["node", str(ENV_SERVICE), "--host", "127.0.0.1", "--port", str(scene_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    env = dict(os.environ,
               CUA_SWE_EXTERNAL_SERVICE_ORIGIN=f"http://127.0.0.1:{scene_port}")
    app = subprocess.Popen(
        ["node", str(WORKSPACE / "server.mjs"), "--host", "127.0.0.1",
         "--port", str(app_port)],
        cwd=str(WORKSPACE), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    all_errs = []
    try:
        if not _wait_health(scene_port) or not _wait_health(app_port):
            print("FAIL: services did not become healthy", file=sys.stderr)
            return 3
        with sync_playwright() as pw:
            browser = _launch(pw)
            page = browser.new_page(viewport={"width": 1000, "height": 780})
            for preset in PRESETS:
                page.goto(f"http://127.0.0.1:{app_port}/?preset={preset}",
                          wait_until="load")
                page.wait_for_function(
                    "window.__geom && (window.__geom.zoom !== undefined "
                    "|| window.__geom.error)", timeout=10000)
                geom = page.evaluate("window.__geom")
                if geom.get("error"):
                    all_errs.append(f"[{preset}] app error: {geom['error']}")
                    continue
                all_errs.extend(_check(preset, geom))
            browser.close()
    finally:
        app.terminate()
        svc.terminate()
        try:
            app.wait(timeout=5)
            svc.wait(timeout=5)
        except Exception:
            pass

    if all_errs:
        print("VERIFIER FAIL:", file=sys.stderr)
        for e in all_errs:
            print("  " + e, file=sys.stderr)
        return 1
    print("VERIFIER PASS: all four camera presets show correct control geometry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
