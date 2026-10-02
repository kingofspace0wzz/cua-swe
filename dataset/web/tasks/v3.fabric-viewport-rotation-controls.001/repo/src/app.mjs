// Object Editor product surface built on the REAL, pinned fabric.js browser
// build (vendored verbatim at fd50b70 under vendor/fabric.mjs). Only this
// product shell and the evaluator-owned scene feed are authored; the zoom,
// dimensions, control-coordinate, and control-render geometry this task
// exercises is the unmodified upstream fabric code.
//
// The editor loads a "camera preset" for the design surface from the
// harness-owned scene feed (served same-origin at /scene). The preset is the
// canvas viewport transform plus the object placed on the artboard. The shell
// selects the object so fabric draws its selection border and corner handles,
// and mirrors the live fabric geometry into window.__geom for observation.
import * as fabric from '../vendor/fabric.mjs';

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
  const rect = new fabric.Rect({
    left: spec.left,
    top: spec.top,
    width: spec.width,
    height: spec.height,
    angle: spec.angle || 0,
    fill: 'rgb(120, 170, 220)',
    strokeWidth: 0,
    borderColor: 'rgb(255, 64, 64)',
    cornerColor: 'rgb(255, 64, 64)',
    cornerStrokeColor: 'rgb(255, 255, 255)',
    cornerSize: 12,
    transparentCorners: false,
    padding: spec.padding || 0,
    originX: spec.originX || 'left',
    originY: spec.originY || 'top',
  });
  canvas.add(rect);
  canvas.setActiveObject(rect);
  rect.setCoords();
  canvas.requestRenderAll();
  canvas.renderAll();

  zoomEl.textContent = `zoom ${canvas.getZoom().toFixed(3)}`;

  // Capture the angle fabric applies when it draws the selection frame.
  const realCtx = canvas.contextTop || canvas.contextContainer;
  const rotateCalls = [];
  const origRotate = realCtx.rotate.bind(realCtx);
  realCtx.rotate = (a) => { rotateCalls.push(a); return origRotate(a); };
  rect._renderControls(realCtx, { hasBorders: true, hasControls: true });
  realCtx.rotate = origRotate;

  const oc = rect.oCoords;
  const dim = rect._calculateCurrentDimensions();
  window.__geom = {
    preset: scene.name,
    zoom: canvas.getZoom(),
    viewportTransform: canvas.viewportTransform.slice(),
    dim: { x: dim.x, y: dim.y },
    oCoords: {
      tl: { x: oc.tl.x, y: oc.tl.y },
      tr: { x: oc.tr.x, y: oc.tr.y },
      br: { x: oc.br.x, y: oc.br.y },
      bl: { x: oc.bl.x, y: oc.bl.y },
    },
    controlRenderAngle: rotateCalls.length ? rotateCalls[0] : null,
  };

  setStatus(`preset ${scene.name} ready`, true);
}

main();
