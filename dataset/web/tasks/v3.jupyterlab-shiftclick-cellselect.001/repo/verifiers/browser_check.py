#!/usr/bin/env python3
# Behavioral verifier for the notebook Shift-click cell-selection task
# (jupyterlab/jupyterlab#19243).
#
# The decisive contract is which DOM regions of a rendered notebook are
# "browser-owned text regions" (a code cell's output area and a rendered
# markdown cell's rendered input, including outputs that attach an open shadow
# root) versus regions where a Shift-click must extend the CELL range selection
# (a code editor, a cell prompt, cell chrome). The notebook DOCUMENT - which
# cells exist and the concrete output DOM - is delivered only by the
# evaluator-owned scene feed (env/service.mjs) and is never present in
# agent-visible repo/ source.
#
# For each protected payload the verifier:
#   * starts the evaluator-owned scene feed and serves it via the product's
#     same-origin /scene proxy;
#   * loads the product, which renders the delivered notebook document;
#   * programmatically creates a text selection anchored in a specific region;
#   * dispatches a Shift + primary-button mousedown on a target cell region,
#     exactly as a Shift-click would;
#   * reads back the notebook's resulting cell selection state and asserts it
#     against the correct region-aware policy for that payload.
#
# No expected answer string is stored in agent-visible source. The broken build
# (which blocks cell selection whenever ANY text is selected) fails P1, and
# each partial repair fails at least one of P2/P3/P4.
from __future__ import annotations

import json
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

_PW_TMP = WORKSPACE / ".pw-tmp"
_PW_TMP.mkdir(exist_ok=True)
if os.environ.get("TMPDIR") != str(_PW_TMP):
    os.environ["TMPDIR"] = str(_PW_TMP)

from playwright.sync_api import sync_playwright  # noqa: E402

# Each payload: (doc key, selection spec, shift-click target spec, expected
# cell-range extension). "extend_cells" True means the Shift-click must turn
# into a multi-cell range selection; False means the browser must own the
# gesture as a text-selection extension and the cell selection must NOT grow.
PAYLOADS = [
    {
        "doc": "A",
        "name": "editor-selection-then-shift-click-prompt",
        # anchor a selection inside cell 0's code editor
        "select": {"cell": 0, "region": "editor"},
        # shift-click cell 2's prompt
        "click": {"cell": 2, "region": "prompt"},
        "expect_extend_cells": True,
    },
    {
        "doc": "B",
        "name": "output-selection-then-shift-click-output",
        "select": {"cell": 0, "region": "output", "sel": "#out-first"},
        "click": {"cell": 0, "region": "output", "sel": "#out-second"},
        "expect_extend_cells": False,
    },
    {
        "doc": "C",
        "name": "rendered-markdown-selection-then-shift-click-prompt",
        "select": {"cell": 0, "region": "markdown", "sel": "#md-first"},
        "click": {"cell": 0, "region": "markdown", "sel": "#md-second"},
        "expect_extend_cells": False,
    },
    {
        "doc": "D",
        "name": "shadow-output-selection-then-shift-click-output",
        "select": {"cell": 0, "region": "shadow", "sel": "#shadow-first"},
        "click": {"cell": 0, "region": "shadow", "sel": "#shadow-second"},
        "expect_extend_cells": False,
    },
    {
        "doc": "E",
        "name": "output-selection-then-shift-click-other-cell-prompt",
        # anchor a selection in cell 0's output, then shift-click cell 2's
        # prompt: the click lands on cell chrome, not a text region, so the
        # cell range selection must extend.
        "select": {"cell": 0, "region": "output", "sel": "#out-first"},
        "click": {"cell": 2, "region": "prompt"},
        "expect_extend_cells": True,
    },
]


def _launch(pw):
    return pw.chromium.launch(headless=True, args=["--no-sandbox"])


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


