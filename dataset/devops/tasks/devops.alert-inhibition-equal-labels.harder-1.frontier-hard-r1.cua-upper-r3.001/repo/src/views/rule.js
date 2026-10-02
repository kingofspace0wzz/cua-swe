import { clear, element } from "./components.js";

function matcherText(matcher) {
  return `${matcher.label} ${matcher.operator} ${matcher.value}`;
}

export function renderRule(rule) {
  const host = clear(document.querySelector('[data-test="rule"]'));
  const sections = [
    ["Source", rule.source_matchers.map(matcherText)],
    ["Target", rule.target_matchers.map(matcherText)],
    ["Equal", rule.equal],
    ["Required on source", rule.required_source_labels],
    ["Required on target", rule.required_target_labels],
  ];
  for (const [label, values] of sections) {
    const row = element("div", "rule-row");
    row.append(
      element("span", "", label),
      element("code", "", values.length ? values.join(", ") : "none"),
    );
    host.append(row);
  }
}
