import {
  clear,
  element,
  labelText,
} from "./components.js";

function renderAlert(alert) {
  const card = element("article", "alert-card");
  card.dataset.test = `alert-${alert.id}`;
  card.dataset.status = alert.status;
  card.append(
    element("strong", "", alert.displayName),
    element("span", `severity severity-${alert.severity}`, alert.severity),
    element("p", "", alert.summary),
    element("code", "", labelText(alert.labels)),
  );
  if (alert.inhibitedBy) {
    card.append(
      element("small", "inhibitor", `inhibited by ${alert.inhibitedBy}`),
    );
  }
  return card;
}

export function renderQueues(snapshot) {
  const firing = clear(document.querySelector('[data-test="firing"]'));
  const suppressed = clear(document.querySelector('[data-test="suppressed"]'));
  for (const alert of snapshot.firing) firing.append(renderAlert(alert));
  for (const alert of snapshot.suppressed) suppressed.append(renderAlert(alert));
}
