#!/usr/bin/env python3
"""Deterministic behavioral verifier for the appointment date field.

Launches the product app, drives the four protected interaction scenarios in a
real headless browser, and checks the observable outcomes (input value and the
selected-date readout AFTER blur) against the evaluator-owned contract in
env/contract.json. Exit 0 iff every protected payload passes.

The verifier is behavior-based: it never inspects source, never matches a patch,
and never references the repair mechanism -- only the required observable state.
"""
import json, os, sys, time, socket, subprocess, pathlib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
ENV_DIR = REPO.parent / "env"
CONTRACT = pathlib.Path(os.environ.get(
    "CUA_SWE_CONTRACT",
    str(REPO.parent / "env" / "contract.json")))

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def wait_http(port, path="/health", timeout=25):
    import urllib.request
    dl = time.time() + timeout
    while time.time() < dl:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False

def clear_and_type(pg, inp, text):
    # Emulate "select all + delete": reliably empties the controlled field
    # (which the product mask runtime then surfaces as its placeholder
    # pattern via an async /mask fetch). Wait for that controlled-state update
    # before typing so a late mask response cannot overwrite the next value.
    inp.click()
    before = inp.input_value()
    inp.fill("")
    pg.wait_for_function(
        """({selector, before}) => {
          const input = document.querySelector(selector);
          return input && input.value !== "" && input.value !== before;
        }""",
        arg={"selector": "#appointment-date", "before": before},
        timeout=3000,
    )
    if text:
        inp.fill(text)
        pg.wait_for_timeout(150)
        assert inp.input_value() == text, f"typed value did not stabilize: {text!r}"

def run():
    contract = json.loads(CONTRACT.read_text())
    sp = free_port()
    ap = free_port()
    svc = subprocess.Popen(
        ["node", str(ENV_DIR / "service.mjs"), "--host", "127.0.0.1", "--port", str(sp)])
    app_env = dict(os.environ, CUA_SWE_EXTERNAL_SERVICE_ORIGIN=f"http://127.0.0.1:{sp}")
    app = subprocess.Popen(
        ["node", "server.mjs", "--host", "127.0.0.1", "--port", str(ap)],
        cwd=str(REPO), env=app_env)
    results = []
    try:
        assert wait_http(sp), "mask service did not come up"
        assert wait_http(ap), "app did not come up"
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            for sc in contract["scenarios"]:
                pg = b.new_page(viewport={"width": 640, "height": 480})
                scene = sc.get("scene", "")
                q = f"?scene={scene}" if scene else ""
                pg.goto(f"http://127.0.0.1:{ap}/{q}")
                pg.wait_for_selector("#appointment-date")
                inp = pg.query_selector("#appointment-date")
                # sanity: initial readout
                init = pg.eval_on_selector("#selected-readout", "e => e.textContent")
                assert init == contract["initial_selected_readout"], \
                    f"bad initial readout {init!r}"
                clear_and_type(pg, inp, sc["typed_after_clear"])
                # blur
                pg.eval_on_selector("h1", "e => e.tabIndex = 0")
                pg.click("h1")
                time.sleep(0.2)
                val = inp.input_value()
                readout = pg.eval_on_selector("#selected-readout", "e => e.textContent")
                ok = True
                reasons = []
                if "expect_input_value_after_blur" in sc:
                    if val != sc["expect_input_value_after_blur"]:
                        ok = False; reasons.append(
                            f"input={val!r} expected={sc['expect_input_value_after_blur']!r}")
                if "expect_input_value_after_blur_not" in sc:
                    if val == sc["expect_input_value_after_blur_not"]:
                        ok = False; reasons.append(
                            f"input={val!r} must NOT equal {sc['expect_input_value_after_blur_not']!r}")
                if "expect_selected_readout_after_blur" in sc:
                    if readout != sc["expect_selected_readout_after_blur"]:
                        ok = False; reasons.append(
                            f"readout={readout!r} expected={sc['expect_selected_readout_after_blur']!r}")
                results.append((sc["id"], ok, reasons, val, readout))
                pg.close()
            b.close()
    finally:
        app.terminate()
        try:
            app.wait(timeout=5)
        except Exception:
            app.kill()
        svc.terminate()
        try:
            svc.wait(timeout=5)
        except Exception:
            svc.kill()
    return results

def main():
    results = run()
    passed = 0
    for sid, ok, reasons, val, readout in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {sid}: input={val!r} readout={readout!r}"
              + (f"  -> {'; '.join(reasons)}" if reasons else ""))
        passed += 1 if ok else 0
    total = len(results)
    print(f"\n{passed}/{total} protected payloads passed")
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
