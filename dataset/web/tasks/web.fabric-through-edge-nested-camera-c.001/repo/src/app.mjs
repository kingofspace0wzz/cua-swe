// Artboard shell using pinned Fabric and scene-space rectangle edits.
import * as fabric from '../vendor/fabric.mjs';
import { mountArtwork } from './artwork-fixture.mjs';

const statusEl = document.getElementById('status');
const zoomEl = document.getElementById('zoom-readout');
const presetEl = document.getElementById('preset-name');

function setStatus(text, ok) {
  statusEl.textContent = text;
  statusEl.className = ok ? 'ok' : 'busy';
}

async function main() {
  const canvasEl = document.getElementById('artboard');
  const canvas = new fabric.Canvas(canvasEl, {
    width: 800,
    height: 600,
    backgroundColor: '#0f1115',
    selection: false,
    skipOffscreen: false,
    renderOnAddRemove: false,
    preserveObjectStacking: true,
  });

  setStatus('loading camera preset…', false);
  const params = new URLSearchParams(location.search);
  const preset = params.get('preset') || 'A';
  let scene;
  try {
    const res = await fetch(`/scene?preset=${encodeURIComponent(preset)}`, {
      cache: 'no-store',
    });
    scene = await res.json();
  } catch (err) {
    setStatus('camera preset unavailable', false);
    window.__geom = { error: String(err) };
    return;
  }

  presetEl.textContent = `${scene.name} (${scene.description})`;

  // Apply the camera preset viewport transform delivered by the scene feed.
  canvas.setViewportTransform(scene.viewportTransform);

  const spec = scene.object;
  const rect = new ArtboardRect({
    left: spec.left,
    top: spec.top,
    width: spec.width,
    height: spec.height,
    angle: spec.angle || 0,
    fill: 'rgb(120, 170, 220)',
    strokeWidth: 0,
    // This simple shape paints directly, including every interactive preview.
    objectCaching: false,
    borderColor: 'rgb(255, 64, 64)',
    cornerColor: 'rgb(255, 64, 64)',
    cornerStrokeColor: 'rgb(255, 255, 255)',
    cornerSize: 12,
    transparentCorners: false,
    padding: spec.padding || 0,
    originX: spec.originX || 'left',
    originY: spec.originY || 'top',
  });
  mountArtwork({ canvas, rect, scene, installHandleEdits });
  canvas.requestRenderAll();
  canvas.renderAll();

  zoomEl.textContent = `zoom ${canvas.getZoom().toFixed(3)}`;

  setStatus(`preset ${scene.name} ready`, true);
}

// Project the rectangle's actual edges, rather than decomposing the camera into
// an angle and two scales (which loses shear after an object rotation).
class ArtboardRect extends fabric.Rect {
  calcOCoords() {
    const matrix = fabric.util.multiplyTransformMatrices(
      this.getViewportTransform(), this.calcTransformMatrix());
    const center = new fabric.Point(0, 0).transform(matrix);
    const xAxis = new fabric.Point(matrix[0], matrix[1]);
    const yAxis = new fabric.Point(matrix[2], matrix[3]);
    const ux = xAxis.scalarDivide(Math.hypot(xAxis.x, xAxis.y));
    const uy = yAxis.scalarDivide(Math.hypot(yAxis.x, yAxis.y));
    const coords = {};
    this.forEachControl((control, key) => {
      const position = center
        .add(xAxis.scalarMultiply(control.x * this.width))
        .add(yAxis.scalarMultiply(control.y * this.height))
        .add(ux.scalarMultiply(2 * control.x * this.padding + control.offsetX))
        .add(uy.scalarMultiply(2 * control.y * this.padding + control.offsetY));
      coords[key] = Object.assign(position, this._calcCornerCoords(control, position));
    });
    return coords;
  }

