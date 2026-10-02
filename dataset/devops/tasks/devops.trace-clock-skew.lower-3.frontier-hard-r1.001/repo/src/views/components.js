export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

export function byId(spans) {
  return new Map(spans.map((span) => [span.id, span]));
}