# Injected into the page. Anchors a text selection in a region, then dispatches
# a Shift + primary mousedown at a target region's center, then returns the
# notebook's cell selection state.
DRIVER_JS = r"""
({selectSpec, clickSpec}) => {
  const nb = window.__notebook;
  if (!nb) return {error: 'no notebook'};

  function regionRoot(cellIdx, region, sel) {
    const cell = nb.widgets[cellIdx];
    if (!cell) return null;
    if (region === 'editor') return cell.editor;
    if (region === 'prompt') return cell.node.querySelector('.jp-InputArea-prompt');
    if (region === 'markdown') {
      const md = cell.renderedInput;
      return sel ? md.querySelector(sel) : md;
    }
    if (region === 'output') {
      const out = cell.outputArea.querySelector('.jp-OutputArea-output');
      return sel ? out.querySelector(sel) : out;
    }
    if (region === 'shadow') {
      const host = cell.outputHost;
      const root = host.shadowRoot;
      return sel ? root.querySelector(sel) : root.firstElementChild;
    }
    return null;
  }

  // 1. Create a text selection anchored in the select region.
  const selEl = regionRoot(selectSpec.cell, selectSpec.region, selectSpec.sel);
  if (!selEl) return {error: 'no select element'};
  const textNode = (function firstText(node) {
    if (node.nodeType === 3 && (node.textContent || '').trim().length) return node;
    for (const c of node.childNodes) {
      const t = firstText(c);
      if (t) return t;
    }
    return null;
  })(selEl);
  if (!textNode) return {error: 'no text node in select region'};
  const range = document.createRange();
  range.setStart(textNode, 0);
  range.setEnd(textNode, Math.min(4, textNode.textContent.length));
  // Use the document-level selection via setBaseAndExtent so that a selection
  // anchored inside an open shadow root is faithfully represented at the
  // window.getSelection() level (addRange collapses such selections, but
  // setBaseAndExtent does not), matching a real user text selection.
  const selection = window.getSelection();
  selection.removeAllRanges();
  const end = Math.min(4, (textNode.textContent || '').length);
  selection.setBaseAndExtent(textNode, 0, textNode, end);

  // 2. Dispatch a Shift + primary mousedown at the click region.
  const clickEl = regionRoot(clickSpec.cell, clickSpec.region, clickSpec.sel)
    || regionRoot(clickSpec.cell, clickSpec.region);
  if (!clickEl) return {error: 'no click element'};
  const targetForEvent = (clickEl.nodeType === 3) ? clickEl.parentElement : clickEl;
  const rect = targetForEvent.getBoundingClientRect();
  const evt = new MouseEvent('mousedown', {
    bubbles: true,
    cancelable: true,
    composed: true,
    button: 0,
    shiftKey: true,
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2
  });
  targetForEvent.dispatchEvent(evt);

  // 3. Read back cell selection state.
  const st = nb.selectionState();
  const selectedCount = st.selected.filter(Boolean).length;
  return {
    selectedCount,
    selected: st.selected,
    active: st.active,
    defaultPrevented: evt.defaultPrevented
  };
}
"""


def _check(payload, result):
    errs = []
    if result.get("error"):
        return [f"[{payload['name']}] driver error: {result['error']}"]
    selected_count = result.get("selectedCount")
    expect_extend = payload["expect_extend_cells"]
    # A range extension across cells selects more than one cell. When the
    # browser owns the gesture the notebook must leave the cell selection at a
    # single (active) cell.
    if expect_extend:
        if not (isinstance(selected_count, int) and selected_count >= 2):
            errs.append(
                f"[{payload['name']}] expected cell range extension "
                f"(>=2 selected), got {selected_count}"
            )
    else:
        if not (isinstance(selected_count, int) and selected_count <= 1):
            errs.append(
                f"[{payload['name']}] expected browser-owned text selection "
                f"(<=1 cell selected), got {selected_count}"
            )
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
            for payload in PAYLOADS:
                page.goto(f"http://127.0.0.1:{app_port}/?doc={payload['doc']}",
                          wait_until="load")
                page.wait_for_function(
                    "window.__ready === true || window.__error", timeout=10000)
                err = page.evaluate("window.__error || null")
                if err:
                    all_errs.append(f"[{payload['name']}] app error: {err}")
                    continue
                result = page.evaluate(
                    DRIVER_JS,
                    {"selectSpec": payload["select"], "clickSpec": payload["click"]},
                )
                all_errs.extend(_check(payload, result))
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
    print("VERIFIER PASS: all four notebook payloads show correct region-aware "
          "Shift-click cell selection")
    return 0


if __name__ == "__main__":
    sys.exit(main())
