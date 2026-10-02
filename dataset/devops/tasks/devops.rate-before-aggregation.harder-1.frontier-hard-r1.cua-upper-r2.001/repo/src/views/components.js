export function clear(node) {
  while (node.firstChild) node.firstChild.remove();
}

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function setText(selector, value) {
  document.querySelector(selector).textContent = value ?? "—";
}
