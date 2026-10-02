# Astray deterministic Level 2 parallax-glass replay

## Agent-visible reproduction

1. Select Level 2 and do nothing. The gold ball remains stationary below three
   opaque magenta seals and a red crossbar.
2. Press and hold the ordinary Up arrow. The ball travels through the gallery.
3. Each passed seal should be replaced by a green glass core and a separate
   amber crown while the seals farther ahead remain magenta.
4. After the third transition, three green-and-amber signatures remain visible
   and the crossbar is green. Continuing with ordinary movement carries the
   ball beyond it.

The broken snapshot advances the gallery state and player, but its overlapping
transparent panes disagree about depth-buffer ownership and presentation
order. The resulting pixels show near-layer colors instead of the intended
two-part glass signatures.

## Behavioral oracle

The protected replay selects Level 3, holds an arrow across in-place Level 2
selection, releases it, and proves held-input neutralization with a true no-input
interval. It retains an opening screenshot containing the stationary
gold ball, three magenta seals, and the red crossbar.

The replay then holds ordinary Up and records public `window.gameAPI` player
samples over time. It retains a mixed screenshot with one resolved green core,
one amber crown, at least one remaining magenta seal, and the red bar. It then
retains a completion screenshot containing at least three green cores, three
amber crowns, the green bar, and no magenta, red, or reverse-composited teal
mechanism pixels. Public player history must independently show substantial
forward travel, and ordinary Up must continue moving the ball beyond the
completed gallery.

Screenshots are retained evidence, not a clock or a source of private state.
Assertions use only rendered color components and public player
position/velocity. The complete sequence repeats after ordinary `R`, producing
six exact PNG files and one JSON evidence record.

## Why the negatives fail

- The depth-only patch allows overlapping panes to contribute without writing
  over one another's depth, so green cores appear. It leaves the crown painter
  order reversed, producing teal crowns instead of amber.
- The order-only patch presents the crown layers back-to-front, so amber crowns
  appear. It leaves the near core layer owning depth, so the farther layer
  cannot contribute and the cores remain red rather than green.

## Certification status

Construction is source-only and launches no browser or server. Runtime static
verification is intentionally implementation-independent: it checks syntax,
self-containment, frozen dependencies, launch shape, and the public gameAPI,
but no broken literal, gold literal, function name, formula, or mechanism
source shape. Protected certification must still establish no-op failure, two
complete gold runs, both negative failures, true idle, held-input
neutralization, ordinary restart, and retained PNG/JSON evidence.