  _renderControls(ctx, styleOverride = {}) {
    const style = {hasBorders: this.hasBorders, hasControls: this.hasControls,
      borderColor: this.borderColor, borderDashArray: this.borderDashArray,
      ...styleOverride};
    const coords = this.oCoords;
    const retina = this.getCanvasRetinaScaling();
    ctx.save();
    ctx.setTransform(retina, 0, 0, retina, 0, 0);
    ctx.globalAlpha = this.isMoving ? this.borderOpacityWhenMoving : 1;
    if (style.hasBorders) {
      ctx.strokeStyle = style.borderColor;
      ctx.lineWidth = this.borderScaleFactor;
      this._setLineDash(ctx, style.borderDashArray);
      ctx.beginPath();
      ['tl', 'tr', 'br', 'bl'].forEach((key, i) => {
        const p = coords[key];
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.closePath();
      if (style.hasControls && this.controls.mtr.getVisibility(this, 'mtr')) {
        ctx.moveTo(coords.mt.x, coords.mt.y);
        ctx.lineTo(coords.mtr.x, coords.mtr.y);
      }
      ctx.stroke();
    }
    if (style.hasControls) this.drawControls(ctx, styleOverride);
    ctx.restore();
  }
}

main();

// All handles share a transaction captured from the latest committed geometry.
// Pointer deltas are mapped into the immediate parent frame, then projected
// onto the current local edges. For Single, the parent frame is the scene.
function installHandleEdits(canvas, rect) {
  const surface = canvas.upperCanvasEl;
  const signs = {tl: [-1,-1], tr: [1,-1], br: [1,1], bl: [-1,1],
    ml: [-1,0], mr: [1,0], mt: [0,-1], mb: [0,1]};
  let edit = null;
  function viewport(e) {
    const box = surface.getBoundingClientRect();
    return new fabric.Point((e.clientX-box.left)*canvas.width/box.width,
      (e.clientY-box.top)*canvas.height/box.height);
  }
  function paint() { rect.setCoords(); canvas.requestRenderAll(); }
  function finish(cancel) {
    if (!edit) return;
    const saved = edit;
    edit = null;
    if (cancel) rect.set(saved.original);
    paint();
    if (surface.hasPointerCapture(saved.id)) surface.releasePointerCapture(saved.id);
  }
  surface.addEventListener('pointerdown', e => {
    if (edit || e.button !== 0 || !e.isPrimary) return;
    const hit = rect.findControl(viewport(e));
    if (!hit || (!signs[hit.key] && hit.key !== 'mtr') ||
        canvas.getActiveObject() !== rect) return;
    // Own this gesture before Fabric's compatibility mouse events acquire it.
    e.preventDefault(); e.stopImmediatePropagation();
    const [sx,sy] = signs[hit.key] || [0,0];
    // Snapshot the entire camera/ancestor chain, not Blue's own transform:
    // its angle and dimensions are expressed in its immediate parent's plane.
    const parentToViewport = rect.group
      ? fabric.util.multiplyTransformMatrices(canvas.viewportTransform,
          rect.group.calcTransformMatrix())
      : canvas.viewportTransform;
    const viewportToParent = fabric.util.invertTransform(parentToViewport);
    const center = rect.getRelativeCenterPoint();
    const start = viewport(e).transform(viewportToParent);
    const angle = rect.angle * Math.PI / 180;
    const u = new fabric.Point(Math.cos(angle), Math.sin(angle));
    const v = new fabric.Point(-Math.sin(angle), Math.cos(angle));
    const width = rect.getScaledWidth(), height = rect.getScaledHeight();
    edit = {id:e.pointerId, key:hit.key, sx, sy, start, center, u, v, width, height,
      viewportToParent,
      anchor: center.subtract(u.scalarMultiply(sx*width/2))
        .subtract(v.scalarMultiply(sy*height/2)),
      pointerAngle: Math.atan2(start.y-center.y, start.x-center.x),
      original: {left:rect.left, top:rect.top, width:rect.width, height:rect.height,
        scaleX:rect.scaleX, scaleY:rect.scaleY, angle:rect.angle}};
    surface.setPointerCapture(e.pointerId);
  }, true);
  function update(e) {
    if (!edit || edit.id !== e.pointerId) return;
    e.preventDefault(); e.stopImmediatePropagation();
    const p = viewport(e).transform(edit.viewportToParent);
    const {sx,sy,anchor,start,u,v,center} = edit;
    if (edit.key === 'mtr') {
      const delta = Math.atan2(p.y-center.y, p.x-center.x) - edit.pointerAngle;
      rect.set('angle', edit.original.angle + delta * 180 / Math.PI);
      rect.setPositionByOrigin(center, 'center', 'center');
    } else {
      const delta = p.subtract(start);
      const width = sx ? Math.max(1, edit.width+sx*(delta.x*u.x+delta.y*u.y)) : edit.width;
      const height = sy ? Math.max(1, edit.height+sy*(delta.x*v.x+delta.y*v.y)) : edit.height;
      rect.set({scaleX:width/edit.original.width, scaleY:height/edit.original.height});
      rect.setPositionByOrigin(anchor.add(u.scalarMultiply(sx*width/2))
        .add(v.scalarMultiply(sy*height/2)), 'center', 'center');
    }
    paint();
  }
  surface.addEventListener('pointermove', update, true);
  surface.addEventListener('pointerup', e => {
    if (!edit || edit.id !== e.pointerId) return;
    update(e); finish(false);
  }, true);
  surface.addEventListener('pointercancel', e => {
    if (edit && edit.id === e.pointerId) finish(true);
  }, true);
  surface.addEventListener('lostpointercapture', () => finish(true));
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape' && edit) { e.preventDefault(); finish(true); }
  });
  window.addEventListener('blur', () => finish(true));
}
