import { Group, Rect, Point, LayoutManager, FixedLayout } from '../vendor/fabric.mjs';

// Native artwork assembly. Single retains the original feed-defined rectangle.
export function mountArtwork({ canvas, rect, scene, installHandleEdits }) {
  if (new URLSearchParams(location.search).get('artwork') === 'single') {
    installHandleEdits(canvas, rect);
    canvas.add(rect);
    canvas.setActiveObject(rect);
    rect.setCoords();
    return;
  }

  rect.set({ width: 60, height: 36, angle: 15, originX: 'center', originY: 'center' });
  const frameOptions = {
    originX: 'center', originY: 'center',
    interactive: true, subTargetCheck: true,
    selectable: false, evented: true, hasControls: false, hasBorders: false,
  };
  const inner = new Group([rect], {
    ...frameOptions, width: 120, height: 80,
    backgroundColor: '#555b65', layoutManager: new LayoutManager(new FixedLayout()),
  });
  const amber = new Rect({
    width: 16, height: 16, originX: 'center', originY: 'center',
    fill: '#e2a43b', strokeWidth: 0,
    selectable: false, evented: false, hasControls: false, hasBorders: false,
  });
  const outer = new Group([inner, amber], {
    ...frameOptions, width: 180, height: 120,
    backgroundColor: '#343840', layoutManager: new LayoutManager(new FixedLayout()),
  });

  // Group construction performs native initial layout. Declare parent-local
  // placements only after both constructors have completed that layout.
  outer.set({ angle: -15, scaleX: 1.1, scaleY: .9 });
  outer.setPositionByOrigin(new Point(scene.object.left, scene.object.top), 'center', 'center');
  inner.set({ angle: -10, scaleX: 1, scaleY: 1 });
  inner.setPositionByOrigin(new Point(0, 0), 'center', 'center');
  rect.setPositionByOrigin(new Point(0, 0), 'center', 'center');
  amber.setPositionByOrigin(new Point(60, 0), 'center', 'center');
  installHandleEdits(canvas, rect);
  canvas.add(outer);
  outer.setCoords();
}
