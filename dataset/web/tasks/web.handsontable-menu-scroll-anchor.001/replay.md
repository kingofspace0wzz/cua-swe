# Handsontable menu scroll-anchor replay

Open `/runtime-task/index.html` in Chromium. The fixture renders a Handsontable
grid inside a separately scrollable panel and exposes both a column dropdown
and a cell context menu.

Exercise the behavior by opening a menu and then scrolling either the outer
panel or the grid viewport while the menu remains open. The menu must preserve
its measured offset from the header, cell, or parent submenu item that opened
it. If virtual rendering removes that anchor, the menu must close instead of
remaining stranded on screen.

The protected browser verifier checks several distinct runtime cases:

- an outer-panel scroll moves an open dropdown by the same vertical delta;
- grid scrolling keeps a context menu attached to its cell;
- horizontal grid scrolling moves the menu with its anchor;
- scrolling an anchor out of the rendered viewport closes the menu;
- custom UI containers, internal menu scroll, sticky headers, keyboard-opened
  menus, page scroll, and submenu hover behavior remain intact.

Observed reference behavior:

- Broken baseline: the outer panel moves 100 px while the dropdown moves 0 px;
  the measured anchor offset is wrong by 100 px, and a derendered anchor leaves
  the menu visible.
- Historical gold repair: the menu moves 100 px with the outer panel, about
  59 px with horizontal grid scroll, preserves a 0 px anchor-offset error, and
  closes after anchor derender.
- Matched CUA agent: used Chromium through the browser tool and passed the
  hidden verifier.
- Matched code-only agent: did not use a browser and failed the hidden verifier.

The verifier is behavioral and runs in real Chromium. It does not require a
particular source shape.
