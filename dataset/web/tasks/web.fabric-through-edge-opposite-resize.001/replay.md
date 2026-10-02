# Opposite-side variant of admitted through-edge revision03

Use Camera B and Nested through the visible selectors. In Blue's initial axes:

1. Grab the left midpoint (-30,0), off-center by three screen pixels along its
   projected axis. Carry it to (66,0), with the opposite midpoint (30,0) fixed.
2. Release. Grab the visible corner at (66,-18), carry it to (78,48), with
   opposite corner (30,18) fixed. Both dimensions cross independently.
3. Release. Ordinary visible-fill acquisition and drag translate the resulting
   rectangle by (-3,-2) in its immediate parent frame.

The final center before fill is (54,33) in initial axes, or
(43.6189661312,45.8517807031) in the inner frame. It lies beyond that frame's
y=40 edge. The four final corners are (78,48),(30,48),(30,18),(78,18).
All expected polygons are prescribed endpoints, independent of candidate state.
The old Single C side/rotation/fill sequence is unchanged.

Keep the inherited six ordinary moves, nondegenerate checkpoints, actual visible
handle/fill acquisition, representation-independent bitmap observer, tolerances,
preservation checks and raw coverage semantics. No held-drag Escape. One root
entry then visible selectors; no URL-only required mode.

Finite controls: gold, complete alternate, baseline, geometry-only partial.
The first two must fully pass. Baseline must visibly fail. The retained GPT6
partial must preserve resize geometry but fail actual out-of-parent acquisition;
missing controls require before/after pixel and source causal qualification,
never automatic conversion of generic coverage/runtime errors into failure.
Existing other partials remain retained, outside this minimum control set.
