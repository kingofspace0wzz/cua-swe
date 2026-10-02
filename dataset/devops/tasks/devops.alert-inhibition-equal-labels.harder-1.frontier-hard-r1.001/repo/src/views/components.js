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

export function labelText(labels) {
  return Object.entries(labels)
    .map(([name, value]) => `${name}=${value === "" ? '""' : value}`)
    .join(" · ");
}
