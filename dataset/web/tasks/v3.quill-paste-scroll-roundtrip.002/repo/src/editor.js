// Collaborative document rendering for the Threadloop reading surface.
//
// The reading surface is a real Quill editor. The shared document is loaded as
// a Quill Delta (one line per block, headings carry Quill's `header` format),
// and every collaborative update is an actual Quill edit. Quill owns the line
// boxes and the scroll container, so reading anchors, presence, and inserted
// content all refer to the DOM nodes Quill renders. Each logical block keeps a
// stable id which we stamp onto the Quill line node so callers can measure it.

import Quill from 'quill';

// Mount a read-only Quill editor into `host` and load the shared document as a
// Delta. Returns the live Quill instance. The editor is read-only for the
// reader; collaborative updates arrive through Quill's editing API, not typing.
export function mountEditor(host, blocks) {
  const quill = new Quill(host, {
    theme: 'snow',
    readOnly: true,
    modules: { toolbar: false },
  });
  const doc = blocks.map((b, i) => ({
    id: b.id || `blk-${i}`,
    kind: b.kind || 'para',
    text: b.text,
  }));
  loadDelta(quill, doc);
  stampBlockIds(quill, doc);
  return { quill, doc };
}

// The scroll region is Quill's editor root (`.ql-editor`).
export function scrollRegion(quill) {
  return quill.root;
}

function loadDelta(quill, doc) {
  const Delta = Quill.import('delta');
  const delta = new Delta();
  for (const block of doc) {
    delta.insert(block.text);
    delta.insert('\n', block.kind === 'head' ? { header: 2 } : {});
  }
  quill.setContents(delta, 'silent');
}

// Stamp each logical block id onto the DOM node Quill rendered for that line so
// presence, anchors and inserted content can be located by id.
export function stampBlockIds(quill, doc) {
  const lines = quill.getLines();
  for (let i = 0; i < doc.length && i < lines.length; i++) {
    const node = lines[i].domNode;
    if (node) {
      node.dataset.blockId = doc[i].id;
      node.classList.add(doc[i].kind === 'head' ? 'doc-head' : 'doc-para');
    }
  }
}

// Insert one incoming block into the live Quill document at the given block
// index and return the freshly rendered Quill line node so callers can measure
// it. The insertion is a genuine Quill edit (updateContents on a Delta), which
// is what changes the document height and drives the paste-then-scroll behavior.
export function insertBlock(quill, doc, index, incoming) {
  const Delta = Quill.import('delta');
  const block = {
    id: incoming.id || `ins-${Date.now()}`,
    kind: incoming.kind || 'para',
    text: incoming.text,
  };
  // Character offset where the new line begins: sum of every preceding line's
  // text plus its trailing newline.
  let offset = 0;
  for (let i = 0; i < index && i < doc.length; i++) {
    offset += doc[i].text.length + 1;
  }
  const attrs = block.kind === 'head' ? { header: 2 } : {};
  const edit = new Delta().retain(offset).insert(block.text).insert('\n', attrs);
  quill.updateContents(edit, 'api');
  doc.splice(index, 0, block);
  stampBlockIds(quill, doc);
  const node = blockNode(quill, block.id);
  if (node) node.classList.add('doc-inserted');
  return node;
}

export function blockNode(quill, blockId) {
  return quill.root.querySelector(`[data-block-id="${blockId}"]`);
}

// Viewport-relative top of a block within Quill's scroll region.
export function blockOffsetTop(quill, node) {
  return node.getBoundingClientRect().top - quill.root.getBoundingClientRect().top;
}
