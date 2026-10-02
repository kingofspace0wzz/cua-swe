# Replay (v3.slate-softbreak-scroll.002 -- lower-neighbor calibration)

Open Field Log Composer. The active workspace frame is shown in the product
chrome. The caret begins near the bottom of the current entry. Press
Shift+Enter to continue the same entry on a new line.

The broken build leaves the new caret line below the safe writing region. The
correct repair moves the body only far enough to keep that line visible while
retaining the preceding context. A snap-to-band repair keeps the caret visible
but scrolls substantially farther and loses too much preceding context.

The status strip carries a live cursor-visibility flag. In the broken build it
flips from "Cursor in view" to "Cursor below fold" the moment Shift+Enter is
pressed, so the off-screen writing spot is visible in a single screenshot; a
correct repair keeps it reading "Cursor in view". The flag is derived from the
running layout and reports only the observed in-view / below-fold state -- it
carries no target scroll amount and does not reveal the repair.

The protected verifier repeats this interaction in three workspace frames with
different body heights, safe margins, and text scales. Because each frame uses
a different text scale, one continued line is a different height on each frame,
so the minimal reveal differs per frame and no single fixed scroll amount can
pass all three. The verifier checks the live caret box, scroll delta, and
preceding-line displacement; it does not compare a fixed offset.
