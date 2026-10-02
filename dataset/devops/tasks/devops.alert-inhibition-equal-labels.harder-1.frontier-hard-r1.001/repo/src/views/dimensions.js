import { clear, element } from "./components.js";

export function renderDimensions(policy) {
  const host = clear(document.querySelector('[data-test="dimensions"]'));
  for (const dimension of policy.dimensionRegistry) {
    const row = element("article", "dimension");
    row.dataset.test = `dimension-${dimension.name}`;
    row.dataset.role = dimension.role;
    row.append(
      element("strong", "", dimension.name),
      element("span", "dimension-role", dimension.role),
      element("small", "", dimension.note),
    );
    host.append(row);
  }
}
